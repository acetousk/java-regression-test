from copy import deepcopy
import json
from pathlib import Path
import unittest

from approvals import ApprovalEngine
from incremental import EVENT_PREFIX


def marker(**event):
    return EVENT_PREFIX + "'" + json.dumps(event).replace("'", "''") + "'"


def row_change(table, row, kind="insert"):
    return [f"table {table}: {kind.upper()}: id[integer]:1",
            marker(kind=kind, table=table, new=json.dumps(row), old=None)]


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.rules = json.loads((Path(__file__).resolve().parent.parent / "approved-differences.json").read_text())
        self.engine = ApprovalEngine(self.rules)

    def test_policy_is_json_only_and_engine_neutral(self):
        rules = {"allowed": ["custom.arbitrary"], "transaction_exemptions": [
            {"engine": "another-engine", "when": {"path": "table", "in": {"ref": "allowed"}}}]}
        engine = ApprovalEngine(rules)
        changes = row_change("custom.arbitrary", {"id": 1})
        self.assertTrue(engine.exempt_transaction("another-engine", changes))
        self.assertFalse(engine.exempt_transaction("rust", changes))
        self.assertFalse(ApprovalEngine({}).exempt_transaction("another-engine", changes))
        rules = deepcopy(rules)
        rules["allowed"] = []
        self.assertFalse(ApprovalEngine(rules).exempt_transaction("another-engine", changes))

    def test_all_changes_must_be_approved(self):
        approved = row_change("search.document_index", {"document_id": "x"})
        self.assertTrue(self.engine.exempt_transaction("rust", approved))
        self.assertFalse(self.engine.exempt_transaction("java", approved))
        shared = row_change("public.enumeration", {"enum_id": "shared"})
        self.assertFalse(self.engine.exempt_transaction("rust", approved + shared))
        self.assertFalse(self.engine.exempt_transaction("rust", []))

    def test_seed_keys_and_insert_only_come_from_json(self):
        self.rules["rust_seed_additions"] = [{"table": "public.service_job", "key": ["job_name"],
                                               "values": [["Rust's_job"]]}]
        engine = ApprovalEngine(self.rules)
        self.assertTrue(engine.exempt_transaction("rust", row_change("public.service_job", {"job_name": "Rust's_job"})))
        self.assertFalse(engine.exempt_transaction("rust", row_change("public.service_job", {"job_name": "other"})))
        self.assertFalse(engine.exempt_transaction("rust", row_change("public.service_job", {"job_name": "Rust's_job"}, "update")))

    def test_ddl_needs_identified_approved_tables(self):
        for tag in ("CREATE TABLE", "CREATE INDEX"):
            def approved(**fields):
                return self.engine.exempt_transaction("rust", [marker(kind="schema", tag=tag, **fields)])
            self.assertTrue(approved(tables=["search.moqui_logs"], table_only=True))
            self.assertFalse(approved(tables=["public.enumeration"], table_only=True))
            self.assertFalse(approved(tables=["search.moqui_logs", "public.enumeration"], table_only=True))
            self.assertFalse(approved(tables=["search.moqui_logs"], table_only=False))
            self.assertFalse(approved(tables=[], table_only=True))
            self.assertFalse(approved())
        self.assertTrue(self.engine.exempt_transaction("rust", [
            marker(kind="schema", tag="DROP TABLE", tables=None, table_only=True)]))
        self.assertFalse(self.engine.exempt_transaction("rust", [
            marker(kind="schema", tag="DROP", dropped=["search.moqui_logs"])]))
        self.assertFalse(self.engine.exempt_transaction("rust", [
            marker(kind="schema", tag="CREATE SEQUENCE", tables=None, table_only=False)]))

    def test_no_ddl_tag_or_event_kind_is_implicitly_approved(self):
        event = marker(kind="schema", tag="CREATE INDEX", table_only=True, tables=["search.moqui_logs"])
        self.rules["transaction_exemptions"] = []
        self.assertFalse(ApprovalEngine(self.rules).exempt_transaction("rust", [event]))
        self.rules["transaction_exemptions"] = [{"engine": "custom", "when": {
            "all": [{"path": "kind", "equals": "schema"},
                    {"path": "tag", "equals": "CUSTOM DDL"},
                    {"path": "tables", "all_in": {"ref": "rust_only_tables"}}]}}]
        engine = ApprovalEngine(self.rules)
        self.assertFalse(engine.exempt_transaction("custom", [event]))
        self.assertTrue(engine.exempt_transaction("custom", [
            marker(kind="schema", tag="CUSTOM DDL", tables=["search.moqui_logs"])]))

    def test_capture_gaps_cannot_be_approved(self):
        with self.assertRaises(ValueError):
            self.engine.exempt_transaction("rust", ["table search.moqui_logs: INSERT: id[integer]:1"])

    def test_unknown_operators_and_references_fail_closed(self):
        for condition in ({"path": "table", "regex": ".*"},
                          {"path": "table", "in": {"ref": "missing"}}, {"all": []}):
            with self.assertRaises(ValueError):
                ApprovalEngine({"transaction_exemptions": [{"engine": "rust", "when": condition}]})

    def test_login_password_upgrade_changes_only_password_columns(self):
        old = {"user_id": "EX_JOHN_DOE", "current_password": "16ac58bb", "password_salt": None,
               "password_hash_type": "SHA", "password_base64": None, "disabled": "N",
               "last_updated_stamp": "2026-10-22T22:26:54.719"}
        new = {**old, "current_password": "$argon2id$v=19$x", "password_salt": "",
               "password_hash_type": "argon2", "password_base64": "N",
               "last_updated_stamp": "2026-10-22T22:26:54.722"}

        def update(old, new, table="public.user_account"):
            return [f"table {table}: UPDATE: user_id[character varying]:'EX_JOHN_DOE'",
                    marker(kind="update", table=table, old=json.dumps(old), new=json.dumps(new))]
        self.assertTrue(self.engine.exempt_transaction("rust", update(old, new)))
        self.assertFalse(self.engine.exempt_transaction("java", update(old, new)))
        self.assertFalse(self.engine.exempt_transaction("rust", update(old, new, "public.other")))
        self.assertFalse(self.engine.exempt_transaction("rust", update(old, {**new, "disabled": "Y"})))
        self.assertFalse(self.engine.exempt_transaction("rust", update(old, {**new, "password_hash_type": "SHA"})))
        self.assertFalse(self.engine.exempt_transaction("rust", update({**old, "password_hash_type": "argon2"}, new)))
        extra = {**new, "unexpected_column": "x"}
        self.assertFalse(self.engine.exempt_transaction("rust", update(old, extra)))
        with self.assertRaises(ValueError):
            ApprovalEngine({"transaction_exemptions": [{"engine": "rust", "when": {"changed_fields": []}}]})
