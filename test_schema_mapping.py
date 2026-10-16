import json
import unittest

from schema_mapping import MappingCollision, NameMapping, entity_name
import test_database_compare


class NameMappingTests(unittest.TestCase):
    def test_java_acronym_convention(self):
        self.assertEqual(entity_name("UserAccount"), "user_account")
        self.assertEqual(entity_name("userId"), "user_id")
        self.assertEqual(entity_name("OAuthURL"), "o_auth_u_r_l")
        self.assertEqual(entity_name("user_account"), "user_account")

    def test_nested_values_are_never_mapped(self):
        record = {"table": "public.UserAccount", "row": {
            "userId": "UserAccount.userId", "payload": {"userId": "unchanged"}}}
        mapped = NameMapping().record(record)
        self.assertEqual(mapped["table"], "public.user_account")
        self.assertEqual(mapped["row"]["user_id"], "UserAccount.userId")
        self.assertEqual(mapped["row"]["payload"], {"userId": "unchanged"})
        self.assertIn("userId", record["row"])

    def test_schema_names_and_sequence_names_are_not_mapped(self):
        self.assertEqual(NameMapping().table("OtherSchema.UserAccount"), "OtherSchema.user_account")
        record = {"sequence": "public.UserAccount", "state": {"last_value": 4}}
        self.assertEqual(NameMapping().record(record), record)
        self.assertEqual(NameMapping().table("public.dotted.UserAccount"), "public.dotted.UserAccount")

    def test_table_collision_rejected(self):
        mapping = NameMapping()
        mapping.table("public.UserAccount")
        with self.assertRaises(MappingCollision):
            mapping.table("public.user_account")
        self.assertEqual(mapping.table("other.user_account"), "other.user_account")

    def test_column_collision_rejected(self):
        with self.assertRaises(MappingCollision):
            NameMapping().record({"table": "public.UserAccount", "row": {"userId": 1, "user_id": 2}})

    def test_simple_ddl_and_foreign_keys(self):
        java = '''CREATE TABLE public.user_account (user_id varchar(40) NOT NULL);
ALTER TABLE ONLY public.user_account ADD CONSTRAINT pk PRIMARY KEY (user_id);
ALTER TABLE ONLY public.user_account ADD CONSTRAINT fk FOREIGN KEY (user_id)
REFERENCES public.user_account(user_id);'''
        rust = java.replace("user_account", '"UserAccount"').replace("user_id", '"userId"')
        self.assertEqual(NameMapping().schema(java), NameMapping().schema(rust))

    def test_supported_statement_order_and_comments(self):
        first = 'CREATE TABLE public.user_account (user_id text);'
        second = 'ALTER TABLE public.user_account OWNER TO moqui;'
        self.assertEqual(NameMapping().schema(first + second),
                         NameMapping().schema('-- ignored\n' + second + first))

    def test_settings_remain_ordering_barriers(self):
        first = 'CREATE TABLE public.user_account (user_id text);'
        setting = 'SET search_path = public;'
        self.assertNotEqual(NameMapping().schema(first + setting), NameMapping().schema(setting + first))

    def test_defaults_and_function_bodies_are_not_rewritten(self):
        for literal in ("'UserAccount; userId'", "E'UserAccount\\nuserId'", "$tag$UserAccount; userId$tag$"):
            sql = f'CREATE TABLE public."UserAccount" ("userId" text DEFAULT {literal});'
            normalized = NameMapping().schema(sql)
            self.assertIn(literal, normalized[0])
        function = 'CREATE FUNCTION public.f() RETURNS text AS $$SELECT \'UserAccount.userId\';$$ LANGUAGE sql;'
        self.assertIn("$$SELECT 'UserAccount.userId';$$", NameMapping().schema(function)[0])

    def test_unsupported_ddl_remains_physical(self):
        for java in (
            'CREATE VIEW public.user_account AS SELECT user_id FROM public.user_account;',
            'CREATE INDEX idx ON public.user_account (user_id);',
            'CREATE TABLE public.user_account (user_id text CHECK (user_id <> \'\'));',
            'ALTER TABLE public.user_account ALTER COLUMN user_id SET DEFAULT \'x\';',
            'COMMENT ON COLUMN public.user_account.user_id IS \'userId\';',
        ):
            rust = java.replace('user_account', '"UserAccount"').replace('user_id', '"userId"')
            self.assertNotEqual(NameMapping().schema(java), NameMapping().schema(rust))


