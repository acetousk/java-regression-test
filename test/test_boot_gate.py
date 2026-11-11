import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from boot_gate import require_matching_boot_gate


class GateTests(unittest.TestCase):
    def test_gate_must_match_both_artifacts_and_complete_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {side: root / side for side in ('java', 'rust')}
            for side, path in artifacts.items(): path.write_text(side)
            gate = {'passed': True, 'http_ready': True, 'verification': {'servers_started': True, 'shutdown_verified': True},
                    'shutdown': {s: {'errors': [], 'forced_kill': False, 'missing_shutdown_markers': [], 'returncode': 0} for s in artifacts}}
            gate.update({s: {'artifact_sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for s, p in artifacts.items()})
            path = root / 'gate.json'
            path.write_text(json.dumps(gate))
            self.assertEqual(require_matching_boot_gate(path, artifacts), gate)
            for side in artifacts:
                original = artifacts[side].read_bytes()
                artifacts[side].write_text('rebuilt')
                with self.assertRaises(ValueError): require_matching_boot_gate(path, artifacts)
                artifacts[side].write_bytes(original)
            gate['shutdown']['rust']['forced_kill'] = True
            path.write_text(json.dumps(gate))
            with self.assertRaises(ValueError): require_matching_boot_gate(path, artifacts)
            with self.assertRaises(FileNotFoundError): require_matching_boot_gate(root / 'missing', artifacts)

    def test_entry_points_reject_before_any_launch_without_gate(self):
        for name in ('phase_two_db', 'phase_two_rust'):
            spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            argv = [name, '--output', '/unused']
            if name.endswith('rust'): argv += ['--runtime', '/unused']
            with self.subTest(name=name), patch.object(sys, 'argv', argv), patch.object(module.subprocess, 'run') as launch:
                with self.assertRaises(SystemExit): module.main()
                launch.assert_not_called()
            with patch.object(sys, 'argv', argv + ['--boot-gate', '/missing/gate.json']), patch.object(module.subprocess, 'run') as launch:
                with self.assertRaises(FileNotFoundError): module.main()
                launch.assert_not_called()
