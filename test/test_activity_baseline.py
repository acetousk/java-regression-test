"""Step 5 excludes loading differences, never activity-induced differences."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from deterministic import DeterministicCoordinator

spec = importlib.util.spec_from_file_location('activity_controller', Path(__file__).resolve().parents[1] / 'java-regression-test.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class ActivityBaselineTests(unittest.TestCase):
    def snapshot(self, rows, schema='schema'):
        return {'schema': schema, 'records': [json.dumps({'table': 'public.person', 'row': row}) for row in rows]}

    def compare(self, java, rust, baselines):
        def normalize(snapshot):
            return {**snapshot, 'records': [json.loads(record) for record in snapshot['records']]}
        with tempfile.TemporaryDirectory() as directory, patch.object(
                controller, 'apply_approved_differences', side_effect=lambda left, right, _: (
                    [normalize(left), normalize(right)], [])):
            return controller.diff_compare(controller.DatabaseState(java), controller.DatabaseState(rust),
                                           directory, approved_differences={}, activity_baselines=list(map(normalize, baselines)))

    def test_existing_loading_differences_do_not_fail_matching_activity_writes(self):
        java = self.snapshot([{'id': 'java-seed'}], 'java-schema')
        rust = self.snapshot([{'id': 'rust-seed'}], 'rust-schema')
        baselines = [java, rust]
        self.assertTrue(self.compare(java, rust, baselines))
        customer = {'id': 'customer', 'name': 'Regression'}
        self.assertTrue(self.compare(self.snapshot([{'id': 'java-seed'}, customer], 'java-schema'),
                                     self.snapshot([{'id': 'rust-seed'}, customer], 'rust-schema'), baselines))

    def test_new_mismatch_and_deletion_are_not_hidden(self):
        baseline = self.snapshot([{'id': 'existing'}])
        self.assertFalse(self.compare(self.snapshot([{'id': 'existing'}, {'id': 'new'}]), baseline,
                                      [baseline, baseline]))
        self.assertFalse(self.compare(self.snapshot([]), baseline, [baseline, baseline]))
        self.assertFalse(self.compare(baseline, self.snapshot([{'id': 'existing'}], 'changed-schema'),
                                      [baseline, baseline]))

    def test_bootstrap_requires_idle_boundary_before_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            cdc = Mock(return_value=[])
            coordinator = DeterministicCoordinator('run', directory, cdc=cdc, bootstrap=True)
            request = {'version': 1, 'run_id': 'run', 'engine': 'java', 'sequence': 1, 'event': 'begin'}
            begun = coordinator.exchange(request)
            establish = Mock()
            with self.assertRaisesRegex(RuntimeError, 'idle engines'):
                coordinator.activate(establish)
            establish.assert_not_called()
            coordinator.exchange({**request, 'event': 'complete', 'outcome': 'committed',
                                  'operation_id': begun['operation_id']})
            cdc.assert_not_called()
            coordinator.activate(establish)
            establish.assert_called_once()
            self.assertFalse(coordinator.bootstrap)
            begun = coordinator.exchange({**request, 'sequence': 2})
            coordinator.exchange({**request, 'sequence': 2, 'event': 'complete', 'outcome': 'committed',
                                  'operation_id': begun['operation_id']})
            cdc.assert_called_once_with('java')
