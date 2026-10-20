from copy import deepcopy
import json
import unittest

import test_database_compare
from test_java_regression import controller


class ApprovedDifferencesTests(unittest.TestCase):
    def setUp(self):
        self.approved = deepcopy(controller.APPROVED_STARTUP_DIFFERENCES)

    def theme(self, side, stamp="same"):
        rule = self.approved["theme_resources"][0]
        return {"table": "public.screen_theme_resource", "row": {
            "screen_theme_id": rule["theme"], "sequence_num": rule["sequence"],
            "resource_type_enum_id": rule[side][0], "resource_value": rule[side][1],
            "last_updated_stamp": stamp,
        }}

    def compare(self, left, right, left_schema="schema", right_schema="schema"):
        # Reuse the full gate: raw evidence must remain even when approved differences pass.
        return test_database_compare.SnapshotTests().compare([json.dumps(r) for r in left], [json.dumps(r) for r in right],
                                       left_schema, right_schema)

    def test_exact_theme_difference_passes_but_raw_difference_remains(self):
        equal, report, _ = self.compare([self.theme("java")], [self.theme("rust")])
        self.assertTrue(equal)
        self.assertFalse(report["row_and_sequence_values_equal"])
        self.assertEqual(len(report["approved_differences_applied"]), 1)

    def test_shared_theme_timestamp_and_unknown_values_still_fail(self):
        self.assertFalse(self.compare([self.theme("java", "a")], [self.theme("rust", "b")])[0])
        row = self.theme("rust")
        row["row"]["resource_value"] = "/unexpected.css"
        self.assertFalse(self.compare([self.theme("java")], [row])[0])
        row = self.theme("rust")
        row["row"]["unexpected_column"] = "anything"
        self.assertFalse(self.compare([self.theme("java")], [row])[0])

    def test_duplicate_and_missing_shared_resources_still_fail(self):
        self.assertFalse(self.compare([self.theme("java")], [self.theme("rust")] * 2)[0])
        self.assertFalse(self.compare([self.theme("java")], [])[0])

    def test_only_exact_approved_absent_resource_passes(self):
        rule = self.approved["theme_resources"][1]
        row = {"table": "public.screen_theme_resource", "row": {
            "screen_theme_id": rule["theme"], "sequence_num": rule["sequence"],
            "resource_type_enum_id": rule["java"][0], "resource_value": rule["java"][1],
            "last_updated_stamp": "not comparable: approved absent on Rust",
        }}
        self.assertTrue(self.compare([row], [])[0])
        row["row"]["resource_value"] = "/unexpected.css"
        self.assertFalse(self.compare([row], [])[0])

    def statistic(self, table="public.artifact_hit_bin", offset=0):
        row = {"hit_bin_id": "100000", "artifact_type": "AT_ENTITY", "artifact_sub_type": "one",
               "artifact_name": "moqui.basic.Enumeration", "hit_count": 2,
               "server_ip_address": "127.0.0.1", "server_host_name": "test",
               "bin_start_date_time": f"2026-01-01T00:00:0{offset}",
               "bin_end_date_time": f"2026-01-01T00:00:0{offset + 1}",
               "last_updated_stamp": f"2026-01-01T00:00:0{offset + 1}",
               "total_time_millis": 2 + offset, "total_squared_time": 4 + offset,
               "min_time_millis": 1 + offset, "max_time_millis": 2 + offset,
               "slow_hit_count": offset}
        return {"table": table, "row": row}

    def test_custom_differences_do_not_inherit_default_approvals(self):
        equal, report, _ = test_database_compare.SnapshotTests().compare(
            [json.dumps(self.statistic())], [json.dumps(self.statistic(offset=1))],
            approved_differences={"theme_resources": [], "full_text_indexes": []})
        self.assertFalse(equal)
        self.assertEqual(report["approved_differences_applied"], [])

    def visit(self, java=True):
        return {"table": "public.visit", "row": {
            "visit_id": "100000", "session_id": "same", "initial_request": "/Login",
            "webapp_name": "ROOT" if java else None,
            "from_date": "2026-01-01T00:00:00" if java else "2026-01-01T00:00:01",
            "last_updated_stamp": "2026-01-01T00:00:02" if java else "2026-01-01T00:00:03",
        }}

    def test_java_servlet_session_fields_keep_raw_evidence(self):
        left, right = self.visit(), self.visit(False)
        original = deepcopy((left, right))
        equal, report, _ = self.compare([left], [right])
        self.assertTrue(equal)
        self.assertFalse(report["row_and_sequence_values_equal"])
        self.assertEqual(report["approved_differences_applied"][0]["kind"], "java_servlet_session_fields")
        self.assertEqual((left, right), original)

    def test_visit_other_fields_missing_rows_and_duplicates_stay_strict(self):
        for field in ("visit_id", "session_id", "initial_request", "thru_date", "unexpected_column"):
            with self.subTest(field=field):
                right = self.visit(False)
                right["row"][field] = "different"
                self.assertFalse(self.compare([self.visit()], [right])[0])
        self.assertFalse(self.compare([self.visit()], [])[0])
        self.assertFalse(self.compare([self.visit()], [self.visit(False)] * 2)[0])
        self.assertFalse(self.compare([self.visit()], [self.visit(False)], "schema", "other")[0])
        self.assertFalse(test_database_compare.SnapshotTests().compare(
            [json.dumps(self.visit())], [json.dumps(self.visit(False))],
            approved_differences={"theme_resources": [], "full_text_indexes": []})[0])

    def test_visit_url_ports_pass_without_changing_raw_values(self):
        for host in ("127.0.0.1", "[::1]"):
            with self.subTest(host=host):
                left, right = self.visit(), self.visit()
                for field in ("initial_request", "initial_referrer"):
                    left["row"][field] = f"http://{host}:28080/Login?next=%2Fapps#login"
                    right["row"][field] = f"http://{host}:28081/Login?next=%2Fapps#login"
                original = deepcopy((left, right))
                equal, report, _ = self.compare([left], [right])
                self.assertTrue(equal)
                self.assertFalse(report["row_and_sequence_values_equal"])
                self.assertTrue(any(rule["kind"] == "url_port_differences"
                                    for rule in report["approved_differences_applied"]))
                self.assertEqual((left, right), original)

    def test_visit_url_non_port_differences_remain_strict(self):
        left = self.visit()
        left["row"]["initial_request"] = "http://127.0.0.1:28080/Login?next=%2Fapps#login"
        for url in ("https://127.0.0.1:28081/Login?next=%2Fapps#login",
                    "http://localhost:28081/Login?next=%2Fapps#login",
                    "http://127.0.0.1:28081/Other?next=%2Fapps#login",
                    "http://127.0.0.1:28081/Login?next=%2Fother#login",
                    "http://127.0.0.1:28081/Login?next=/apps#login",
                    "http://127.0.0.1:28081/Login?next=%2Fapps#other",
                    "http://127.0.0.1:invalid/Login?next=%2Fapps#login",
                    None):
            with self.subTest(url=url):
                right = self.visit()
                right["row"]["initial_request"] = url
                self.assertFalse(self.compare([left], [right])[0])
        right = deepcopy(left)
        right["row"]["initial_request"] = "http://127.0.0.1:28081/Login?next=%2Fapps#login"
        self.assertFalse(test_database_compare.SnapshotTests().compare(
            [json.dumps(left)], [json.dumps(right)],
            approved_differences={"theme_resources": [], "full_text_indexes": []})[0])
        left["table"] = right["table"] = "public.other"
        self.assertFalse(self.compare([left], [right])[0])

    def test_statistics_timing_passes_but_raw_evidence_remains(self):
        equal, report, _ = self.compare([self.statistic()], [self.statistic(offset=1)])
        self.assertTrue(equal)
        self.assertFalse(report["row_and_sequence_values_equal"])
        self.assertEqual(report["approved_differences_applied"][0]["kind"], "statistics_timing")

    def test_statistics_counts_identity_duplicates_and_unknown_columns_still_fail(self):
        for field, value in (("hit_count", 3), ("hit_bin_id", "100001"),
                             ("artifact_sub_type", "list"), ("artifact_type", "AT_SERVICE"),
                             ("artifact_name", "other"), ("server_host_name", "other"),
                             ("unexpected_column", "anything")):
            with self.subTest(field=field):
                right = self.statistic(offset=1)
                right["row"][field] = value
                self.assertFalse(self.compare([self.statistic()], [right])[0])
        self.assertFalse(self.compare([self.statistic()], [self.statistic()] * 2)[0])
        self.assertFalse(self.compare([self.statistic()], [])[0])

    def split_statistics(self):
        rows = [self.statistic(), self.statistic(offset=1)]
        for index, item in enumerate(rows):
            item["row"]["hit_bin_id"] = str(100000 + index)
            item["row"]["hit_count"] = 1
        return rows

    def test_bin_splits_pass_and_keep_raw_evidence(self):
        equal, report, _ = self.compare([self.statistic()], self.split_statistics())
        self.assertTrue(equal)
        self.assertFalse(report["row_and_sequence_values_equal"])
        self.assertTrue(any(rule["kind"] == "statistics_bin_boundaries"
                            for rule in report["approved_differences_applied"]))
        self.assertTrue(self.compare(self.split_statistics(), [self.statistic()])[0])

    def test_equal_bin_counts_with_different_partitions_pass(self):
        left, right = self.split_statistics(), self.split_statistics()
        left[0]["row"]["hit_count"] = 3
        right[0]["row"]["hit_count"] = 2
        right[1]["row"]["hit_count"] = 2
        self.assertTrue(self.compare(left, right)[0])

    def test_bin_splits_keep_sequence_states_strict(self):
        def sequence(value):
            return {"table": "public.sequence_value_item", "row": {
                "seq_name": "moqui.server.ArtifactHitBin", "seq_num": value,
                "last_updated_stamp": "same"}}
        self.assertFalse(self.compare([self.statistic(), sequence(100100)],
                                      self.split_statistics() + [sequence(100200)])[0])

    def test_bin_splits_close_only_induced_id_gaps(self):
        left_next, right_next = self.statistic(), self.statistic()
        for item, identity in ((left_next, "100001"), (right_next, "100002")):
            item["row"]["artifact_name"] = "other"
            item["row"]["hit_bin_id"] = identity
        self.assertTrue(self.compare([self.statistic(), left_next],
                                     self.split_statistics() + [right_next])[0])
        right_next["row"]["hit_bin_id"] = "100003"
        self.assertFalse(self.compare([self.statistic(), left_next],
                                      self.split_statistics() + [right_next])[0])

    def test_bin_splits_do_not_hide_workload_host_or_invalid_data(self):
        for field, value in (("hit_count", 2), ("server_host_name", "other"),
                             ("artifact_name", "other"), ("unexpected_column", "anything"),
                             ("hit_bin_id", "100000"), ("bin_end_date_time", "invalid"),
                             ("slow_hit_count", 2)):
            with self.subTest(field=field):
                rows = self.split_statistics()
                rows[1]["row"][field] = value
                self.assertFalse(self.compare([self.statistic()], rows)[0])

    def test_bin_splits_require_explicit_approval(self):
        approved = deepcopy(self.approved)
        approved.pop("statistics_bin_boundaries")
        snapshots = [{"schema": "schema", "records": [json.dumps(row) for row in rows]}
                     for rows in ([self.statistic()], self.split_statistics())]
        normalized, applied = controller.apply_approved_differences(*snapshots, approved)
        self.assertFalse(controller.statistics_equal(normalized))
        self.assertFalse(any(rule["kind"] == "statistics_bin_boundaries" for rule in applied))

    def test_statistics_missing_or_invalid_timing_metrics_still_fail(self):
        for field, value in (("total_time_millis", -1), ("slow_hit_count", 3),
                             ("slow_hit_count", 0.5), ("bin_start_date_time", "bad date")):
            with self.subTest(field=field):
                right = self.statistic(offset=1)
                right["row"][field] = value
                self.assertFalse(self.compare([self.statistic()], [right])[0])
        right = self.statistic(offset=1)
        del right["row"]["max_time_millis"]
        self.assertFalse(self.compare([self.statistic()], [right])[0])

    def test_timing_approval_does_not_apply_to_other_tables(self):
        self.assertFalse(self.compare([self.statistic("public.other")],
                                      [self.statistic("public.other", offset=1)])[0])

    def test_individual_hit_timing_only_is_approved(self):
        def hit(offset):
            return {"table": "public.artifact_hit", "row": {
                "artifact_hit_id": "100000", "artifact_type": "AT_SERVICE", "artifact_name": "test",
                "start_date_time": f"2026-01-01T00:00:0{offset}",
                "last_updated_stamp": f"2026-01-01T00:00:0{offset}",
                "running_time_millis": 1 + offset, "is_slow_hit": "Y" if offset else "N",
                "was_error": "N"}}
        self.assertTrue(self.compare([hit(0)], [hit(1)])[0])
        right = hit(1)
        right["row"]["was_error"] = "Y"
        self.assertFalse(self.compare([hit(0)], [right])[0])

    def ssh_permission(self, permission="SSH_SFTP"):
        return {"table": "public.user_permission", "row": {
            "user_permission_id": permission, "description": "SSH", "last_updated_stamp": None}}

    def bin(self, bin_id, name, sub_type, count, end="2026-01-01T00:00:09"):
        row = self.statistic()
        row["row"].update({"hit_bin_id": bin_id, "artifact_name": name, "artifact_sub_type": sub_type,
                           "hit_count": count, "bin_end_date_time": end, "last_updated_stamp": end})
        return row

    def test_listed_rust_seed_addition_and_its_load_hits_pass(self):
        permission = "moqui.security.UserPermission"
        java = [self.bin("100000", permission, "create", 10), self.bin("100001", "other", "list", 1)]
        rust = [self.ssh_permission(), self.ssh_permission("SSH_SHELL"),
                self.bin("100000", permission, "create", 12), self.bin("100001", "other", "list", 1)]
        equal, report, _ = self.compare(java, rust)
        self.assertTrue(equal)
        kinds = [item["kind"] for item in report["approved_differences_applied"]]
        self.assertIn("rust_seed_addition", kinds)
        self.assertIn("seed_statistics", kinds)
        self.assertTrue(report["statistics_equal_after_approved_differences"])

    def test_seed_statistics_need_the_exact_row_difference(self):
        permission = "moqui.security.UserPermission"
        java = [self.bin("100000", permission, "create", 10)]
        # One more hit than the two listed rows explain.
        self.assertFalse(self.compare(java, [self.ssh_permission(), self.ssh_permission("SSH_SHELL"),
                                             self.bin("100000", permission, "create", 13)])[0])
        # A listed row missing from Rust approves neither the other row nor any hits.
        self.assertFalse(self.compare(java, [self.ssh_permission(),
                                             self.bin("100000", permission, "create", 11)])[0])
        # A listed row that Java also has is not a Rust addition.
        self.assertFalse(self.compare(java + [self.ssh_permission(), self.ssh_permission("SSH_SHELL")],
                                      [self.ssh_permission(), self.ssh_permission("SSH_SHELL"),
                                       self.bin("100000", permission, "create", 12)])[0])

    def test_rust_only_seed_bin_is_set_aside_and_later_ids_close_the_gap(self):
        message = {"table": "public.system_message_type", "row": {
            "system_message_type_id": "ExampleSftp", "last_updated_stamp": None}}
        name = "moqui.service.message.SystemMessageType"
        java = [self.bin("100000", "first", "list", 1), self.bin("100001", "last", "list", 1),
                self.bin("100101", "next", "list", 1, end="2026-01-01T00:00:10")]
        rust = [message, self.bin("100000", "first", "list", 1), self.bin("100001", name, "create", 1),
                self.bin("100002", name, "refresh", 1), self.bin("100003", "last", "list", 1),
                self.bin("100101", "next", "list", 1, end="2026-01-01T00:00:10")]
        self.assertTrue(self.compare(java, rust)[0])
        # Order is still strict: the bins after the set-aside ones must follow Java's order.
        rust[1]["row"]["hit_bin_id"], rust[4]["row"]["hit_bin_id"] = "100003", "100000"
        self.assertFalse(self.compare(java, rust)[0])

    def test_rust_only_statistics_are_listed_and_set_aside(self):
        java = [self.bin("100000", "moqui.basic.StatusItem", "one", 31)]
        rust = [self.bin("100000", "moqui.basic.StatusItem", "one", 31),
                self.bin("100001", "moqui.basic.StatusItem", "fk-check", 136),
                self.bin("100002", "moqui.basic.Enumeration", "load-report", 1)]
        equal, report, _ = self.compare(java, rust)
        self.assertTrue(equal)
        self.assertTrue(report["statistics_equal_after_approved_differences"])
        [rule] = [item for item in report["approved_differences_applied"] if item["kind"] == "rust_only_statistics"]
        self.assertEqual(rule["hit_count"], 137)
        # Raw evidence keeps the Rust-only bins.
        self.assertFalse(report["row_and_sequence_values_equal"])

    def test_rust_only_statistics_remain_excluded_after_restart(self):
        java = [self.bin("100000", "moqui.basic.StatusItem", "one", 31),
                self.bin("100101", "moqui.entity.feed.DataFeed", "list", 1,
                         end="2026-01-01T00:00:10")]
        rust = deepcopy(java) + [self.bin("100001", "moqui.basic.Enumeration", "load-report", 1)]
        equal, report, _ = self.compare(java, rust)
        self.assertTrue(equal)
        self.assertIn("rust_only_statistics", [item["kind"] for item in report["approved_differences_applied"]])
        # A shared bin later in the same flush still invalidates the exclusion.
        rust[1]["row"]["bin_end_date_time"] = java[0]["row"]["bin_end_date_time"]
        self.assertFalse(self.compare(java, rust)[0])

    def test_rust_only_statistics_must_follow_shared_bins_in_flush_and_be_rust_only(self):
        shared = self.bin("100001", "moqui.basic.StatusItem", "one", 31)
        java = [self.bin("100000", "moqui.basic.StatusItem", "one", 31)]
        # An FK bin ahead of a shared bin moves its id.
        self.assertFalse(self.compare(java, [self.bin("100000", "moqui.basic.StatusItem", "fk-check", 1), shared])[0])
        # A sub type Java also writes is not Rust-only.
        fk = self.bin("100001", "moqui.basic.StatusItem", "fk-check", 1)
        self.assertFalse(self.compare(java + [fk], [java[0], fk, self.bin("100002", "x", "fk-check", 1)])[0])

    def sequence(self, seq_num):
        return {"table": "public.sequence_value_item", "row": {
            "seq_name": "moqui.server.ArtifactHitBin", "seq_num": seq_num, "last_updated_stamp": None}}

    def test_restart_bins_and_sequence_bank_must_match(self):
        feed = "moqui.entity.feed.DataFeed"
        java = [self.bin("100000", feed, "list", 1), self.bin("100001", "other", "list", 1),
                self.bin("100101", feed, "list", 1), self.sequence(100201)]
        rust = deepcopy(java)
        self.assertTrue(self.compare(java, rust)[0])
        # A missing restart bin must fail on either side.
        self.assertFalse(self.compare(java, rust[:2] + rust[3:])[0])
        self.assertFalse(self.compare(java[:2] + java[3:], rust)[0])
        # The formerly approved Java-only sequence bank must fail independently.
        rust[3]["row"]["seq_num"] = 100101
        self.assertFalse(self.compare(java, rust)[0])
        rust[3]["row"]["seq_num"] = 100201
        java[2]["row"]["hit_count"] = 2
        self.assertFalse(self.compare(java, rust)[0])

    def test_listed_java_seed_addition_and_its_load_hits_pass(self):
        job = {"table": "public.service_job", "row": {"job_name": "clean_LlmData_daily", "last_updated_stamp": None}}
        parameters = [{"table": "public.service_job_parameter", "row": {
            "job_name": "clean_LlmData_daily", "parameter_name": name, "last_updated_stamp": None}}
            for name in ("contentDaysToKeep", "daysToKeep")]
        java = [job, *parameters, self.bin("100000", "moqui.service.job.ServiceJob", "create", 20),
                self.bin("100001", "moqui.service.job.ServiceJobParameter", "create", 12)]
        rust = [self.bin("100000", "moqui.service.job.ServiceJob", "create", 19),
                self.bin("100001", "moqui.service.job.ServiceJobParameter", "create", 10)]
        equal, report, _ = self.compare(java, rust)
        self.assertTrue(equal)
        self.assertIn("java_seed_addition", [item["kind"] for item in report["approved_differences_applied"]])
        # Rust missing only one of the listed rows is not approved.
        self.assertFalse(self.compare(java, rust + [parameters[0]])[0])

    def fts(self):
        table, field = "public.test_fts", "body"
        expr = "to_tsvector('english'::regconfig, COALESCE(body, ''::text))"
        java_schema = (f"CREATE TABLE {table} (\n    body text,\n"
                       f"    body_tsv tsvector GENERATED ALWAYS AS ({expr}) STORED\n);\n\n"
                       "--\n-- Name: fts_test_fts_body; Type: INDEX; Schema: public; Owner: moqui\n--\n\n"
                       f"CREATE INDEX fts_test_fts_body ON {table} USING gin (body_tsv);\n\n")
        rust_schema = (f"CREATE TABLE {table} (\n    body text\n);\n\n"
                       "--\n-- Name: test_fts_body_fts; Type: INDEX; Schema: public; Owner: moqui\n--\n\n"
                       f"CREATE INDEX test_fts_body_fts ON {table} USING gin "
                       "(to_tsvector('english'::regconfig, body));\n\n")
        source = {"name": field, "type": "text", "not_null": False, "default": None}
        generated = {"name": "body_tsv", "type": "tsvector", "not_null": False, "default": expr}
        java = [{"relation": table, "columns": [source, generated]},
                {"table": table, "row": {"body": "cats", "body_tsv": "'cat':1"}}]
        rust = [{"relation": table, "columns": [source]}, {"table": table, "row": {"body": "cats"}}]
        return java, rust, java_schema, rust_schema

    def test_approved_fts_storage_passes_without_hiding_raw_schema(self):
        equal, report, _ = self.compare(*self.fts())
        self.assertTrue(equal)
        self.assertFalse(report["schema_dump_equal"])
        self.assertTrue(report["schema_equal_after_approved_differences"])
        self.assertEqual(report["approved_differences_applied"][0]["kind"], "full_text_storage")

    def test_missing_index_wrong_language_and_changed_source_text_fail(self):
        java, rust, left, right = self.fts()
        self.assertFalse(self.compare(java, rust, left, right.replace("english", "simple"))[0])
        self.assertFalse(self.compare(java, rust, left, right.split("--\n-- Name:")[0])[0])
        rust[1]["row"]["body"] = "dogs"
        self.assertFalse(self.compare(java, rust, left, right)[0])


if __name__ == "__main__":
    unittest.main()
