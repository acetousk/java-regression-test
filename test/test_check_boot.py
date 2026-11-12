import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("check_boot", Path(__file__).resolve().parents[1] / "check_boot.py")
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


def response(body, status=200):
    stream = io.BytesIO(body)
    stream.status = status
    stream.url = "http://127.0.0.1/Login"
    return stream


class BootGateTests(unittest.TestCase):
    def test_runtime_change_fails_even_with_healthy_http_and_shutdown(self):
        for changed in ('none', 'runtime', 'artifact', 'launch'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                checkouts = {side: root / side for side in ('java', 'rust')}
                for checkout in checkouts.values():
                    for name in ('base-component', 'component', 'conf'):
                        (checkout / 'runtime' / name).mkdir(parents=True)
                    (checkout / 'runtime/conf/test.xml').write_text('<conf/>')
                (checkouts['java'] / 'moqui.war').write_bytes(b'java')
                (root / 'binary').write_bytes(b'rust')
                output = root / 'result'
                def run(args, *, evidence_dir, readiness_check):
                    # The real controller creates a fresh directory and rejects an existing one.
                    self.assertFalse(evidence_dir.exists())
                    evidence_dir.mkdir(parents=True)
                    self.assertEqual(args.boot_artifacts['rust'].read_bytes(), b'rust')
                    readiness_check({})
                    boot.write_json(evidence_dir / 'shutdown.json', {
                        side: {'errors': [], 'forced_kill': False} for side in checkouts})
                    boot.write_json(evidence_dir / 'verification.json', {
                        'servers_started': True, 'shutdown_verified': True})
                    if changed == 'runtime':
                        (checkouts['java'] / 'runtime/conf/test.xml').write_text('<changed/>')
                    elif changed == 'artifact':
                        (root / 'binary').write_bytes(b'replacement')
                        self.assertEqual(args.boot_artifacts['rust'].read_bytes(), b'rust')
                    elif changed == 'launch':
                        args.boot_artifacts['rust'].chmod(0o600)
                        args.boot_artifacts['rust'].write_bytes(b'replacement')
                with patch.object(boot, 'ROOT', root), \
                        patch.object(boot.controller, 'engine_directories', return_value=checkouts), \
                        patch.object(boot, 'artifact_evidence', side_effect=lambda _, artifact: {
                            'artifact_sha256': boot.hashlib.sha256(artifact.read_bytes()).hexdigest()}), \
                        patch.object(boot.controller, 'rust_artifact', return_value=root/'binary'), \
                        patch.object(boot.controller, 'boot_and_stop', side_effect=run), \
                        patch.object(boot, 'http_readiness', side_effect=lambda _, gate: gate.update(http_ready=True)):
                    self.assertEqual(boot.check(SimpleNamespace(evidence_dir=output)), int(changed != 'none'))
                gate = json.loads((output / 'gate.json').read_text())
                self.assertEqual(gate['passed'], changed == 'none')
                self.assertEqual(bool(gate['runtime_errors']), changed == 'runtime')
                self.assertEqual(bool(gate['artifact_errors']), changed in ('artifact', 'launch'))
                for side in checkouts:
                    manifest = json.loads(Path(gate[side]['runtime_source_manifest']).read_text())
                    self.assertEqual(gate[side]['runtime_source_sha256'], boot.manifest_digest(manifest))

    def test_success_requires_health_and_pages_from_both_engines(self):
        gate = {"java": {}, "rust": {}}
        replies = [response(b'{"JavaRuntime": {}}'), response(b"<html>Java</html>"),
                   response(b'{"ready": true}'), response(b"<html>Rust</html>")]
        with patch.object(boot, "urlopen", side_effect=replies):
            boot.http_readiness({"java": 18080, "rust": 18081}, gate)
        self.assertTrue(gate["http_ready"])
        self.assertEqual(gate["rust"]["http_readiness"]["body"], {"ready": True})

    def test_listening_rust_with_unhealthy_or_wrong_response_fails(self):
        for payload in ({"ready": False}, {"ready": "true"}, [], {"error": "startup failed"}):
            with self.subTest(payload=payload):
                gate = {"java": {}, "rust": {}}
                replies = [response(b'{"JavaRuntime": {}}'), response(b"<html>Java</html>"),
                           response(json.dumps(payload).encode())]
                with patch.object(boot, "urlopen", side_effect=replies), self.assertRaises(RuntimeError):
                    boot.http_readiness({"java": 18080, "rust": 18081}, gate)
                self.assertFalse(gate.get("http_ready", False))

    def test_empty_or_error_page_does_not_pass_health_gate(self):
        for status, content in ((200, b""), (503, b"unavailable")):
            with self.subTest(status=status):
                replies = [response(b'{"JavaRuntime": {}}'), response(content, status)]
                with patch.object(boot, "urlopen", side_effect=replies), self.assertRaises(RuntimeError):
                    boot.http_readiness({"java": 18080}, {"java": {}})

    def test_busy_run_lock_preserves_manifest_and_existing_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".runs"
            runs.mkdir()
            manifest = runs / "build.json"
            manifest.write_text("existing manifest")
            gate = runs / "gate.json"
            gate.write_text("existing gate")
            with (runs / "run.lock").open("a") as lock:
                boot.fcntl.flock(lock, boot.fcntl.LOCK_EX | boot.fcntl.LOCK_NB)
                with patch.object(boot, "ROOT", root), self.assertRaisesRegex(RuntimeError, "already active"):
                    boot.check(SimpleNamespace(evidence_dir=runs))
            self.assertEqual(manifest.read_text(), "existing manifest")
            self.assertEqual(gate.read_text(), "existing gate")
