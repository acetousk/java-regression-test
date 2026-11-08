import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'phase_two_report', Path(__file__).resolve().parents[1] / 'tools/phase_two_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class EvidenceTests(unittest.TestCase):
    def test_missing_commands_never_establish_a_rust_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(report.rust_evidence_complete(Path(directory)))

    def test_all_three_runs_need_success_and_junit_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = [{'log': name + '.log', 'returncode': 0}
                        for name in ('rust-business', 'rust-expanded', 'rust-acceptance')]
            path = root / 'rust-commands.json'
            path.write_text(json.dumps(commands))
            self.assertFalse(report.rust_evidence_complete(root))
            for name in ('rust-junit', 'rust-expanded-junit', 'rust-acceptance-junit'):
                (root / name).mkdir()
                (root / name / 'TEST-example.xml').write_text('<testsuite/>')
            self.assertTrue(report.rust_evidence_complete(root))
            commands[-1]['returncode'] = 1
            path.write_text(json.dumps(commands))
            self.assertFalse(report.rust_evidence_complete(root))
