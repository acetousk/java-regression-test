"""Phase2 Change20: capture never hides altered observation or adjacent application SQL."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_java_regression import controller


class ObservationCaptureTests(unittest.TestCase):
    footer = '--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict MoquiRegression\n\n'

    def fixture(self, kind='row'):
        events, level = ('INSERT OR DELETE OR UPDATE', 'ROW') if kind == 'row' else ('TRUNCATE', 'STATEMENT')
        header = f'--\n-- Name: sample moqui_regression_{kind}; Type: TRIGGER; Schema: public; Owner: moqui\n--\n\n'
        statement = (f'CREATE TRIGGER moqui_regression_{kind} AFTER {events} ON public.sample FOR EACH {level} '
                     'EXECUTE FUNCTION moqui_regression.row_change();\n\n\n')
        return header, statement

    def capture(self, schema):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'snapshot.json'
            with patch.object(controller.subprocess, 'check_output', side_effect=[schema, '']):
                controller.capture_snapshot('mocked-container', destination)
            return json.loads(destination.read_text())['schema']

    def test_exact_generated_triggers_removed_with_footer_retained(self):
        for kind in ('row', 'truncate'):
            with self.subTest(kind=kind):
                header, statement = self.fixture(kind)
                self.assertEqual(self.capture(header + statement + self.footer), self.footer)

    def test_adjacent_unheaded_sql_and_comments_remain_exact(self):
        header, statement = self.fixture()
        for extra in ('ALTER TABLE public.shared ADD COLUMN hidden text;\n',
                      'SELECT 42;\n', '-- application comment\n',
                      "DO $$ BEGIN RAISE NOTICE 'unrelated'; END $$;\n"):
            with self.subTest(extra=extra):
                self.assertEqual(self.capture(header + statement + extra + self.footer), extra + self.footer)

    def test_altered_trigger_definitions_remain_exact(self):
        for kind in ('row', 'truncate'):
            header, statement = self.fixture(kind)
            alterations = [
                statement.replace('EXECUTE FUNCTION', 'WHEN (false) EXECUTE FUNCTION'),
                statement.replace('AFTER ', 'BEFORE '),
                statement.replace('FOR EACH ROW', 'FOR EACH STATEMENT') if kind == 'row'
                    else statement.replace('FOR EACH STATEMENT', 'FOR EACH ROW'),
                statement.replace('row_change()', 'other_change()'),
                statement.replace('row_change()', "row_change('arg')"),
                statement.replace(' FOR EACH ', ' DEFERRABLE INITIALLY DEFERRED FOR EACH '),
                statement.replace('CREATE TRIGGER', 'CREATE CONSTRAINT TRIGGER'),
                statement.replace('AFTER INSERT OR DELETE OR UPDATE', 'AFTER INSERT') if kind == 'row'
                    else statement.replace('AFTER TRUNCATE', 'AFTER DELETE'),
            ]
            for altered in alterations:
                with self.subTest(kind=kind, altered=altered):
                    schema = header + altered + self.footer
                    self.assertEqual(self.capture(schema), schema)

    def test_disabled_and_always_enabled_trigger_retained(self):
        header, statement = self.fixture()
        for state in ('DISABLE', 'ENABLE REPLICA', 'ENABLE ALWAYS'):
            for target in ('moqui_regression_row', 'ALL', 'USER'):
                with self.subTest(state=state, target=target):
                    schema = header + statement + f'ALTER TABLE public.sample {state} TRIGGER {target};\n' + self.footer
                    self.assertEqual(self.capture(schema), schema)

    def test_wrong_header_or_unheaded_trigger_is_not_removed(self):
        header, statement = self.fixture()
        for prefix in ('', header.replace('Name: sample ', 'Name: other '),
                       header.replace('Schema: public', 'Schema: other')):
            schema = prefix + statement + self.footer
            self.assertEqual(self.capture(schema), schema)

    def test_trigger_text_inside_literals_and_nested_comments_remains_exact(self):
        header, statement = self.fixture()
        fake = header + statement
        for before, after in (("SELECT '", "';\n"),
                              ('CREATE FUNCTION public.sample() RETURNS text AS $body$\n', '$body$ LANGUAGE sql;\n'),
                              ('/* outer /* inner */\n', '*/\n')):
            with self.subTest(before=before):
                schema = before + fake + after + self.footer
                self.assertEqual(self.capture(schema), schema)
