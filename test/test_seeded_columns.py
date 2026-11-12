"""Phase2 Change22: added column seeds need complete original values and a real primary key."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from test_java_regression import controller


class SeededColumnTests(unittest.TestCase):
    def fixture(self):
        primary = dict(kind='index', name='sample_pk', columns=['id'], method='btree', unique=True,
                       primary=True, exclusion=False, valid=True, ready=True, live=True, expressions=None,
                       predicate=None, constraint_backed=True, plain=True, key_count=1, attribute_count=1,
                       key_metadata=[dict(opclass='pg_catalog.text_ops', collation='pg_catalog.default', option=0)],
                       options=None, owner='tester', partition=False, table_inherits=False,
                       definition='CREATE UNIQUE INDEX sample_pk ON public.sample USING btree (id)')
        shared = [dict(name='id', type='character varying(40)', not_null=True, default=None),
                  dict(name='value', type='text', not_null=False, default=None)]
        column = dict(name='extra', type='character varying(40)', not_null=False, default=None)
        snapshots = [dict(schema='CREATE TABLE public.sample (\n    id character varying(40) NOT NULL,\n    value text'
            + (',\n    extra character varying(40)' if rust else '') + '\n);\n', records=[
                dict(relation='public.sample', kind='r', columns=deepcopy(shared)+([deepcopy(column)] if rust else []),
                     schema_objects=[deepcopy(primary)]),
                dict(table='public.sample', row=dict(id='one', value='shared', **({'extra':'seed'} if rust else {}))),
                dict(table='public.sample', row=dict(id='two', value='unchanged', **({'extra':None} if rust else {})))])
            for rust in (False, True)]
        rule = dict(table='public.sample', name='extra', type='character varying(40)', primary_key=['id'],
                    seed_values=[dict(key={'id':'one'}, value='seed')])
        return snapshots, rule

    def apply(self, snapshots, rule, original=None):
        return controller.apply_rust_only_columns(snapshots, [rule], original=original)

    def test_exact_seed_projects_only_column_and_keeps_raw(self):
        snapshots, rule = self.fixture()
        original = deepcopy(snapshots)
        applied = self.apply(snapshots, rule, original)
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]['seed_values'], rule['seed_values'])
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(original, self.fixture()[0])

    def test_shared_field_changes_and_future_rows_remain_strict(self):
        snapshots, rule = self.fixture()
        snapshots[1]['records'][1]['row']['value'] = 'different'
        future = dict(table='public.sample', row=dict(id='future', value='runtime', extra=None))
        snapshots[1]['records'].append(future)
        self.assertEqual(len(self.apply(snapshots, rule)), 1)
        self.assertEqual(future['row'], dict(id='future', value='runtime'))
        self.assertNotEqual(snapshots[0], snapshots[1])

    def test_nullability_requires_boolean_false_in_current_and_original(self):
        for seeded in (False, True):
            for original_only in (False, True):
                for flag in (0, Decimal('0'), None, 'false', []):
                    with self.subTest(seeded=seeded, original_only=original_only, flag=flag):
                        snapshots, rule = self.fixture()
                        if not seeded:
                            rule.pop('primary_key')
                            rule.pop('seed_values')
                            snapshots[1]['records'][1]['row']['extra'] = None
                        original = deepcopy(snapshots)
                        changed = original if original_only else snapshots
                        changed[1]['records'][0]['columns'][-1]['not_null'] = flag
                        before = deepcopy(snapshots)
                        self.assertEqual(self.apply(snapshots, rule, original), [])
                        self.assertEqual(snapshots, before)

    def test_exact_catalog_primary_key_required(self):
        for change in ('missing', 'duplicate', 'not_primary', 'wrong_columns', 'not_unique', 'invalid',
                       'not_ready', 'not_live', 'not_constraint', 'expression', 'included', 'wrong_definition',
                       'nullable_key', 'missing_key_type', 'wrong_key_type', 'wrong_rule_key'):
            with self.subTest(change=change):
                snapshots, rule = self.fixture()
                metadata = snapshots[1]['records'][0]
                obj = metadata['schema_objects'][0]
                if change == 'missing': metadata.pop('schema_objects')
                elif change == 'duplicate': metadata['schema_objects'].append(deepcopy(obj))
                elif change == 'not_primary': obj['primary'] = False
                elif change == 'wrong_columns': obj['columns'] = ['value']
                elif change == 'not_unique': obj['unique'] = False
                elif change == 'invalid': obj['valid'] = False
                elif change == 'not_ready': obj['ready'] = False
                elif change == 'not_live': obj['live'] = False
                elif change == 'not_constraint': obj['constraint_backed'] = False
                elif change == 'expression': obj['expressions'] = 'lower(id)'
                elif change == 'included': obj['attribute_count'] = 2
                elif change == 'wrong_definition': obj['definition'] += ' WHERE id IS NOT NULL'
                elif change == 'nullable_key': metadata['columns'][0]['not_null'] = False
                elif change == 'missing_key_type': metadata['columns'][0].pop('type')
                elif change == 'wrong_key_type': metadata['columns'][0]['type'] = 'integer'
                elif change == 'wrong_rule_key': rule['primary_key'] = ['value']
                before = deepcopy(snapshots)
                self.assertEqual(self.apply(snapshots, rule), [])
                self.assertEqual(snapshots, before)

    def test_changed_missing_duplicate_and_unknown_values_fail_closed(self):
        for change in ('changed', 'missing_seed', 'seed_null', 'missing_field', 'missing_shared_field',
                       'extra_field', 'duplicate', 'unknown_nonnull', 'null_key', 'bool_key', 'partial_rule',
                       'duplicate_seed', 'unknown_rule_field', 'empty_seeds', 'seed_null_rule', 'bad_seed_key'):
            with self.subTest(change=change):
                snapshots, rule = self.fixture()
                row = snapshots[1]['records'][1]['row']
                if change == 'changed': row['extra'] = 'changed'
                elif change == 'missing_seed': snapshots[1]['records'].pop(1)
                elif change == 'seed_null': row['extra'] = None
                elif change == 'missing_field': row.pop('extra')
                elif change == 'missing_shared_field': row.pop('value')
                elif change == 'extra_field': row['unknown'] = None
                elif change == 'duplicate': snapshots[1]['records'].append(deepcopy(snapshots[1]['records'][1]))
                elif change == 'unknown_nonnull': snapshots[1]['records'][2]['row']['extra'] = 'unlisted'
                elif change == 'null_key': row['id'] = None
                elif change == 'bool_key': row['id'] = True
                elif change == 'partial_rule': rule.pop('seed_values')
                elif change == 'duplicate_seed': rule['seed_values'].append(deepcopy(rule['seed_values'][0]))
                elif change == 'unknown_rule_field': rule['ignore_other_values'] = True
                elif change == 'empty_seeds': rule['seed_values'] = []
                elif change == 'seed_null_rule': rule['seed_values'][0]['value'] = None
                elif change == 'bad_seed_key': rule['seed_values'][0]['key'] = {'value':'shared'}
                before = deepcopy(snapshots)
                self.assertEqual(self.apply(snapshots, rule), [])
                self.assertEqual(snapshots, before)

    def test_prior_exclusion_cannot_hide_original_changed_seed_or_nonnull(self):
        for seeded in (False, True):
            snapshots, rule = self.fixture()
            original = deepcopy(snapshots)
            original[1]['records'][1]['row']['extra'] = 'unapproved'
            snapshots[1]['records'].pop(1)
            if not seeded:
                rule.pop('primary_key'); rule.pop('seed_values')
            before = deepcopy(snapshots)
            self.assertEqual(self.apply(snapshots, rule, original), [])
            self.assertEqual(snapshots, before)

    def test_exact_original_seed_can_be_previously_excluded(self):
        snapshots, rule = self.fixture()
        original = deepcopy(snapshots)
        snapshots[1]['records'].pop(1)
        self.assertEqual(len(self.apply(snapshots, rule, original)), 1)

    def test_numeric_bool_and_string_values_are_not_conflated(self):
        for value in ('1', True):
            snapshots, rule = self.fixture()
            rule['seed_values'][0]['value'] = 1
            snapshots[1]['records'][1]['row']['extra'] = value
            self.assertEqual(self.apply(snapshots, rule), [])
        snapshots, rule = self.fixture()
        rule['seed_values'][0]['value'] = 1
        snapshots[1]['records'][1]['row']['extra'] = Decimal('1.0')
        self.assertEqual(len(self.apply(snapshots, rule)), 1)

    def test_full_snapshot_comparison_keeps_raw_difference(self):
        snapshots, rule = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / (side+'.json') for side in ('java','rust')]
            for path, snapshot in zip(paths, snapshots):
                path.write_text(json.dumps({**snapshot, 'records':[json.dumps(record) for record in snapshot['records']]}))
            raw = [path.read_bytes() for path in paths]
            approved = {**controller.APPROVED_STARTUP_DIFFERENCES, 'rust_only_columns':[rule]}
            self.assertTrue(controller.snapshot_compare(*paths, root, approved_differences=approved, emit_report=False))
            report = json.loads((root/'comparison.json').read_text())
            self.assertFalse(report['row_and_sequence_values_equal'])
            self.assertFalse(report['schema_dump_equal'])
            self.assertEqual([path.read_bytes() for path in paths], raw)

    def test_populated_foreign_key_is_not_approved_by_seeded_column(self):
        from test_schema_additions import SchemaAdditionTests
        snapshots, rule = self.fixture()
        obj_rule = SchemaAdditionTests().fixture('foreign_key')[1]
        obj_rule['catalog']['columns'] = ['extra']
        obj_rule['catalog']['definition'] = 'FOREIGN KEY (extra) REFERENCES public.parent(id)'
        obj_rule['ddl'] = 'ALTER TABLE ONLY public.sample\n    ADD CONSTRAINT sample_extra FOREIGN KEY (extra) REFERENCES public.parent(id);'
        snapshots[1]['records'][0]['schema_objects'].append(deepcopy(obj_rule['catalog']))
        snapshots[1]['schema'] += obj_rule['ddl'] + '\n'
        original = deepcopy(snapshots)
        applied = self.apply(snapshots, rule, original)
        self.assertEqual(len(applied), 1)
        self.assertEqual(controller.apply_schema_additions(snapshots, original, applied, [obj_rule]), [])
        self.assertIn(obj_rule['ddl'], snapshots[1]['schema'])
