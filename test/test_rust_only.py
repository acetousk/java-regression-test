import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_java_regression import controller

filter_snapshots = controller.filter_snapshots
source_records = controller.source_records


MANIFEST = controller.RUST_ONLY_SOURCES


class RustOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = copy.deepcopy(MANIFEST)
        # Small source-tree fixtures, no initialized submodules or private runtime.
        basic = '<entities>'
        for name, fields in (("Enumeration", ("enumId", "enumTypeId", "description", "optionValue")),
                             ("EnumerationType", ("enumTypeId", "description"))):
            basic += f'<entity entity-name="{name}" package="moqui.basic">'
            basic += ''.join(f'<field name="{f}" is-pk="{str(i == 0).lower()}"/>'
                             for i, f in enumerate(fields)) + '</entity>'
        self.put(self.manifest["metadata"][0], basic + '</entities>')
        self.put(self.manifest["metadata"][1], '''<entities>
          <entity entity-name="ServiceJob" package="moqui.service.job">
            <field name="jobName" is-pk="true"/><field name="description"/>
            <relationship type="many" related="moqui.service.job.ServiceJobParameter" short-alias="parameters"/>
          </entity>
          <entity entity-name="ServiceJobParameter" package="moqui.service.job">
            <field name="jobName" is-pk="true"/><field name="parameterName" is-pk="true"/>
            <field name="parameterValue"/>
          </entity></entities>''')
        self.put(self.manifest["sources"][0]["path"], '''<entity-facade-xml>
          <moqui.service.job.ServiceJob jobName="Sftp" description="demo">
            <parameters parameterName="a" parameterValue="one"/>
            <parameters parameterName="b" parameterValue="two"/>
          </moqui.service.job.ServiceJob>
          <moqui.service.job.ServiceJob jobName="Other1"/>
          <moqui.service.job.ServiceJob jobName="Other2"/>
        </entity-facade-xml>''')
        security = ET.Element("entities")
        seed = ET.SubElement(security, "seed-data")
        for group, count in zip(self.manifest["sources"][1]["groups"], (3, 13, 4, 13)):
            ET.SubElement(seed, "moqui.basic.EnumerationType", enumTypeId=group, description=group)
            for i in range(count):
                enum_id = "OctGoogle" if i == 0 and group in ("OauthClientType", "OidcClientType") else f"{group}{i}"
                ET.SubElement(seed, "moqui.basic.Enumeration", enumId=enum_id, enumTypeId=group,
                              description=f"{group} value {i}")
        # An unrelated inline seed must never become an exclusion.
        ET.SubElement(seed, "moqui.basic.Enumeration", enumId="shared", enumTypeId="Shared")
        self.put(self.manifest["sources"][1]["path"], ET.tostring(security, encoding="unicode"))
        self.seeds, _ = source_records(self.manifest, self.root)

    def put(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def row(self, seed=None):
        seed = seed or self.seeds[0]
        return {"table": seed["table"], "row": {**seed["expected"], "lastUpdatedStamp": "runtime-time"}}

    def snapshot(self, *records):
        return {"schema": "unchanged schema", "records": [json.dumps(r) for r in records]}

    def filter(self, java, rust):
        return filter_snapshots(java, rust, MANIFEST, self.root)

    def test_exact_source_counts_pk_and_nested_attribution(self):
        self.assertEqual(len(self.seeds), 42)  # 5 SFTP + 37 occurrences (36 distinct auth PKs).
        nested = self.seeds[1]
        self.assertEqual(nested["pk"], {"jobName": "Sftp", "parameterName": "a"})
        java, rust = self.snapshot(), self.snapshot(self.row(nested))
        original = copy.deepcopy(rust)
        _, filtered, audit = self.filter(java, rust)
        self.assertEqual(filtered["records"], [])
        self.assertEqual(rust, original)
        self.assertEqual(filtered["schema"], rust["schema"])
        excluded = audit["excluded"][0]
        self.assertEqual(excluded["source"], self.manifest["sources"][0]["path"])
        self.assertEqual(excluded["record"], original["records"][0])
        self.assertIn("/parameters[1]", excluded["locator"])
        self.assertEqual(len(audit["source_sha256"]), 4)

    def test_edits_extra_fields_and_unset_values_stay_visible(self):
        for field, value in (("description", "edited"), ("extra", "new")):
            row = self.row()
            row["row"][field] = value
            rust = self.snapshot(row)
            self.assertEqual(self.filter(self.snapshot(), rust)[1], rust)
        enum = next(s for s in self.seeds if s["entity"] == "moqui.basic.Enumeration")
        row = self.row(enum)
        row["row"]["optionValue"] = "runtime value"
        self.assertEqual(self.filter(self.snapshot(), self.snapshot(row))[2]["excluded"], [])

    def test_shared_pk_and_duplicates_are_not_hidden(self):
        row = self.row()
        for java, rust, reason in ((self.snapshot(row), self.snapshot(row), "PK present in Java"),
                                   (self.snapshot(), self.snapshot(row, row), "duplicate Rust PK")):
            _, filtered, audit = self.filter(java, rust)
            self.assertEqual(filtered, rust)
            self.assertEqual(audit["retained_candidates"][0]["reason"], reason)

    def test_java_physical_pk_collision_guard_without_schema_mapping(self):
        java = self.snapshot({"table": "public.service_job", "row": {"job_name": "Sftp", "description": "different"}})
        rust = self.snapshot(self.row())
        _, filtered, audit = self.filter(java, rust)
        self.assertEqual(filtered, rust)
        self.assertEqual(audit["retained_candidates"][0]["reason"], "PK present in Java")

    def test_auth_source_collision_and_unrelated_enum_preserved(self):
        google = next(s for s in self.seeds if s["pk"].get("enumId") == "OctGoogle")
        unrelated = {"table": "public.Enumeration", "row": {"enumId": "shared", "enumTypeId": "Shared"}}
        rust = self.snapshot(self.row(google), unrelated)
        _, filtered, audit = self.filter(self.snapshot(), rust)
        self.assertEqual(filtered, rust)
        self.assertEqual(audit["retained_candidates"][0]["reason"], "source PK collision")

    def test_only_precise_operational_tables_not_business_hits_cluster_or_sequences(self):
        operational = [{"table": e["table"], "row": {"id": 1}} for e in self.manifest["operational"]]
        retained = [{"table": table, "row": {"id": 1}} for table in
                    ("search.business_documents", "public.moqui_logs", "search.moqui_logs_extra",
                     "public.ArtifactHit", "public.ClusterNode", "public.Theme")]
        retained.append({"sequence": "search.moqui_logs", "state": {"last_value": 1}})
        java = self.snapshot(*operational)
        _, filtered, audit = self.filter(java, self.snapshot(*operational, *retained))
        self.assertEqual(filtered["records"], self.snapshot(*retained)["records"])
        self.assertEqual(audit["excluded_counts"], {"operational": 3})
        self.assertEqual(java["records"], self.snapshot(*operational)["records"])

    def test_missing_sources_and_drift_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "source unavailable.*source_root"):
            source_records(self.manifest, self.root / "missing")
        self.put(self.manifest["sources"][0]["path"], '<entity-facade-xml/>')
        with self.assertRaisesRegex(ValueError, "record count changed"):
            source_records(self.manifest, self.root)

    def test_comparator_opt_in_raw_evidence_and_schema_differences(self):
        left, right = self.root / "java.json", self.root / "rust.json"
        left.write_text(json.dumps(self.snapshot()))
        right.write_text(json.dumps(self.snapshot(self.row())))
        raw = right.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(controller.snapshot_compare(left, right, self.root))
            self.assertTrue(controller.snapshot_compare(left, right, self.root,
                            rust_only_manifest=MANIFEST, source_root=self.root))
            self.assertEqual(right.read_bytes(), raw)
            changed = self.snapshot(self.row())
            changed["schema"] = "operational DDL still visible"
            right.write_text(json.dumps(changed))
            self.assertFalse(controller.snapshot_compare(left, right, self.root,
                             rust_only_manifest=MANIFEST, source_root=self.root))
        right.write_bytes(raw)
        self.assertEqual(right.read_bytes(), raw)
        report = json.loads((self.root / "comparison.json").read_text())
        self.assertEqual(report["rust_only_exclusions"]["classification"], "Rust only")
        self.assertTrue(report["schema_byte_differences"])


if __name__ == "__main__":
    unittest.main()
