from copy import deepcopy
import json
import unittest

from test_java_regression import controller


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.rules = deepcopy(controller.APPROVED_STARTUP_DIFFERENCES["template_differences"])

    def rows(self, rule, rust=None):
        java = {**rule["key"], rule["field"]: rule["java"], "last_updated_stamp": "java-time"}
        if rust is None:
            rust = (controller.convert_template(rule["java"], "java", "rust")
                    if "validator" in rule else rule["rust"])
        return [{"schema": "schema", "records": [{"table": rule["table"], "row": row}]}
                for row in (java, {**java, rule["field"]: rust, "last_updated_stamp": "rust-time"})]

    def test_all_approved_templates_convert_and_leave_other_fields_strict(self):
        for rule in self.rules:
            with self.subTest(key=rule["key"], field=rule["field"]):
                snapshots = self.rows(rule)
                applied = controller.apply_template_differences(snapshots, [rule])
                self.assertEqual(len(applied), 1)
                self.assertEqual(snapshots[1]["records"][0]["row"][rule["field"]], rule["java"])
                self.assertEqual(snapshots[1]["records"][0]["row"]["last_updated_stamp"], "rust-time")
                self.assertEqual(snapshots[1]["schema"], "schema")

    def test_nested_ternary_round_trip_and_quoted_operators(self):
        java = "literal ?: || ${name?:'keep ?: ||'} ${a ? (b ? c + ' ' : '') : ''}"
        rust = controller.convert_template(java, "java", "rust")
        self.assertEqual(rust, "literal ?: || ${name || 'keep ?: ||'} ${a ? ( b ? c + ' ' : '' ) : ''}")
        self.assertEqual(controller.convert_template(rust, "rust", "java"),
                         controller.convert_template(java, "java", "java"))

    def test_actual_nested_username_template_validates(self):
        rule = self.rules[2]
        rust = ("${userFullName || (lastName ? (firstName ? firstName + ' ' : '') + lastName : '')} "
                "[${username || userId || ''}]")
        snapshots = self.rows(rule, rust)
        self.assertEqual(len(controller.apply_template_differences(snapshots, [rule])), 1)
        for value in (rust.replace(" + lastName", ""), rust.replace("' '", "''")):
            self.assertEqual(controller.apply_template_differences(self.rows(rule, value), [rule]), [])

    def test_unknown_missing_duplicate_changed_and_wrong_dialect_fail_closed(self):
        rule = self.rules[0]
        valid = controller.convert_template(rule["java"], "java", "rust")
        for changed in (valid.replace("lookedUpStatusId", "otherId"), valid + "!",
                        valid.replace(" || ", " ?: "), None, "${execute()}", "${broken", "${{nested}}"):
            with self.subTest(changed=changed):
                snapshots = self.rows(rule, valid)
                snapshots[1]["records"][0]["row"][rule["field"]] = changed
                original = deepcopy(snapshots)
                self.assertEqual(controller.apply_template_differences(snapshots, [rule]), [])
                self.assertEqual(snapshots, original)
        for side in (0, 1):
            for duplicate in (False, True):
                snapshots = self.rows(rule)
                snapshots[side]["records"] *= 2 if duplicate else 0
                original = deepcopy(snapshots)
                self.assertEqual(controller.apply_template_differences(snapshots, [rule]), [])
                self.assertEqual(snapshots, original)
        snapshots = self.rows(rule)
        snapshots[0]["records"][0]["row"][rule["field"]] += "!"
        self.assertEqual(controller.apply_template_differences(snapshots, [rule]), [])
        self.assertEqual(controller.apply_template_differences(self.rows(rule), []), [])

    def test_full_approval_does_not_mutate_raw_snapshots(self):
        rule = self.rules[2]
        snapshots = self.rows(rule)
        for snapshot in snapshots:
            snapshot["records"] = [json.dumps(record) for record in snapshot["records"]]
        original = deepcopy(snapshots)
        normalized, applied = controller.apply_approved_differences(
            *snapshots, {"theme_resources": [], "full_text_indexes": [], "template_differences": [rule]})
        self.assertEqual(snapshots, original)
        self.assertEqual(len(applied), 1)
        rows = [snapshot["records"][0]["row"] for snapshot in normalized]
        self.assertEqual(rows[0][rule["field"]], rows[1][rule["field"]])
        self.assertNotEqual(rows[0]["last_updated_stamp"], rows[1]["last_updated_stamp"])

    def test_exact_link_approval_does_not_allow_other_routes(self):
        rule = self.rules[-1]
        snapshots = self.rows(rule, rule["rust"].replace("/qapps/System", "/qapps/Other"))
        self.assertEqual(controller.apply_template_differences(snapshots, [rule]), [])

    def test_unsupported_expression_syntax_rejected(self):
        for template in ("${a; run()}", "${a == b}", "${a['key']}", "${}", "${'unterminated}"):
            with self.subTest(template=template):
                with self.assertRaises(ValueError):
                    controller.convert_template(template, "java", "rust")
