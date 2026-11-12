"""Regression tests for supplied-clock publication and fail-closed evidence checks."""
import tempfile
import unittest
from pathlib import Path
from acceptance.ui.data_clock import SuppliedDataClock, read_assignment, verify_persisted_millis


class DataClockTests(unittest.TestCase):
    def test_advance_only_after_paired_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock'
            clock = SuppliedDataClock(path, 1700000000000)
            with clock.paired_operation() as first:
                self.assertEqual(read_assignment(path), first)
                with self.assertRaises(RuntimeError):
                    clock.advance(first + 1)
            clock.advance(first + 1)
            self.assertEqual(read_assignment(path), first + 1)
            self.assertEqual(clock.environment()['MOQUI_TEST_DATA_CLOCK_FILE'], str(path))
            with self.assertRaises(ValueError):
                clock.advance(first)

    def test_invalid_assignment_never_reuses_old_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock'
            clock = SuppliedDataClock(path, 1700000000000)
            for bad in (b'', b'0', b'-1', b'1.5', b' 12', b'12\r\n', b'253402300800000', b'1' * 40):
                path.write_bytes(bad)
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    clock.verify_assignment()
            path.unlink()
            with self.assertRaises(ValueError):
                clock.environment()

    def test_failure_unwinds_pair_but_tampering_rejects_next_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock'
            clock = SuppliedDataClock(path, 1000)
            with self.assertRaises(RuntimeError):
                with clock.paired_operation():
                    raise RuntimeError('operation failed')
            clock.advance(2000)
            path.write_text('3000\n')
            with self.assertRaises(ValueError):
                clock.advance(4000)

    def test_proof_requires_supplied_instant_not_merely_equal_engines(self):
        verify_persisted_millis(1000, {'java': [1000], 'rust': [1000, 1000]})
        for observed in ({'java': [999], 'rust': [999]}, {'java': [], 'rust': []},
                         {'java': [1000]}, {'java': [1000], 'rust': ['1000']}):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                verify_persisted_millis(1000, observed)

    def test_never_overwrite_existing_file_and_reject_boolean_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock'
            path.write_text('existing')
            with self.assertRaises(FileExistsError):
                SuppliedDataClock(path, 1000)
            self.assertEqual(path.read_text(), 'existing')
            with self.assertRaises(ValueError):
                SuppliedDataClock(Path(directory) / 'other', True)

class DataClockProofTests(unittest.TestCase):
    def test_services_prove_each_assignment_independently(self):
        from unittest.mock import patch
        from acceptance.ui.data_clock_proof import prove_data_clock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock = SuppliedDataClock(root / 'clock', 1700000000000)
            def query(_container):
                return {'name': 'Clock proof ' + ('create' if clock.epoch_ms == 1700000000000 else 'update'),
                        'stamp_ms': clock.epoch_ms}
            with patch('acceptance.ui.data_clock_proof._startup_stamp', return_value=1700000000000), patch('acceptance.ui.data_clock_proof._visit_sequence_stamp', return_value=1700000000000) as sequence, patch('acceptance.ui.data_clock_proof._invoke') as invoke, patch('acceptance.ui.data_clock_proof._query', side_effect=query):
                report = prove_data_clock({'java': 1, 'rust': 2}, {'java': 'moqui-regression-2026-11-10_23-00-00.123Z-java', 'rust': 'moqui-regression-2026-11-10_23-00-00.123Z-rust'}, root, clock, disposable=True)
            self.assertTrue(report['passed'])
            self.assertEqual(invoke.call_count, 4)
            self.assertEqual(sequence.call_count, 2)
            self.assertTrue(report['sequence_bank']['passed'])
            self.assertEqual([x['supplied_epoch_ms'] for x in report['assignments']], [1700000000000, 1700000000001])
            self.assertFalse(report['optimistic_lock']['verified'])

    def test_startup_clock_mismatch_blocks_service_writes(self):
        from unittest.mock import patch
        from acceptance.ui.data_clock_proof import prove_data_clock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock = SuppliedDataClock(root / 'clock', 1000)
            with patch('acceptance.ui.data_clock_proof._startup_stamp', return_value=999), patch('acceptance.ui.data_clock_proof._invoke') as invoke:
                with self.assertRaises(ValueError):
                    prove_data_clock({'java': 1, 'rust': 2}, {'java': 'phase-three-java-proof', 'rust': 'phase-three-rust-proof'}, root, clock, disposable=True)
                invoke.assert_not_called()

    def test_ignored_clock_is_failure_with_evidence(self):
        from unittest.mock import patch
        import json
        from acceptance.ui.data_clock_proof import prove_data_clock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock = SuppliedDataClock(root / 'clock', 1000)
            with patch('acceptance.ui.data_clock_proof._startup_stamp', return_value=1000), patch('acceptance.ui.data_clock_proof._invoke'), patch('acceptance.ui.data_clock_proof._query', return_value={'name': 'Clock proof create', 'stamp_ms': 999}):
                with self.assertRaises(ValueError):
                    prove_data_clock({'java': 1, 'rust': 2}, {'java': 'phase-three-java-proof', 'rust': 'phase-three-rust-proof'}, root, clock, disposable=True)
            self.assertFalse(json.loads((root / 'data-clock-proof/proof.json').read_text())['passed'])

if __name__ == '__main__':
    unittest.main()
