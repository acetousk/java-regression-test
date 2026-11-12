"""Phase 2 Change 13: extension ownership must come from retained catalog evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_java_regression import controller


class ExtensionViewTests(unittest.TestCase):
    def test_exact_ownership_metadata_and_absence_required(self):
        metadata = {'relation': 'public.extension_summary', 'kind': 'v',
                    'extension': {'name': 'example_extension', 'version': '1.2'},
                    'view_definition': 'SELECT count(*) FROM example_extension_internal;',
                    'columns': [{'name': 'count', 'type': 'bigint',
                                 'not_null': False, 'default': None}]}
        rule = {'engine': 'rust', 'metadata': metadata}
        for change in ('none', 'missing_owner', 'version', 'owner', 'column',
                       'shared', 'duplicate', 'row', 'ddl', 'materialized', 'definition'):
            with self.subTest(change=change):
                snapshots = [{'schema': '', 'records': []},
                             {'schema': '', 'records': [deepcopy(metadata)]}]
                view = snapshots[1]['records'][0]
                if change == 'missing_owner': view.pop('extension')
                if change == 'version': view['extension']['version'] = '1.3'
                if change == 'owner': view['extension']['name'] = 'other_extension'
                if change == 'column': view['columns'][0]['type'] = 'text'
                if change == 'shared': snapshots[0]['records'].append(deepcopy(metadata))
                if change == 'duplicate': snapshots[1]['records'].append(deepcopy(metadata))
                if change == 'row': snapshots[1]['records'].append({'table': metadata['relation'], 'row': {}})
                if change == 'ddl': snapshots[1]['schema'] = 'CREATE VIEW public.extension_summary AS SELECT 1;'
                if change == 'materialized': view['kind'] = 'm'
                if change == 'definition': view['view_definition'] = 'SELECT secret FROM shared_table;'
                before = deepcopy(snapshots)
                applied = controller.apply_extension_views(snapshots, [rule])
                self.assertEqual(bool(applied), change == 'none')
                if change != 'none': self.assertEqual(snapshots, before)
                else: self.assertEqual(snapshots[1]['records'], [])

    def test_catalog_capture_uses_snapshot_and_extension_dependency(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                controller.subprocess, 'check_output', side_effect=['schema', '']) as call:
            controller.capture_snapshot('container', Path(directory) / 'snapshot.json',
                                        snapshot_id='00000003-00000010-1')
        self.assertIn('--snapshot=00000003-00000010-1', call.call_args_list[0].args[0])
        sql = call.call_args_list[1].kwargs['input']
        self.assertLess(sql.index('SET TRANSACTION SNAPSHOT'), sql.index('SELECT json_build_object'))
        for required in ("dep.classid='pg_class'::regclass", "dep.refclassid='pg_extension'::regclass",
                         "dep.deptype='e'", 'dep.objsubid=0', "'version', e.extversion"):
            self.assertIn(required, sql)


if __name__ == '__main__':
    unittest.main()
