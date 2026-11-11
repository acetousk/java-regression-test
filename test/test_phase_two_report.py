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

    def test_reports_only_combine_matching_retained_contexts(self):
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        for mutation in (None, 'rust_artifact', 'java_artifact', 'revision', 'diff', 'missing_source', 'missing_gate', 'failed_gate'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                rust = root / 'independent'
                rust.mkdir()
                self.fixture(rust)
                independent = json.loads((rust / 'rust-provenance.json').read_text())
                paired = root / 'paired-05'
                paired.mkdir()
                database = paired / 'database'
                database.mkdir()
                provenance = {side: {'artifact_sha256': independent['boot_gate'][side]['artifact_sha256'],
                                     'revision': 'b' * 40, 'tracked_diff_sha256': 'c' * 64} for side in ('java', 'rust')}
                gate = independent['boot_gate']
                if mutation == 'rust_artifact': provenance['rust']['artifact_sha256'] = 'f' * 64
                if mutation == 'java_artifact': provenance['java']['artifact_sha256'] = 'e' * 64
                if mutation == 'revision': provenance['rust']['revision'] = 'f' * 40
                if mutation == 'diff': provenance['rust']['tracked_diff_sha256'] = 'f' * 64
                if mutation == 'failed_gate': gate['passed'] = False
                if mutation != 'missing_source': (paired / 'provenance.json').write_text(json.dumps(provenance))
                if mutation != 'missing_gate': (paired / 'boot-gate.json').write_text(json.dumps(gate))
                (paired / 'result.json').write_text(json.dumps({
                    'evidence': str(database), 'raw_whole_database_equal': True, 'business_all_passed': True,
                    'whole_database_equal_with_existing_approvals': True,
                    'business': [{'case': 'fixture', 'service': 'paired#Service', 'passed': True,
                                  'raw_selected_rows_equal': True, 'raw_selected_rows_encoding': 'UTF-8'}]}))
                (paired / 'inventory.json').write_text(json.dumps({side: {
                    'specs': [{'path': 'runtime/base-component/framework/test/Units.spec.js', 'status': 'not_run'}],
                    'services': {'independent#Service': {'status': 'not_run'}}} for side in ('java', 'rust')}))
                (database / 'summary.json').write_text(json.dumps({k: [] for k in (
                    'java_only_relations', 'rust_only_relations', 'shared_relation_differences', 'differing_tables')}))
                (rust / 'rust-service-coverage.txt').write_text('  called 2 independent#Service\n')
                with patch.object(sys, 'argv', ['report', '--run', str(root), '--rust-results', str(rust)]), contextlib.redirect_stdout(io.StringIO()):
                    report.main()
                summary = json.loads((root / 'summary.json').read_text())
                inventory = json.loads((root / 'coverage-inventory.json').read_text())
                self.assertEqual(summary['phase_passed'], mutation is None)
                self.assertEqual(summary['paired_and_rust_evidence_context_matches'], mutation is None)
                self.assertTrue(summary['rust_execution_evidence_complete'])
                self.assertEqual(inventory['rust']['specs'][0]['status'], 'pass' if mutation is None else 'not_run')
                self.assertEqual(inventory['rust']['services']['independent#Service']['status'],
                                 'called_in_rust_specs' if mutation is None else 'not_run')
                self.assertEqual(summary['rust_spec_count'], 45)
