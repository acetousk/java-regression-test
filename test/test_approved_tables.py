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
    def test_final_owned_block_keeps_dump_footer(self):
        footer = '--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict MoquiRegression\n\n'
        snapshots = deepcopy(self.snapshots)
        snapshots[0]['schema'] = self.shared + footer
        snapshots[1]['schema'] = self.shared + self.ddl + footer
        self.assertEqual(len(controller.apply_rust_only_tables(snapshots, [self.table])), 1)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertTrue(snapshots[1]['schema'].endswith(footer))

    def test_unheaded_sql_or_unsupported_syntax_rejects_exception(self):
        additions = [
            'ALTER TABLE public.shared ADD COLUMN extra text;\n',
            'GRANT ALL ON TABLE public.shared TO PUBLIC;\n',
            'DROP TABLE public.shared;\n',
            '-- unexpected comment\n',
            'DO $$ BEGIN PERFORM 1; END $$;\n',
            "ALTER TABLE public.auth_flow OWNER TO other_role; SELECT 'hidden';\n",
        ]
        for addition in additions:
            with self.subTest(addition=addition):
                snapshots = deepcopy(self.snapshots)
                snapshots[1]['schema'] = self.shared + self.ddl + addition
                before = deepcopy(snapshots)
                self.assertEqual(controller.apply_rust_only_tables(snapshots, [self.table]), [])
                self.assertEqual(snapshots, before)

    def test_quoted_default_semicolons_are_not_statement_boundaries(self):
        snapshots = deepcopy(self.snapshots)
        snapshots[1]['schema'] = snapshots[1]['schema'].replace(
            'CREATE TABLE public.auth_flow (id text);',
            "CREATE TABLE public.auth_flow (id text DEFAULT 'one;\ntwo''s;value');")
        self.assertEqual(len(controller.apply_rust_only_tables(snapshots, [self.table])), 1)
        self.assertEqual(snapshots[0], snapshots[1])

    def test_duplicate_create_and_escape_strings_reject_exception(self):
        for create in ("CREATE TABLE public.auth_flow (id text DEFAULT E'one\\\\two');",
                       'CREATE TABLE public.auth_flow (id text); CREATE TABLE public.auth_flow (id text);'):
            snapshots = deepcopy(self.snapshots)
            snapshots[1]['schema'] = snapshots[1]['schema'].replace('CREATE TABLE public.auth_flow (id text);', create)
            before = deepcopy(snapshots)
            self.assertEqual(controller.apply_rust_only_tables(snapshots, [self.table]), [])
            self.assertEqual(snapshots, before)

    def test_quoted_index_name_keeps_exact_owned_table_boundary(self):
        snapshots = deepcopy(self.snapshots)
        snapshots[1]['schema'] = snapshots[1]['schema'].replace('flow_idx', '"flow.by_id"')
        self.assertEqual(len(controller.apply_rust_only_tables(snapshots, [self.table])), 1)
        self.assertEqual(snapshots[0], snapshots[1])
