"""Phase 2 Change 15: generated sequence timestamps must be exact supplied milliseconds."""
import unittest
from unittest.mock import patch
from acceptance.ui.data_clock_proof import _visit_sequence_stamp


class SequenceClockProofTests(unittest.TestCase):
    def test_exact_timestamp_is_read_without_float_rounding(self):
        with patch('acceptance.ui.data_clock_proof.subprocess.check_output', return_value='1794513029199.000\n'):
            self.assertEqual(_visit_sequence_stamp('owned-test'), 1794513029199)

    def test_missing_duplicate_and_fractional_timestamps_fail(self):
        for output in ('', '1\n2\n', '1794513029199.001\n', 'NaN\n'):
            with self.subTest(output=output), patch('acceptance.ui.data_clock_proof.subprocess.check_output', return_value=output):
                with self.assertRaises(RuntimeError):
                    _visit_sequence_stamp('owned-test')
