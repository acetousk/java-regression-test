import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_java_regression import controller


class SnapshotTests(unittest.TestCase):
    def compare(self, left_rows, right_rows, left_schema="schema", right_schema="schema"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left, right = root / "left.json", root / "right.json"
            for path, rows, schema in ((left, left_rows, left_schema), (right, right_rows, right_schema)):
                path.write_text(json.dumps({"schema": schema, "records": rows}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                equal = controller.snapshot_compare(left, right, root)
            report = json.loads((root / "comparison.json").read_text())
            return equal, report, output.getvalue()

    def test_order_and_exact_numeric_precision(self):
        equal, _, _ = self.compare(
            ['{"a":1.00,"b":null}', '{"a":2}'],
            ['{"a":2}', '{"b":null,"a":1}'],
        )
        self.assertTrue(equal)
        equal, _, _ = self.compare(['{"a":123456789012345678901234567890}'],
                                   ['{"a":123456789012345678901234567891}'])
        self.assertFalse(equal)
        self.assertFalse(self.compare(['{"a":"1"}'], ['{"a":1}'])[0])

    def test_duplicate_rows_report_exact_bytes_and_counts(self):
        equal, report, output = self.compare(['{"a":1}'], ['{"a":1}', '{"a":1}'])
        self.assertFalse(equal)
        difference = report["record_byte_differences"][0]
        self.assertEqual(difference["side"], "rust")
        self.assertEqual(difference["count"], 1)
        record = bytes.fromhex(difference["hex"]).decode("utf-8")
        self.assertEqual(record, report["rust_only_records"][0])
        self.assertEqual(json.loads(output), report)

    def test_all_schema_byte_ranges_are_reported(self):
        equal, report, _ = self.compare([], [], "aé middle X end", "aè middle Y end!")
        self.assertFalse(equal)
        differences = report["schema_byte_differences"]
        self.assertEqual(len(differences), 3)
        left, right = "aé middle X end".encode(), "aè middle Y end!".encode()
        for difference in differences:
            for side, data in (("java", left), ("rust", right)):
                chunk = bytes.fromhex(difference[f"{side}_hex"])
                start = difference[f"{side}_offset"]
                self.assertEqual(data[start:start + len(chunk)], chunk)

    def test_incremental_comparison_fails_without_tracking(self):
        with self.assertRaises(NotImplementedError):
            controller.diff_compare(None, None, None)


if __name__ == "__main__":
    unittest.main()
