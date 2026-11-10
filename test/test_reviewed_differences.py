"""Change 6: user approval cannot hide shared rows, changed grants or timestamps."""
from copy import deepcopy
import unittest
from test_java_regression import controller
from test_approved_tables import ApprovedTableTests


class ReviewedDifferencesTests(unittest.TestCase):
    def test_java_only_relation_uses_absence_guards(self):
        fixture = ApprovedTableTests()
        fixture.setUp()
        snapshots = list(reversed(deepcopy(fixture.snapshots)))
        self.assertEqual(controller.apply_java_only_tables(snapshots, [fixture.table]),
                         [{'kind': 'java_only_table', 'table': fixture.table, 'rows': 1}])
        self.assertEqual(*snapshots)
        snapshots = list(reversed(deepcopy(fixture.snapshots)))
        snapshots[1]['records'].append(deepcopy(fixture.row))
        before = deepcopy(snapshots)
        self.assertEqual(controller.apply_java_only_tables(snapshots, [fixture.table]), [])
        self.assertEqual(snapshots, before)

    def test_reviewed_rows_require_exact_values_and_absence(self):
        rule = {'engine': 'rust', 'table': 'public.grants', 'key': {'id': 'approved'},
                'expected': {'id': 'approved', 'permission': 'read'}}
        row = {'table': rule['table'], 'row': {**rule['expected'], 'last_updated_stamp': '2026-01-01'}}
        for mutation in ('none', 'permission', 'extra', 'duplicate', 'shared', 'unlisted'):
            with self.subTest(mutation=mutation):
                snapshots = [{'records': []}, {'records': [deepcopy(row)]}]
                if mutation == 'permission': snapshots[1]['records'][0]['row']['permission'] = 'admin'
                if mutation == 'extra': snapshots[1]['records'][0]['row']['other'] = 'x'
                if mutation == 'duplicate': snapshots[1]['records'].append(deepcopy(row))
                if mutation == 'shared': snapshots[0]['records'].append(deepcopy(row))
                if mutation == 'unlisted': snapshots[1]['records'][0]['row']['id'] = 'unlisted'
                before = deepcopy(snapshots)
                applied = controller.apply_reviewed_seed_rows(snapshots, [rule])
                self.assertEqual(bool(applied), mutation == 'none')
                if mutation != 'none': self.assertEqual(snapshots, before)

    def test_new_approvals_do_not_include_unapproved_schema_or_stamp(self):
        approved = controller.APPROVED_STARTUP_DIFFERENCES
        self.assertEqual(len(approved['java_only_tables']), 17)
        self.assertNotIn('public.agent_definition', approved['rust_only_tables'])
        self.assertFalse(any(r['name'] in ('password_used', 'last_updated_stamp')
                             for r in approved['rust_only_columns']))
