from copy import deepcopy
import json
import unittest

from test_java_regression import controller


class ApprovedSchemaTests(unittest.TestCase):
    def setUp(self):
        self.approved = controller.APPROVED_STARTUP_DIFFERENCES
        self.rule = self.approved["rust_only_columns"][0]

    def column_snapshots(self):
        rule = self.rule
        column = {"name": rule["name"], "type": rule["type"], "not_null": False, "default": None}
        base = {"name": "id", "type": "text", "not_null": False, "default": None}
        snapshots = []
        for rust in (False, True):
            columns = [deepcopy(base)] + ([deepcopy(column)] if rust else [])
            ddl = "    id text" + (",\n    " + rule["name"] + " " + rule["type"] if rust else "")
            row = {"id": "one", **({rule["name"]: None} if rust else {})}
            snapshots.append({"schema": f'CREATE TABLE {rule["table"]} (\n{ddl}\n);', "records": [
                {"relation": rule["table"], "kind": "r", "columns": columns},
                {"table": rule["table"], "row": row}]})
        return snapshots

    def test_exact_column_is_removed_without_touching_shared_values(self):
        snapshots = self.column_snapshots()
        self.assertEqual(len(controller.apply_rust_only_columns(snapshots, [self.rule])), 1)
        self.assertEqual(snapshots[0], snapshots[1])

    def test_column_definition_shared_presence_and_non_null_data_remain_strict(self):
        for change in ("type", "default", "not_null", "data", "java", "ddl", "missing", "duplicate"):
            with self.subTest(change=change):
                snapshots = self.column_snapshots()
                column = snapshots[1]["records"][0]["columns"][-1]
                if change == "type":
                    column["type"] = "text"
                elif change == "default":
                    column["default"] = "'x'::text"
                elif change == "not_null":
                    column["not_null"] = True
                elif change == "data":
                    snapshots[1]["records"][1]["row"][self.rule["name"]] = "business-data"
                elif change == "java":
                    snapshots[0]["records"][0]["columns"].append(deepcopy(column))
                elif change == "ddl":
                    snapshots[1]["schema"] = snapshots[1]["schema"].replace(self.rule["type"], "text")
                elif change == "missing":
                    snapshots[1]["records"].pop(0)
                else:
                    snapshots[1]["records"].append(deepcopy(snapshots[1]["records"][0]))
                raw = deepcopy(snapshots)
                self.assertEqual(controller.apply_rust_only_columns(snapshots, [self.rule]), [])
                self.assertEqual(snapshots, raw)

    def test_exact_ddl_keeps_unlisted_tables_and_setup_statements(self):
        for rule in self.approved["rust_only_ddl"]:
            with self.subTest(name=rule["name"]):
                shared = "SET default_tablespace = '';\nCREATE TABLE search.unlisted (id text);\n"
                snapshots = [{"schema": shared}, {"schema": "".join(rule["blocks"]) + shared}]
                self.assertEqual(len(controller.apply_rust_only_ddl(snapshots, [rule])), 1)
                self.assertEqual(snapshots[0], snapshots[1])

    def test_changed_shared_or_duplicate_ddl_is_not_approved(self):
        for rule in self.approved["rust_only_ddl"]:
            for change in ("changed", "missing", "java", "duplicate"):
                with self.subTest(name=rule["name"], change=change):
                    ddl = "".join(rule["blocks"])
                    snapshots = [{"schema": ""}, {"schema": ddl}]
                    if change == "changed":
                        snapshots[1]["schema"] = ddl.replace("moqui", "other").replace("public", "other")
                    elif change == "missing":
                        snapshots[1]["schema"] = ""
                    elif change == "java":
                        snapshots[0]["schema"] = f'CREATE {rule["kind"]} {rule["name"]};'
                    else:
                        snapshots[1]["schema"] += ddl
                    raw = deepcopy(snapshots)
                    self.assertEqual(controller.apply_rust_only_ddl(snapshots, [rule]), [])
                    self.assertEqual(snapshots, raw)

    def test_full_approval_preserves_raw_evidence(self):
        raw = self.column_snapshots()
        for snapshot in raw:
            snapshot["records"] = [json.dumps(item) for item in snapshot["records"]]
        original = deepcopy(raw)
        normalized, applied = controller.apply_approved_differences(*raw, {
            "theme_resources": [], "full_text_indexes": [], "rust_only_columns": [self.rule]})
        self.assertEqual(raw, original)
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(len(applied), 1)
