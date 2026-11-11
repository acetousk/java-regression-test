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
    def fixture(self, root):
        digest = 'a' * 64
        shutdown = {side: {'errors': [], 'forced_kill': False, 'missing_shutdown_markers': [], 'returncode': 0}
                    for side in ('java', 'rust')}
        gate = {'passed': True, 'http_ready': True, 'verification': {'servers_started': True, 'shutdown_verified': True},
                'shutdown': shutdown, 'rust': {'artifact_sha256': digest}, 'java': {'artifact_sha256': 'd' * 64}}
        provenance = {'binary_sha256': digest, 'source': {'revision': 'b' * 40, 'tracked_diff_sha256': 'c' * 64},
                      'expected_suites': report.expected_suites(), 'boot_gate': gate}
        (root / 'rust-provenance.json').write_text(json.dumps(provenance))
        commands = []
        for name, directory, selectors in report.run_plans(root):
            target = root / directory
            target.mkdir()
            for suite in report.expected_suites()[directory]:
                (target / ('TEST-' + suite + '.xml')).write_text(
                    f'<testsuite name="{suite}" tests="1" failures="0" errors="0" skipped="0"><testcase name="rule"/></testsuite>')
            commands.append({'command': ['/artifact/moqui', 'test', *selectors, '--junit', str(target), '--keep'],
                             'runtime': '/private/runtime', 'binary_sha256': digest, 'returncode': 0,
                             'expected_suites': report.expected_suites()[directory], 'log': str(root / (name + '.log')),
                             'junit_sha256': {p.name: report.sha256(p) for p in target.glob('TEST-*.xml')}})
        (root / 'rust-commands.json').write_text(json.dumps(commands))
        return commands

    def test_exact_selected_execution_and_fail_closed_variants(self):
        for mutation in ('missing', 'unrelated', 'duplicate', 'empty', 'skipped', 'totals', 'selector', 'hash', 'failed', 'provenance'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                commands = self.fixture(root)
                self.assertTrue(report.rust_evidence_complete(root))
                path = next((root / 'rust-junit').glob('TEST-*.xml'))
                if mutation == 'missing': path.unlink()
                elif mutation == 'unrelated': path.write_text(path.read_text().replace('framework.', 'example.'))
                elif mutation == 'duplicate': (path.parent / 'TEST-duplicate.xml').write_bytes(path.read_bytes())
                elif mutation == 'empty': path.write_text('<testsuite/>')
                elif mutation == 'skipped': path.write_text(path.read_text().replace('<testcase name="rule"/>', '<testcase name="rule"><skipped/></testcase>'))
                elif mutation == 'totals': path.write_text(path.read_text().replace('tests="1"', 'tests="2"'))
                elif mutation == 'selector': commands[0]['command'][4] = 'WrongSelector'
                elif mutation == 'hash': commands[0]['junit_sha256'][path.name] = '0' * 64
                elif mutation == 'failed': commands[0]['returncode'] = 1
                elif mutation == 'provenance': (root / 'rust-provenance.json').unlink()
                # Refresh hashes to test semantic rejection independently of tamper detection.
                if mutation in ('missing', 'unrelated', 'duplicate', 'empty', 'skipped', 'totals'):
                    commands[0]['junit_sha256'] = {p.name: report.sha256(p) for p in path.parent.glob('TEST-*.xml')}
                (root / 'rust-commands.json').write_text(json.dumps(commands))
                self.assertFalse(report.rust_evidence_complete(root))

    def test_legacy_three_empty_suites_cannot_establish_completeness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(report.rust_evidence_complete(root))
            (root / 'rust-commands.json').write_text(json.dumps([
                {'log': name + '.log', 'returncode': 0} for name in ('rust-business', 'rust-expanded', 'rust-acceptance')]))
            for directory in report.expected_suites():
                (root / directory).mkdir()
                (root / directory / 'TEST-example.xml').write_text('<testsuite/>')
            self.assertFalse(report.rust_evidence_complete(root))
