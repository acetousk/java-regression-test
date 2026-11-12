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
        runtime_source = {'base-component/framework/test/Units.spec.js': 'e' * 64}
        for side in ('java', 'rust'):
            gate[side]['runtime_source_sha256'] = report.manifest_digest(runtime_source)
        provenance = {'runtime_manifest': runtime_source, 'runtime_source_sha256': report.manifest_digest(runtime_source), 'binary_sha256': digest, 'source': {'revision': 'b' * 40, 'tracked_diff_sha256': 'c' * 64},
                      'expected_suites': report.expected_suites(), 'boot_gate': gate}
        (root / 'rust-provenance.json').write_text(json.dumps(provenance))
        commands = []
        for name, directory, selectors in report.run_plans(root):
            target = root / directory
            target.mkdir()
            for suite in report.expected_suites()[directory]:
                (target / ('TEST-' + suite + '.xml')).write_text(
                    f'<testsuite name="{suite}" tests="1" failures="0" errors="0" skipped="0"><testcase name="rule"/></testsuite>')
            commands.append({'runtime_source_sha256': report.manifest_digest(runtime_source), 'command': ['/artifact/moqui', 'test', *selectors, '--junit', str(target), '--keep'],
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
        for mutation in (None, 'rust_artifact', 'java_artifact', 'revision', 'diff', 'missing_source', 'missing_gate', 'failed_gate', 'stale_runtime', 'missing_runtime', 'changed_runtime', 'missing_gate_runtime', 'wrong_gate_runtime', 'unbooted_same_runtime', 'missing_independent_runtime'):
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
                runtime_manifests = {side: independent['runtime_manifest'] for side in ('java', 'rust')}
                if mutation == 'stale_runtime': runtime_manifests['rust'] = {'base-component/framework/test/Units.spec.js': 'f' * 64}
                if mutation == 'unbooted_same_runtime':
                    runtime_manifests['rust'] = {'base-component/framework/test/Units.spec.js': 'f' * 64}
                    independent['runtime_manifest'] = runtime_manifests['rust']
                    independent['runtime_source_sha256'] = report.manifest_digest(runtime_manifests['rust'])
                    commands = json.loads((rust / 'rust-commands.json').read_text())
                    for command in commands: command['runtime_source_sha256'] = independent['runtime_source_sha256']
                    (rust / 'rust-commands.json').write_text(json.dumps(commands))
                    (rust / 'rust-provenance.json').write_text(json.dumps(independent))
                if mutation == 'missing_independent_runtime':
                    independent['boot_gate']['rust'].pop('runtime_source_sha256')
                    (rust / 'rust-provenance.json').write_text(json.dumps(independent))
                if mutation != 'missing_runtime':
                    (paired / 'runtime-manifests.json').write_text(json.dumps(runtime_manifests))
                    (paired / 'runtime-manifests-after.json').write_text(json.dumps(runtime_manifests if mutation != 'changed_runtime' else {}))
                gate = independent['boot_gate']
                if mutation == 'missing_gate_runtime': gate['java'].pop('runtime_source_sha256')
                if mutation == 'wrong_gate_runtime': gate['rust']['runtime_source_sha256'] = '0' * 64
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
                self.assertEqual(summary['rust_execution_evidence_complete'], mutation not in ('unbooted_same_runtime', 'missing_independent_runtime'))
                self.assertEqual(inventory['rust']['specs'][0]['status'], 'pass' if mutation is None else 'not_run')
                self.assertEqual(inventory['rust']['services']['independent#Service']['status'],
                                 'called_in_rust_specs' if mutation is None else 'not_run')
                self.assertEqual(summary['rust_spec_count'], 45)

    # Phase 2 Change 18: raw equality and approved compatibility use distinct, retained proofs.
    def test_approved_compatibility_recomputes_snapshots_and_checks_each_clock(self):
        import copy
        import contextlib
        import io
        from datetime import datetime, timezone, timedelta
        from phase_two_db import load_controller
        with tempfile.TemporaryDirectory() as directory:
            paired = Path(directory)
            evidence = paired / 'database'
            (evidence / 'data-clock-proof').mkdir(parents=True)
            controller = load_controller()
            active = copy.deepcopy(controller.APPROVED_STARTUP_DIFFERENCES)
            active['reviewed_seed_rows'] = [{'engine': 'rust', 'table': 'public.fixture',
                                             'key': {'id': 'extra'}, 'expected': {'id': 'extra'}}]
            rules = paired / 'approved-differences-input.json'
            rules.write_text(json.dumps(active))
            (evidence / 'approved-differences.json').write_bytes(rules.read_bytes())
            (paired / 'provenance.json').write_text(json.dumps({'approvals_sha256': report.sha256(rules)}))
            for side in ('java', 'rust'):
                records = [] if side == 'java' else [json.dumps({'table': 'public.fixture', 'row': {'id': 'extra'}})]
                (evidence / (side + '-snapshot.json')).write_text(json.dumps({'schema': '', 'records': records}))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(controller.snapshot_compare(evidence / 'java-snapshot.json', evidence / 'rust-snapshot.json',
                                                            evidence, approved_differences=active, emit_report=False))
            verification = {name: True for name in ('servers_started', 'shutdown_verified', 'final_databases_equal', 'passed')}
            verification['approved_differences_sha256'] = report.sha256(evidence / 'approved-differences.json')
            (evidence / 'verification.json').write_text(json.dumps(verification))
            epoch = 1767225600000
            clock = {'passed': True, 'startup_seed': {'passed': True}, 'sequence_bank': {'passed': True},
                     'assignments': [{'operation': 'create'}, {'operation': 'update'}]}
            for name in ('startup_seed', 'sequence_bank'):
                clock[name].update(supplied_epoch_ms=epoch, persisted_epoch_ms={'java': [epoch], 'rust': [epoch]})
            for index, assignment in enumerate(clock['assignments']):
                assignment.update(supplied_epoch_ms=epoch + index,
                                  persisted={side: {'stamp_ms': epoch + index} for side in ('java', 'rust')})
            cases, row_states = [], {}
            contracts = report.business_contracts()
            for index, name in enumerate(report.BUSINESS_CASE_ORDER):
                assigned = epoch + index + 2
                stamp = (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=assigned)).isoformat()
                contract = contracts[name]
                writes = name.startswith(('create-', 'update-', 'store-'))
                before_rows = copy.deepcopy(row_states.get(contract['target'], []))
                after_rows = ([{**contract['after'], 'last_updated_stamp': stamp}] if writes
                              else ([] if name.startswith('delete-') else copy.deepcopy(before_rows)))
                row_states[contract['target']] = copy.deepcopy(after_rows)
                engines = {}
                for side in ('java', 'rust'):
                    dest = paired / 'business' / name / side
                    dest.mkdir(parents=True)
                    (dest / 'before.json').write_text(json.dumps(before_rows) + '\n')
                    (dest / 'after.json').write_text(json.dumps(after_rows) + '\n')
                    response = {'currentParameters': {'serviceName': contract['service'], **contract['parameters']}}
                    if name == 'duplicate-enum-refused':
                        response['errors'] = ['duplicate']
                    (dest / 'response').write_text(json.dumps(response))
                    (dest / 'post-headers').write_text('HTTP/1.1 ' + ('400 Refused' if name == 'duplicate-enum-refused' else '200 OK') + '\n')
                    outputs = copy.deepcopy(report.CONVERSION_OUTPUTS.get(name, {}))
                    (dest / 'service.log').write_text(''.join(f'==> {key}: {value}\n' for key, value in outputs.items()))
                    engines[side] = {'expected_state_passed': True, 'service_outputs': outputs,
                                     'data_clock_proof': {'expected_epoch_ms': assigned, 'persisted_epoch_ms': str(assigned), 'passed': True} if writes else None}
                    for when in ('before', 'after'):
                        engines[side][when + '_sha256'] = report.sha256(dest / (when + '.json'))
                        engines[side][when + '_utf8'] = (dest / (when + '.json')).read_text()
                cases.append({'case': name, 'service': contract['service'], 'passed': True, 'raw_selected_rows_equal': True,
                              'supplied_epoch_ms': assigned, 'data_clock_enabled': True, 'raw_rows_required_for_pass': True,
                              'raw_selected_rows_encoding': 'UTF-8', 'engines': engines})
            (paired / 'supplied-data-clock').write_text(str(epoch + 17) + '\n')
            result = {'raw_whole_database_equal': False, 'whole_database_equal_with_existing_approvals': True,
                      'business_all_passed': True, 'runtime_source_unchanged': True, 'evidence': str(evidence),
                      'data_clock_proof': clock, 'business': cases,
                      'shutdown': {s: {'forced_kill': False, 'errors': [], 'missing_shutdown_markers': []} for s in ('java', 'rust')}}
            captures = ['provenance.json', 'approved-differences-input.json', 'business-results.json', 'supplied-data-clock',
                        'database/java-snapshot.json', 'database/rust-snapshot.json', 'database/comparison.json',
                        'database/verification.json', 'database/shutdown.json', 'database/approved-differences.json',
                        'database/data-clock-proof/proof.json']
            captures += [f"business/{case['case']}/{side}/{name}" for case in cases for side in ('java', 'rust')
                         for name in ('before.json', 'after.json', 'response', 'post-headers', 'service.log')]
            def retain(value):
                (paired / 'business-results.json').write_text(json.dumps(value['business']))
                (evidence / 'data-clock-proof/proof.json').write_text(json.dumps(value['data_clock_proof']))
                (evidence / 'shutdown.json').write_text(json.dumps(value['shutdown']))
                (paired / 'comparison-inputs.json').write_text(json.dumps({'sha256': {n: report.sha256(paired / n) for n in captures}}))
            counts = {'pass': 285, 'fail': 0, 'skip': 0}
            retain(result)
            self.assertTrue(report.approved_compatibility_complete(paired, result, True, True, counts))
            self.assertFalse(result['raw_whole_database_equal'])
            for mutation in ('missing_case', 'duplicate_case', 'clock', 'missing_case_clock', 'false_case_clock',
                             'wrong_case_epoch', 'wrong_persisted_epoch', 'stamp', 'shutdown', 'whole_db', 'output_text'):
                changed = copy.deepcopy(result)
                if mutation == 'missing_case': changed['business'].pop()
                if mutation == 'duplicate_case': changed['business'][-1] = changed['business'][0]
                if mutation == 'clock': changed['data_clock_proof']['assignments'][0]['persisted']['rust']['stamp_ms'] += 1
                detail = changed['business'][0]['engines']['rust']
                if mutation == 'missing_case_clock': detail.pop('data_clock_proof')
                if mutation == 'false_case_clock': detail['data_clock_proof']['passed'] = False
                if mutation == 'wrong_case_epoch': changed['business'][0]['supplied_epoch_ms'] += 1
                if mutation == 'wrong_persisted_epoch': detail['data_clock_proof']['persisted_epoch_ms'] = str(epoch)
                if mutation == 'stamp': detail['after_utf8'] = '[]\n'
                if mutation == 'shutdown': changed['shutdown']['rust']['forced_kill'] = True
                if mutation == 'whole_db': changed['whole_database_equal_with_existing_approvals'] = False
                if mutation == 'output_text':
                    next(c for c in changed['business'] if c['case'] == 'convert-forward')['engines']['rust']['service_outputs']['convertedAmount'] = '200'
                retain(changed)
                self.assertFalse(report.approved_compatibility_complete(paired, changed, True, True, counts), mutation)
            retain(result)
            self.assertFalse(report.approved_compatibility_complete(paired, result, False, True, counts))
            self.assertFalse(report.approved_compatibility_complete(paired, result, True, False, counts))
            self.assertFalse(report.approved_compatibility_complete(paired, result, True, True, {**counts, 'skip': 1}))
            # Equal wrong results cannot pass after refreshing every retained hash.
            def restore_case_files():
                for case in result['business']:
                    for side in ('java', 'rust'):
                        dest = paired / 'business' / case['case'] / side
                        detail = case['engines'][side]
                        for when in ('before', 'after'):
                            (dest / (when + '.json')).write_text(detail[when + '_utf8'])
                        (dest / 'service.log').write_text(''.join(f'==> {key}: {value}\n' for key, value in detail['service_outputs'].items()))
            for name in ('convert-forward', 'convert-reverse', 'create-type', 'create-enum', 'create-conversion'):
                changed = copy.deepcopy(result)
                case = next(c for c in changed['business'] if c['case'] == name)
                for side in ('java', 'rust'):
                    detail = case['engines'][side]
                    dest = paired / 'business' / name / side
                    if name.startswith('convert-'):
                        detail['service_outputs'] = {'convertedAmount': '999'}
                        (dest / 'service.log').write_text('==> convertedAmount: 999\n')
                    else:
                        rows = json.loads(detail['after_utf8'])
                        field, value = {'create-type': ('description', 'wrong'), 'create-enum': ('enum_id', 'WRONG_ID'),
                                        'create-conversion': ('conversion_factor', 999)}[name]
                        rows[0][field] = value
                        (dest / 'after.json').write_text(json.dumps(rows) + '\n')
                        detail['after_utf8'], detail['after_sha256'] = (dest / 'after.json').read_text(), report.sha256(dest / 'after.json')
                retain(changed)
                self.assertFalse(report.approved_compatibility_complete(paired, changed, True, True, counts), name)
                restore_case_files()
            retain(result)
            # Equal wrong request inputs cannot pass with refreshed capture hashes.
            for name, field, value in [('convert-reverse', 'serviceName', 'unrelated#Service'),
                                       ('convert-reverse', 'amount', '999'),
                                       ('create-enum', 'enumId', 'WRONG_ID'),
                                       ('create-enum', 'sequenceNum', 7),
                                       ('create-enum', 'currentParameters', None),
                                       ('convert-reverse', 'amount', None)]:
                originals = {}
                for side in ('java', 'rust'):
                    path = paired / 'business' / name / side / 'response'
                    originals[path] = path.read_bytes()
                    payload = json.loads(originals[path])
                    if field == 'currentParameters':
                        payload.pop(field)
                    elif value is None:
                        payload['currentParameters'].pop(field)
                    else:
                        payload['currentParameters'][field] = value
                    path.write_text(json.dumps(payload))
                retain(result)
                self.assertFalse(report.approved_compatibility_complete(paired, result, True, True, counts), (name, field))
                for path, content in originals.items():
                    path.write_bytes(content)
            retain(result)
            # Matching claimed milliseconds cannot conceal different timestamps in retained row bytes.
            wrong_rows = copy.deepcopy(result)
            for side in ('java', 'rust'):
                detail = wrong_rows['business'][0]['engines'][side]
                path = paired / 'business/create-type' / side / 'after.json'
                rows = json.loads(detail['after_utf8'])
                rows[0]['last_updated_stamp'] = '2026-01-01T00:00:00.003+00:00'
                path.write_text(json.dumps(rows) + '\n')
                detail['after_utf8'], detail['after_sha256'] = path.read_text(), report.sha256(path)
            retain(wrong_rows)
            self.assertFalse(report.approved_compatibility_complete(paired, wrong_rows, True, True, counts))
            for side in ('java', 'rust'):
                (paired / 'business/create-type' / side / 'after.json').write_text(result['business'][0]['engines'][side]['after_utf8'])
            retain(result)
            # Even refreshed hashes cannot make a stale comparison flag certify different final rows.
            snapshot = evidence / 'rust-snapshot.json'
            original_snapshot = snapshot.read_text()
            data = json.loads(original_snapshot)
            data['records'].append(json.dumps({'table': 'public.shared', 'row': {'id': 'unexpected'}}))
            snapshot.write_text(json.dumps(data))
            retain(result)
            self.assertFalse(report.approved_compatibility_complete(paired, result, True, True, counts))
            snapshot.write_text(original_snapshot)
            retain(result)
            hashes = json.loads((paired / 'comparison-inputs.json').read_text())
            hashes['sha256'].pop('database/java-snapshot.json')
            (paired / 'comparison-inputs.json').write_text(json.dumps(hashes))
            self.assertFalse(report.approved_compatibility_complete(paired, result, True, True, counts))
