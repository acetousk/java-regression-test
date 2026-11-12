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
            # Phase 1, Change 3: executable equality does not cover changed component inputs.
            from runtime_identity import runtime_manifest, manifest_digest
            runtimes = {side: root / (side + '-runtime') for side in artifacts}
            for side, runtime in runtimes.items():
                for name in ('base-component', 'component', 'conf'):
                    (runtime / name).mkdir(parents=True)
                (runtime / 'conf/test.xml').write_text('<conf/>')
                gate[side]['runtime_source_sha256'] = manifest_digest(runtime_manifest(runtime))
            path.write_text(json.dumps(gate))
            self.assertEqual(require_matching_boot_gate(path, artifacts, runtimes), gate)
            (runtimes['rust'] / 'conf/test.xml').write_text('<changed/>')
            with self.assertRaisesRegex(ValueError, 'Runtime source differs'):
                require_matching_boot_gate(path, artifacts, runtimes)
            (runtimes['rust'] / 'conf/test.xml').write_text('<conf/>')
            gate['java'].pop('runtime_source_sha256')
            path.write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, 'Runtime source differs'):
                require_matching_boot_gate(path, artifacts, runtimes)
            gate['shutdown']['rust']['forced_kill'] = True
            path.write_text(json.dumps(gate))
            with self.assertRaises(ValueError): require_matching_boot_gate(path, artifacts)
            with self.assertRaises(FileNotFoundError): require_matching_boot_gate(root / 'missing', artifacts)

