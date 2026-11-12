"""Phase2 Change21: bounded reviewed event sets retain all unlisted runtime events."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from test_java_regression import controller


class ReviewedEventTests(unittest.TestCase):
    def fixture(self):
        first = dict(event_id='1', subject='seed-a', field='name', old=None, new='a',
                     actor=None, visit=None, stack='load', time='2026-01-01T00:00:00', updated='2026-01-01T00:00:00')
        second = {**first, 'event_id': '2', 'subject': 'seed-b', 'new': 'b'}
        moved = {**second, 'event_id': '3'}
        extra = {**first, 'event_id': '2', 'subject': 'seed-c', 'new': 'c'}
        metadata = dict(relation='public.events', kind='r', columns=[dict(name=key) for key in first])
        snapshots = [dict(schema='', records=[deepcopy(metadata)] + [dict(table='public.events', row=deepcopy(row))
            for row in side]) for side in ([first, second], [first, extra, moved])]
        rule = dict(table='public.events', primary_key=['event_id'],
                    shared_pairs=[dict(java=first, rust=deepcopy(first)), dict(java=second, rust=moved)], rust_only=[extra])
        return snapshots, rule

    def apply(self, snapshots, rules, original=None):
        return controller.apply_reviewed_event_sets(snapshots, deepcopy(snapshots) if original is None else original, rules)

    def test_exact_pairs_and_extra_events_with_cross_side_id_collision(self):
        snapshots, rule = self.fixture()
        original = deepcopy(snapshots)
        applied = self.apply(snapshots, [rule], original)
        self.assertEqual(len(applied), 1)
        self.assertEqual((applied[0]['java_rows'], applied[0]['rust_rows']), (2, 3))
        self.assertEqual(applied[0]['shared_pairs'], rule['shared_pairs'])
        self.assertEqual(applied[0]['rust_only'], rule['rust_only'])
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(len(snapshots[0]['records']), 1)
        self.assertEqual(original, self.fixture()[0])

    def test_future_operation_events_remain_strict(self):
        snapshots, rule = self.fixture()
        future = dict(table='public.events', row={**rule['rust_only'][0], 'event_id': '10', 'subject': 'runtime'})
        snapshots[1]['records'].append(future)
        self.assertEqual(len(self.apply(snapshots, [rule])), 1)
        self.assertIn(future, snapshots[1]['records'])
        self.assertNotEqual(snapshots[0], snapshots[1])

    def test_changed_or_missing_row_fails_whole_rule(self):
        for field in ('time', 'updated', 'actor', 'visit', 'stack', 'subject', 'old', 'new', 'event_id'):
            snapshots, rule = self.fixture()
            snapshots[1]['records'][-1]['row'][field] = 'changed'
            before = deepcopy(snapshots)
            self.assertEqual(self.apply(snapshots, [rule]), [], field)
            self.assertEqual(snapshots, before)
        snapshots, rule = self.fixture()
        snapshots[1]['records'].pop()
        before = deepcopy(snapshots)
        self.assertEqual(self.apply(snapshots, [rule]), [])
        self.assertEqual(snapshots, before)

    def test_duplicates_collisions_semantic_overlap_and_bad_rules_reject(self):
        for change in ('row_duplicate', 'id_collision', 'payload_duplicate', 'extra_exists_java', 'overlap',
                       'pair_payload', 'missing_field', 'extra_field', 'duplicate_rule', 'empty_key',
                       'unknown_key', 'boolean_key', 'malformed_pair', 'unknown_rule_field'):
            with self.subTest(change=change):
                snapshots, rule = self.fixture()
                rules = [rule]
                if change == 'row_duplicate': snapshots[1]['records'].append(deepcopy(snapshots[1]['records'][-1]))
                elif change == 'id_collision': snapshots[1]['records'].append(dict(table='public.events', row={**rule['rust_only'][0], 'subject': 'different'}))
                elif change == 'payload_duplicate': snapshots[1]['records'].append(dict(table='public.events', row={**rule['rust_only'][0], 'event_id': '9'}))
                elif change == 'extra_exists_java': snapshots[0]['records'].append(dict(table='public.events', row={**rule['rust_only'][0], 'event_id': '9'}))
                elif change == 'overlap': rule['rust_only'].append(deepcopy(rule['shared_pairs'][0]['rust']))
                elif change == 'pair_payload': rule['shared_pairs'][1]['java']['actor'] = 'other'
                elif change == 'missing_field': del rule['rust_only'][0]['stack']
                elif change == 'extra_field': rule['rust_only'][0]['unknown'] = None
                elif change == 'duplicate_rule': rules.append(deepcopy(rule))
                elif change == 'empty_key': rule['primary_key'] = []
                elif change == 'unknown_key': rule['primary_key'] = ['unknown']
                elif change == 'boolean_key': rule['rust_only'][0]['event_id'] = True
                elif change == 'malformed_pair': rule['shared_pairs'].append({'java': {}})
                elif change == 'unknown_rule_field': rule['normalize'] = True
                before = deepcopy(snapshots)
                self.assertEqual(self.apply(snapshots, rules), [])
                self.assertEqual(snapshots, before)

    def test_missing_original_or_current_evidence_cannot_be_hidden(self):
        for side in ('original', 'current'):
            snapshots, rule = self.fixture()
            original = deepcopy(snapshots)
            (original if side == 'original' else snapshots)[1]['records'].pop()
            before = deepcopy(snapshots)
            self.assertEqual(self.apply(snapshots, [rule], original), [])
            self.assertEqual(snapshots, before)

    def test_numeric_types_do_not_collapse_into_booleans_or_strings(self):
        for value in ('1', True):
            snapshots, rule = self.fixture()
            rule['rust_only'][0]['new'] = 1
            snapshots[1]['records'][2]['row']['new'] = value
            self.assertEqual(self.apply(snapshots, [rule]), [])
        snapshots, rule = self.fixture()
        rule['rust_only'][0]['new'] = 1
        snapshots[1]['records'][2]['row']['new'] = Decimal('1.0')
        self.assertEqual(len(self.apply(snapshots, [rule])), 1)

    def test_complete_snapshot_raw_verdict_stays_false(self):
        snapshots, rule = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / (side + '.json') for side in ('java', 'rust')]
            for path, snapshot in zip(paths, snapshots):
                path.write_text(json.dumps({**snapshot, 'records': [json.dumps(record) for record in snapshot['records']]}))
            before = [path.read_bytes() for path in paths]
            rules = {**controller.APPROVED_STARTUP_DIFFERENCES, 'reviewed_event_sets': [rule]}
            self.assertTrue(controller.snapshot_compare(*paths, root, approved_differences=rules, emit_report=False))
            report = json.loads((root / 'comparison.json').read_text())
            self.assertFalse(report['row_and_sequence_values_equal'])
            self.assertTrue(report['records_equal_after_approved_differences'])
            self.assertEqual([path.read_bytes() for path in paths], before)