class LogicalComparisonTests(unittest.TestCase):
    compare = test_database_compare.SnapshotTests.compare
    java_schema = 'CREATE TABLE public.user_account (user_id text NOT NULL);'
    rust_schema = 'CREATE TABLE public."UserAccount" ("userId" text NOT NULL);'

    def record(self, table, column, value):
        return json.dumps({"table": table, "row": {column: value}})

    def pair(self, left=1, right=1, **kwargs):
        return self.compare([self.record("public.user_account", "user_id", left)],
                            [self.record("public.UserAccount", "userId", right)],
                            kwargs.get("left_schema", self.java_schema),
                            kwargs.get("right_schema", self.rust_schema))

    def test_name_only_difference_passes_with_physical_evidence(self):
        equal, report, _ = self.pair()
        self.assertTrue(equal)
        self.assertFalse(report["physical_equal"])
        self.assertFalse(report["schema_dump_equal"])
        self.assertFalse(report["row_and_sequence_values_equal"])
        self.assertTrue(report["logical_comparison"]["equal"])
        self.assertTrue(report["schema_byte_differences"])
        self.assertTrue(report["record_byte_differences"])
        self.assertFalse(report["complete_logical_equivalence_verified"])

    def test_genuine_row_and_nested_json_differences_fail(self):
        for left, right in ((1, 2), (None, ""), ({"userId": 1}, {"user_id": 1})):
            equal, report, _ = self.pair(left, right)
            self.assertFalse(equal)
            self.assertFalse(report["logical_comparison"]["row_and_sequence_values_equal"])

    def test_genuine_schema_differences_fail(self):
        for schema in (self.rust_schema.replace("text", "varchar(40)"),
                       self.rust_schema.replace(" NOT NULL", ""),
                       self.rust_schema.replace("public", "other"),
                       self.rust_schema.replace(');', ', extra text);'),
                       self.rust_schema + 'CREATE TABLE public.extra (id text);'):
            self.assertFalse(self.pair(right_schema=schema)[0])

    def test_missing_source_rows_and_extra_runtime_writes_still_fail(self):
        row = self.record("public.UserAccount", "userId", "runtime-write")
        equal, report, _ = self.compare([], [row], self.java_schema, self.rust_schema)
        self.assertFalse(equal)
        self.assertTrue(report["logical_comparison"]["rust_only_records"])
        left = self.record("public.user_account", "user_id", 1)
        right = self.record("public.UserAccount", "userId", 1)
        self.assertFalse(self.compare([left], [right, right], self.java_schema, self.rust_schema)[0])

    def test_collision_fails_closed_and_retains_evidence(self):
        for schema, records in (
            (self.rust_schema + self.java_schema, []),
            (self.rust_schema, [json.dumps({"table": "public.UserAccount", "row": {"userId": 1, "user_id": 1}})]),
        ):
            equal, report, _ = self.compare([], records, self.java_schema, schema)
            self.assertFalse(equal)
            self.assertIn("rust", report["logical_comparison"]["mapping_errors"])
            self.assertTrue(report["schema_byte_differences"])

    def test_schema_defaults_and_constraint_names_remain_significant(self):
        java = self.java_schema.replace('text NOT NULL', "text DEFAULT 'UserAccount.userId'")
        rust = self.rust_schema.replace('text NOT NULL', "text DEFAULT 'user_account.user_id'")
        self.assertFalse(self.pair(left_schema=java, right_schema=rust)[0])
        java = self.java_schema + 'ALTER TABLE public.user_account ADD CONSTRAINT java_pk PRIMARY KEY (user_id);'
        rust = self.rust_schema + 'ALTER TABLE public."UserAccount" ADD CONSTRAINT rust_pk PRIMARY KEY ("userId");'
        self.assertFalse(self.pair(left_schema=java, right_schema=rust)[0])

    def test_mapped_numbers_preserve_exact_precision(self):
        left = '{"table":"public.user_account","row":{"user_id":123456789012345678901234567890.00}}'
        right = '{"table":"public.UserAccount","row":{"userId":123456789012345678901234567890}}'
        self.assertTrue(self.compare([left], [right], self.java_schema, self.rust_schema)[0])
        self.assertFalse(self.compare([left], [right.replace('7890}', '7891}')],
                                      self.java_schema, self.rust_schema)[0])

    def test_collision_across_rows_fails_without_schema(self):
        rows = [self.record('public.UserAccount', 'userId', 1),
                self.record('public.user_account', 'user_id', 2)]
        equal, report, _ = self.compare([], rows)
        self.assertFalse(equal)
        self.assertIn('rust', report['logical_comparison']['mapping_errors'])
        self.assertEqual(len(report['rust_only_records']), 2)

    def test_sequence_state_and_names_remain_significant(self):
        left = json.dumps({"sequence": "public.user_account_seq", "state": {"last_value": 1}})
        for name, value in (("public.UserAccountSeq", 1), ("public.user_account_seq", 2)):
            right = json.dumps({"sequence": name, "state": {"last_value": value}})
            self.assertFalse(self.compare([left], [right])[0])


if __name__ == "__main__":
    unittest.main()
