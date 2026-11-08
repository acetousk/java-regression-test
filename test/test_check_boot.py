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
