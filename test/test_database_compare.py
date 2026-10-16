import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_java_regression import controller


class SnapshotTests(unittest.TestCase):
    def compare(self, left_rows, right_rows, left_schema="schema", right_schema="schema", **options):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left, right = root / "left.json", root / "right.json"
            for path, rows, schema in ((left, left_rows, left_schema), (right, right_rows, right_schema)):
                path.write_text(json.dumps({"schema": schema, "records": rows}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                equal = controller.snapshot_compare(left, right, root, **options)
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

    def test_summary_reports_empty_rust_only_tables_without_excluding_them(self):
        shared = json.dumps({"relation": "public.shared", "kind": "r", "columns": []})
        extra = json.dumps({"relation": "search.logs", "kind": "r", "columns": []})
        summary = controller.startup_summary({"records": [shared]}, {"records": [shared, extra]})
        self.assertTrue(summary["relation_inventory_available"])
        self.assertEqual(summary["java_only_relations"], [])
        self.assertEqual(summary["rust_only_relations"], ["search.logs"])
        self.assertFalse(summary["differences_excluded"])
        self.assertFalse(self.compare([shared], [shared, extra])[0])

    def test_summary_retains_timestamps_duplicates_and_numeric_types(self):
        left = ['{"table":"public.seed","row":{"id":1,"last_updated_stamp":"a"}}']
        right = ['{"table":"public.seed","row":{"id":"1","last_updated_stamp":"b"}}'] * 2
        summary = controller.startup_summary({"records": left}, {"records": right})
        table = summary["differing_tables"]["public.seed"]
        self.assertEqual(table["java_rows"], 1)
        self.assertEqual(table["rust_rows"], 2)
        self.assertEqual(table["java_unmatched_rows"], 1)
        self.assertEqual(table["rust_unmatched_rows"], 2)
        self.assertEqual(table["differing_column_multisets"], ["id", "last_updated_stamp"])

    def test_summary_reports_shared_schema_drift(self):
        left = {"relation": "public.seed", "columns": [{"name": "id", "type": "text"}]}
        right = {"relation": "public.seed", "columns": [{"name": "id", "type": "bigint"}]}
        summary = controller.startup_summary(
            {"records": [json.dumps(left)]}, {"records": [json.dumps(right)]})
        self.assertEqual(summary["shared_relation_differences"]["public.seed"],
                         {"java": left, "rust": right})

    def test_summary_does_not_treat_equal_column_multisets_as_equal_rows(self):
        def snapshot(rows):
            return {"records": [json.dumps({"table": "public.seed", "row": row}) for row in rows]}
        summary = controller.startup_summary(
            snapshot([{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]),
            snapshot([{"id": 2, "value": "a"}, {"id": 1, "value": "b"}]))
        table = summary["differing_tables"]["public.seed"]
        self.assertEqual(table["differing_column_multisets"], [])
        self.assertEqual(table["java_unmatched_rows"], 2)
        self.assertEqual(table["rust_unmatched_rows"], 2)

    def test_statistics_diagnostic_checks_operation_counts_without_merging_bins(self):
        def snapshot(counts, operation="one", stamp="a"):
            return {"records": [json.dumps({"table": "public.artifact_hit_bin", "row": {
                "artifact_type": "AT_ENTITY", "artifact_sub_type": operation,
                "artifact_name": "moqui.basic.Enumeration", "hit_count": count,
                "hit_bin_id": str(index), "bin_start_date_time": stamp,
            }}) for index, count in enumerate(counts)]}
        left, right = snapshot([2]), snapshot([2], stamp="b")
        summary = controller.startup_summary(left, right)["artifact_bin_operations"]
        self.assertTrue(summary["diagnostic_only"])
        self.assertTrue(summary["operation_bin_multisets_equal"])
        # A matching total must not conceal duplicated or split bins.
        for right in (snapshot([2, 2]), snapshot([1, 1]), snapshot([3]), snapshot([2], "list")):
            summary = controller.startup_summary(left, right)["artifact_bin_operations"]
            self.assertFalse(summary["operation_bin_multisets_equal"])
            self.assertTrue(summary["differing_operations"])
        # This diagnostic never relaxes the actual snapshot gate.
        self.assertFalse(self.compare(left["records"], snapshot([2], stamp="b")["records"])[0])

    def test_incremental_comparison_fails_without_tracking(self):
        with self.assertRaises(NotImplementedError):
            controller.diff_compare(None, None, None)


if __name__ == "__main__":
    unittest.main()
