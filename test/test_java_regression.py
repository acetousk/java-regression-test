import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "controller", Path(__file__).resolve().parent.parent / "java-regression-test.py"
)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(controller, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        for checkout in controller.REPOSITORIES:
            conf = self.root / checkout / "runtime" / "conf"
            conf.mkdir(parents=True)
            (conf / "MoquiDevConf.xml").write_text("<moqui-conf/>")

    def fake_build(self, command, *, cwd, env, check):
        artifact = cwd / ("moqui.war" if command[0] == "./gradlew" else "target/debug/moqui")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"test build artifact")
        artifact.chmod(0o755)

    def test_builds_each_checkout_with_private_runtime(self):
        with patch.object(controller.subprocess, "run", side_effect=self.fake_build) as run:
            controller.build_engines("/test/jdk")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ["./gradlew", "--no-daemon", "clean", "build"])
        self.assertEqual(run.call_args_list[1].args[0], ["cargo", "build", "--locked", "-p", "moqui"])
        self.assertEqual(run.call_args_list[0].kwargs["cwd"], self.root / "moqui-framework")
        self.assertEqual(run.call_args_list[1].kwargs["cwd"], self.root / "mr-moqui")
        self.assertEqual(run.call_args_list[0].kwargs["env"]["JAVA_HOME"], "/test/jdk")
        manifest = json.loads((self.root / ".runs/build.json").read_text())
        self.assertNotEqual(manifest["java"]["runtime"], manifest["rust"]["runtime"])
        self.assertEqual(len(manifest["java"]["sha256"]), 64)

    def test_explicit_worktrees_are_used_without_replacing_defaults(self):
        from types import SimpleNamespace
        directories = controller.engine_directories(SimpleNamespace(java_checkout=self.root / "java-worktree",
                                                                   rust_checkout=self.root / "rust-worktree"))
        for directory in directories.values():
            (directory / "runtime/conf").mkdir(parents=True)
            (directory / "runtime/conf/MoquiDevConf.xml").write_text("<moqui-conf/>")
        with patch.object(controller.subprocess, "run", side_effect=self.fake_build) as run:
            controller.build_engines(directories=directories)
        self.assertEqual([call.kwargs["cwd"] for call in run.call_args_list], list(directories.values()))
        self.assertEqual(controller.engine_directories()["java"], self.root / "moqui-framework")

    def test_external_rust_target_directory_is_respected(self):
        with patch.dict(controller.os.environ, {"CARGO_TARGET_DIR": "/test/rust-cache"}):
            self.assertEqual(controller.rust_artifact(self.root / "rust"), Path("/test/rust-cache/debug/moqui"))
        with patch.dict(controller.os.environ, {"CARGO_TARGET_DIR": "cache"}):
            self.assertEqual(controller.rust_artifact(self.root / "rust"), self.root / "rust/cache/debug/moqui")

    def test_missing_artifact_fails(self):
        with patch.object(controller.subprocess, "run"), self.assertRaises(SystemExit):
            controller.build_engines()
        self.assertFalse((self.root / ".runs/build.json").exists())

    def test_failed_build_removes_previous_success_manifest(self):
        manifest = self.root / ".runs/build.json"
        manifest.parent.mkdir()
        manifest.write_text("{}")
        with patch.object(controller.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "build")):
            with self.assertRaises(subprocess.CalledProcessError):
                controller.build_engines()
        self.assertFalse(manifest.exists())


class SnapshotCaptureTests(unittest.TestCase):
    def test_capture_uses_read_only_transaction_and_bounded_schema_lock_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "snapshot.json"
            with patch.object(controller.subprocess, "check_output", side_effect=["schema", '{"table":"t","row":{}}\n']) as run:
                controller.capture_snapshot("isolated-test-container", destination)
            self.assertIn("--lock-wait-timeout=5000", run.call_args_list[0].args[0])
            self.assertIn("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", run.call_args.kwargs["input"])
            self.assertIn("SET LOCAL statement_timeout = '10s'", run.call_args.kwargs["input"])
            self.assertTrue(all(call.kwargs["timeout"] == 60 for call in run.call_args_list))
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(destination.read_text())["schema"], "schema")


