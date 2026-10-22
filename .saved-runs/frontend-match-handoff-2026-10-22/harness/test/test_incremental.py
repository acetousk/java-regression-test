import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from incremental import DatabaseState, EVENT_PREFIX, events
from test_java_regression import controller


def change(kind, old=None, new=None, table='public.example'):
    event = {'kind': kind, 'table': table, 'old': old, 'new': new}
    raw = f'table {table}: {kind.upper()}: irrelevant plugin row text'
    payload = json.dumps(event).replace("'", "''")
    return [raw, EVENT_PREFIX + "'" + payload + "'"]


def baseline(records=()):
    return {'schema': 'schema', 'records': [json.dumps({
        'relation': 'public.example', 'kind': 'r', 'columns': []}), *records]}


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.java, self.rust = (DatabaseState(baseline()) for _ in range(2))

    def compare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return controller.diff_compare(self.java, self.rust, self.path)

    def test_insert_update_delete_key_change_and_exact_numbers(self):
        first = '{"id":1,"amount":123456789012345678901234567890.123456789,"value":null}'
        second = '{"id":2,"amount":1.00,"value":"a \' quoted \\u2603"}'
        for kind, old, new in [('insert', None, first), ('update', first, second), ('delete', second, None)]:
            for state in (self.java, self.rust):
                state.apply([change(kind, old, new)])
            self.assertTrue(self.compare())
        self.assertFalse(self.java.rows['public.example'])

    def test_duplicates_and_numeric_equivalence(self):
        self.java.apply([change('insert', new='{"id":1,"value":1.00}') * 2])
        self.rust.apply([change('insert', new='{"value":1,"id":1}') * 2])
        self.assertTrue(self.compare())
        self.java.apply([change('delete', old='{"value":1,"id":1}')])
        self.assertFalse(self.compare())
        report = json.loads((self.path / 'comparison.json').read_text())
        self.assertEqual(report['unapproved_record_byte_differences'][0]['count'], 1)

    def test_truncate_and_schema_drift(self):
        for state in (self.java, self.rust):
            state.apply([change('insert', new='{"id":1}')])
            state.apply([change('truncate')])
        self.assertTrue(self.compare())
        self.rust.schema = 'different index definition'
        self.assertFalse(self.compare())
        self.assertTrue((self.path / 'unapproved-schema.diff').exists())

    def test_unknown_or_missing_capture_poison_the_state(self):
        for batch in ([['table public.example: INSERT: id[integer]:1']],
                      [[EVENT_PREFIX + "'{}'"]], [['unknown message']]):
            state = DatabaseState(baseline())
            with self.assertRaises(ValueError):
                state.apply(batch)
            self.assertFalse(state.healthy)
            with self.assertRaises(ValueError):
                state.snapshot()

    def test_missing_old_row_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, 'old row missing'):
            self.java.apply([change('delete', old='{"id":1}')])
        self.assertFalse(self.java.healthy)

    def test_decimal_drift_and_string_number_distinction(self):
        self.java.apply([change('insert', new='{"id":1,"value":123456789012345678901234567890}')])
        self.rust.apply([change('insert', new='{"id":1,"value":123456789012345678901234567891}')])
        self.assertFalse(self.compare())
        self.rust.apply([change('update', old='{"id":1,"value":123456789012345678901234567891}',
                                new='{"id":1,"value":"123456789012345678901234567890"}')])
        self.assertFalse(self.compare())

    def test_unchanged_relations_reuse_canonical_counters_and_no_snapshot_capture(self):
        self.assertTrue(self.compare())
        counter = self.java.comparison_cache['public.example']
        with patch.object(controller, 'capture_snapshot', side_effect=AssertionError('must not scan')):
            self.assertTrue(self.compare())
        self.assertIs(counter, self.java.comparison_cache['public.example'])

    def test_catalog_drop_removes_rows_and_unsupported_relations_fail(self):
        self.java.apply([change('insert', new='{"id":1}')])
        self.java.refresh_catalog({'schema': 'empty', 'records': []})
        self.assertFalse(self.java.rows)
        for kind in ('m', 'f'):
            with self.assertRaisesRegex(ValueError, 'dedicated incremental adapter'):
                self.rust.refresh_catalog({'schema': 'schema', 'records': [json.dumps({
                    'relation': 'public.example', 'kind': kind, 'columns': []})]})

    def test_ddl_row_rewrite_requires_targeted_postgres_readback(self):
        self.java.apply([change('insert', new='{"id":1}')])
        catalog = {'schema': 'altered', 'records': [json.dumps({'relation': 'public.example', 'kind': 'r',
                    'columns': [{'name': 'id'}, {'name': 'defaulted'}]})]}
        calls = []
        self.java.refresh_catalog(catalog, reload_rows=lambda table: calls.append(table) or [
            '{"table":"public.example","row":{"id":1,"defaulted":"v"}}'])
        self.assertEqual(calls, ['public.example'])
        self.assertIn('defaulted', self.java.snapshot()['records'][-1])

    def test_rollback_has_no_committed_events_and_schema_events_are_retained(self):
        self.java.apply([])
        self.assertEqual(self.java.transactions, 0)
        self.java.apply([[EVENT_PREFIX + "'{\"kind\":\"schema\",\"tag\":\"CREATE TABLE\"}'"]])
        self.assertTrue(self.java.schema_dirty)
        self.assertEqual(self.java.transactions, 1)

    def test_capture_quoted_text_is_not_truncated(self):
        text = "large ' apostrophe ] [ \\ newline\n" * 100
        row = json.dumps({'id': 1, 'value': text})
        self.assertEqual(events(change('insert', new=row))[0]['new'], row)


if __name__ == '__main__':
    unittest.main()
