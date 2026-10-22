from copy import deepcopy
import unittest

from test_java_regression import controller


class ApprovedTableTests(unittest.TestCase):
    def setUp(self):
        self.table = "public.auth_flow"
        self.ddl = (
            "--\n-- Name: auth_flow; Type: TABLE; Schema: public; Owner: moqui\n--\n\n"
            "CREATE TABLE public.auth_flow (id text);\n\n"
            "ALTER TABLE public.auth_flow OWNER TO moqui;\n\n"
            "--\n-- Name: auth_flow pk; Type: CONSTRAINT; Schema: public; Owner: moqui\n--\n\n"
            "ALTER TABLE ONLY public.auth_flow ADD CONSTRAINT pk PRIMARY KEY (id);\n\n"
            "--\n-- Name: flow_idx; Type: INDEX; Schema: public; Owner: moqui\n--\n\n"
            "CREATE INDEX flow_idx ON public.auth_flow USING btree (id);\n\n"
        )
        self.shared = (
            "--\n-- Name: shared; Type: TABLE; Schema: public; Owner: moqui\n--\n\n"
            "CREATE TABLE public.shared (id text);\n\n"
        )
        self.metadata = {"relation": self.table, "kind": "r", "columns": []}
        self.row = {"table": self.table, "row": {"id": "one"}}
        self.snapshots = [
            {"schema": self.shared, "records": []},
            {"schema": self.ddl + self.shared, "records": [self.metadata, self.row]},
        ]

    def test_listed_table_rows_metadata_and_owned_ddl_are_set_aside(self):
        raw = deepcopy(self.snapshots)
        snapshots = deepcopy(raw)
        applied = controller.apply_rust_only_tables(snapshots, [self.table])
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(applied, [{"kind": "rust_only_table", "table": self.table, "rows": 1}])
        self.assertEqual(self.snapshots, raw)

    def test_unlisted_tables_remain_strict(self):
        raw = deepcopy(self.snapshots)
        self.assertEqual(controller.apply_rust_only_tables(self.snapshots, []), [])
        self.assertEqual(self.snapshots, raw)

    def test_table_present_in_java_is_not_approved(self):
        for evidence in ("schema", "metadata", "row"):
            with self.subTest(evidence=evidence):
                snapshots = deepcopy(self.snapshots)
                if evidence == "schema":
                    snapshots[0]["schema"] += self.ddl
                else:
                    snapshots[0]["records"].append(self.metadata if evidence == "metadata" else self.row)
                raw = deepcopy(snapshots)
                self.assertEqual(controller.apply_rust_only_tables(snapshots, [self.table]), [])
                self.assertEqual(snapshots, raw)

    def test_missing_rust_metadata_or_ddl_is_not_approved(self):
        for evidence in ("schema", "metadata"):
            with self.subTest(evidence=evidence):
                snapshots = deepcopy(self.snapshots)
                if evidence == "schema":
                    snapshots[1]["schema"] = self.shared
                else:
                    snapshots[1]["records"].remove(self.metadata)
                raw = deepcopy(snapshots)
                self.assertEqual(controller.apply_rust_only_tables(snapshots, [self.table]), [])
                self.assertEqual(snapshots, raw)