class StartupTests(unittest.TestCase):
    def test_demo_configuration_preserves_settings_and_overrides_database(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dev.xml"
            destination = Path(directory) / "demo.xml"
            source.write_text('<moqui-conf><default-property name="entity_ds_db_conf" value="mysql8"/>'
                              '<cache-list warm-on-start="false"/></moqui-conf>')
            controller.demo_conf(source, destination, 55432, "test-only-password", 8081, "test-only-key")
            root = controller.ET.parse(destination).getroot()
            values = {n.get("name"): n.get("value") for n in root.findall("default-property")}
            self.assertEqual(values["entity_ds_db_conf"], "postgres")
            self.assertEqual(values["entity_ds_port"], "55432")
            self.assertEqual(values["entity_empty_db_load"], "all")
            self.assertEqual(values["webapp_http_port"], "8081")
            self.assertEqual(values["entity_ds_crypt_pass"], "test-only-key")
            self.assertIsNotNone(root.find("cache-list"))
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_early_engine_exit_fails_readiness(self):
        from unittest.mock import Mock
        process = Mock(pid=123)
        process.poll.return_value = 1
        with self.assertRaises(RuntimeError):
            controller.wait_for_ports({"java": process}, {"java": 8080}, 1)

    def test_readiness_does_not_signal_processes(self):
        from unittest.mock import Mock
        processes = {"java": Mock(pid=123), "rust": Mock(pid=456)}
        for process in processes.values():
            process.poll.return_value = None
        with patch.object(controller.socket, "create_connection"), patch.object(controller.os, "killpg") as kill:
            controller.wait_for_ports(processes, {"java": 8080, "rust": 8081}, 1)
        kill.assert_not_called()

    def test_readiness_waits_for_completed_initialization_not_only_seed_load(self):
        from unittest.mock import Mock
        process = Mock(pid=123)
        process.poll.return_value = None
        log = Mock()
        log.read_text.side_effect = [
            "Loaded records (with types from empty-db-load: all)",
            "Loaded records (with types from empty-db-load: all)\nMoqui Framework initialized in 1 seconds",
            "Loaded records (with types from empty-db-load: all)\nMoqui Framework initialized in 1 seconds\n"
            "Started oejs.Server@123{STARTING}",
        ]
        with patch.object(controller.socket, "create_connection") as connect, \
                patch.object(controller.time, "sleep") as sleep:
            controller.wait_for_ports({"java": process}, {"java": 8080}, 10, {"java": log})
        self.assertEqual(sleep.call_count, 2)
        connect.assert_called_once()

    def test_shutdown_signals_both_before_waiting_and_verifies_new_flush_evidence(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            logs = {name: Path(directory) / name for name in ("java", "rust")}
            processes = {name: Mock(pid=pid, returncode=code)
                         for name, pid, code in (("java", 123, 143), ("rust", 456, 0))}
            events = []
            for name, process in processes.items():
                logs[name].write_text("startup\n")
                process.poll.return_value = None
                process.wait.side_effect = lambda **kwargs: events.append("wait")
            def signal_group(pid, signal):
                events.append(pid)
                name = "java" if pid == 123 else "rust"
                with logs[name].open("a") as log:
                    log.write("ArtifactHitBins stored\n")
                    if name == "java":
                        log.write("Moqui ExecutionContextFactory Destroyed\n")
            with patch.object(controller.os, "killpg", side_effect=signal_group):
                report = controller.stop_engines(processes, logs, 120)
            self.assertEqual(events[:2], [123, 456])
            self.assertTrue(all(not result["errors"] for result in report.values()))

    def test_shutdown_does_not_accept_factory_restart_flush_as_final_shutdown(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "java.log"
            log.write_text("ArtifactHitBins stored\nMoqui ExecutionContextFactory Destroyed\n")
            process = Mock(pid=123, returncode=143)
            process.poll.return_value = None
            with patch.object(controller.os, "killpg"):
                result = controller.stop_engines({"java": process}, {"java": log}, 120)["java"]
            self.assertTrue(result["errors"])
            self.assertEqual(len(result["missing_shutdown_markers"]), 2)

    def test_forced_shutdown_fails_verification(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "rust.log"
            log.write_text("")
            process = Mock(pid=123, returncode=-9)
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired("rust", 120), None]
            with patch.object(controller.os, "killpg") as kill:
                result = controller.stop_engines({"rust": process}, {"rust": log}, 120)["rust"]
            self.assertTrue(result["forced_kill"])
            self.assertTrue(result["errors"])
            self.assertEqual(kill.call_args_list[-1].args, (123, controller.signal.SIGKILL))

    def test_readiness_timeout_fails(self):
        from unittest.mock import Mock
        process = Mock(pid=123)
        process.poll.return_value = None
        with patch.object(controller.socket, "create_connection", side_effect=OSError), \
                patch.object(controller.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                controller.wait_for_ports({"java": process}, {"java": 8080}, 1)


class CdcTests(unittest.TestCase):
    def test_read_cdc_groups_rows_per_committed_transaction(self):
        rows = ["BEGIN", "table public.a: INSERT: id[integer]:1 note[text]:'two\nlines'", "COMMIT",
                "BEGIN", "COMMIT"]
        result = subprocess.CompletedProcess([], 0, stdout="\0".join(rows) + "\n")
        with patch.object(controller.subprocess, "run", return_value=result):
            self.assertEqual(controller.read_cdc("container"),
                             [["table public.a: INSERT: id[integer]:1 note[text]:'two\nlines'"], []])

    def test_read_cdc_rejects_a_partial_transaction(self):
        result = subprocess.CompletedProcess([], 0, stdout="BEGIN\0table public.a: INSERT: id[integer]:1")
        with patch.object(controller.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "inside a transaction"):
                controller.read_cdc("container")

    def test_rust_only_statistics_exemption_uses_existing_snapshot_approval(self):
        from test.test_approvals import row_change
        approved = {"theme_resources": [], "full_text_indexes": [],
                    "rust_only_statistics": {"artifact_sub_types": ["update-probe"]},
                    "transaction_exemptions": [
                        {"engine": "rust", "when": {"approved_difference": "rust_only_statistics"}}]}
        row = {"hit_bin_id": "100091", "artifact_type": "AT_ENTITY", "artifact_sub_type": "update-probe",
               "artifact_name": "moqui.basic.Enumeration", "hit_count": 219}
        shared = {**row, "hit_bin_id": "100090", "artifact_sub_type": "create"}
        record = {"table": "public.artifact_hit_bin", "row": row}
        records = [[{"table": "public.artifact_hit_bin", "row": shared}],
                   [{"table": "public.artifact_hit_bin", "row": shared}, record]]
        snapshots = lambda: [{"schema": "", "records": [json.dumps(item) for item in side]} for side in records]
        engine = controller.ApprovalEngine(approved, lambda event, kind:
            controller.approved_statistics_change(event, kind, snapshots, approved))
        transaction = lambda: row_change("public.artifact_hit_bin", row)
        self.assertTrue(engine.exempt_transaction("rust", transaction()))
        sequence = row_change("public.sequence_value_item", {"seq_name": "moqui.server.ArtifactHitBin",
                              "seq_num": 100201}, "update")
        self.assertFalse(engine.exempt_transaction("rust", sequence))
        self.assertFalse(engine.exempt_transaction("rust", transaction() + sequence))
        self.assertFalse(engine.exempt_transaction("java", transaction()))
        self.assertFalse(engine.exempt_transaction("rust", row_change("public.artifact_hit_bin", row, "update")))
        self.assertFalse(engine.exempt_transaction("rust", row_change("public.artifact_hit_bin", shared)))
        records[0].append(record)
        self.assertFalse(engine.exempt_transaction("rust", transaction()))
        records[0].pop()
        records[1].append(record)
        self.assertFalse(engine.exempt_transaction("rust", transaction()))
        records[1].pop()
        row["hit_bin_id"] = "100089"
        self.assertFalse(engine.exempt_transaction("rust", transaction()))
        row["hit_bin_id"] = "100091"
        records[1].remove(record)
        self.assertFalse(engine.exempt_transaction("rust", transaction()))
        records[1].append(record)
        del approved["rust_only_statistics"]
        self.assertFalse(engine.exempt_transaction("rust", transaction()))

    def test_seed_statistics_exemption_requires_complete_database_evidence(self):
        from test.test_approvals import row_change
        approved = {"theme_resources": [], "full_text_indexes": [], "rust_seed_additions": [
            {"table": "public.system_message_remote", "entity": "moqui.service.message.SystemMessageRemote",
             "key": ["system_message_remote_id"], "values": [["ExampleSftpLocal"]]}],
            "transaction_exemptions": [{"engine": "rust", "when": {"approved_difference": "seed_statistics"}}]}
        seed = {"table": "public.system_message_remote", "row": {"system_message_remote_id": "ExampleSftpLocal"}}
        row = {"hit_bin_id": "100004", "artifact_type": "AT_ENTITY", "artifact_sub_type": "create",
               "artifact_name": "moqui.service.message.SystemMessageRemote", "hit_count": 1}
        bin_record = {"table": "public.artifact_hit_bin", "row": row}
        records = [[], [seed, bin_record]]
        snapshots = lambda: [{"schema": "", "records": [json.dumps(item) for item in side]} for side in records]
        engine = controller.ApprovalEngine(approved, lambda event, kind:
            controller.approved_statistics_change(event, kind, snapshots, approved))
        def covered(kind="insert"):
            return engine.exempt_transaction("rust", row_change("public.artifact_hit_bin", row, kind))
        self.assertTrue(covered())
        self.assertFalse(covered("update"))
        self.assertFalse(engine.exempt_transaction("java", row_change("public.artifact_hit_bin", row)))
        self.assertFalse(controller.ApprovalEngine(approved).exempt_transaction(
            "rust", row_change("public.artifact_hit_bin", row)))
        row["hit_count"] = 2
        self.assertFalse(covered())
        row["hit_count"] = 1
        records[1].append(bin_record)
        self.assertFalse(covered())
        records[1].pop()
        records[1].remove(seed)
        self.assertFalse(covered())
        records[1].append(seed)
        records[0].append(seed)
        self.assertFalse(covered())
        records[0][:] = [bin_record]
        self.assertFalse(covered())
        records[0].clear()
        approved["transaction_exemptions"].clear()
        self.assertFalse(controller.ApprovalEngine(approved).exempt_transaction(
            "rust", row_change("public.artifact_hit_bin", row)))


if __name__ == "__main__":
    unittest.main()
