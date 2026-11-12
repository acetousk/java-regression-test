#!/usr/bin/env python3
"""Change 3: consolidate private phase-two evidence without upgrading its verdicts."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


# Change 8: require the exact selected executions, not merely three XML files.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase_two_rust import expected_suites, run_plans, sha256
from runtime_identity import manifest_digest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def rust_evidence_complete(root):
    try:
        commands = json.loads((root / 'rust-commands.json').read_text())
        provenance = json.loads((root / 'rust-provenance.json').read_text())
        runtime_source = provenance['runtime_manifest']
        if not runtime_source or provenance['runtime_source_sha256'] != manifest_digest(runtime_source):
            return False
        expected = expected_suites()
        if provenance['expected_suites'] != expected or len(commands) != 3:
            return False
        # Validate the retained gate directly, without consulting mutable live artifacts.
        gate = provenance['boot_gate']
        from boot_gate import validate_boot_gate_data
        validate_boot_gate_data(gate)
        # Phase 2 Change 14: matching retained manifests do not prove they were booted.
        if provenance['runtime_source_sha256'] != gate['rust'].get('runtime_source_sha256'):
            return False
        if any(not re.fullmatch('[0-9a-f]{64}', gate[side].get('runtime_source_sha256', '')) for side in ('java', 'rust')):
            return False
        digest = provenance['binary_sha256']
        if not re.fullmatch('[0-9a-f]{64}', digest) or digest != gate['rust']['artifact_sha256']:
            return False
        source = provenance['source']
        if not re.fullmatch('[0-9a-f]{40}', source['revision']) or not re.fullmatch('[0-9a-f]{64}', source['tracked_diff_sha256']):
            return False
        for item, (name, directory, selectors) in zip(commands, run_plans(root)):
            command = item['command']
            if (item['runtime_source_sha256'] != provenance['runtime_source_sha256'] or item['returncode'] != 0 or Path(item['log']).resolve() != (root / (name + '.log')).resolve()
                    or item['binary_sha256'] != digest or not Path(item['runtime']).is_absolute()
                    or item['expected_suites'] != expected[directory]
                    or command[1:] != ['test', *selectors, '--junit', str(root / directory), '--keep']
                    or Path(command[0]).name != 'moqui'):
                return False
            paths = sorted((root / directory).glob('TEST-*.xml'))
            if item['junit_sha256'] != {p.name: sha256(p) for p in paths}:
                return False
            names = []
            for path in paths:
                suite = ET.parse(path).getroot()
                cases = suite.findall('testcase')
                names.append(suite.get('name'))
                if (suite.tag != 'testsuite' or not cases or int(suite.get('tests', '-1')) != len(cases)
                        or any(int(suite.get(key, '-1')) != 0 for key in ('failures', 'errors', 'skipped'))
                        or any(case.find(tag) is not None for case in cases for tag in ('failure', 'error', 'skipped'))):
                    return False
            if sorted(names) != sorted(expected[directory]):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, IndexError, ET.ParseError):
        return False


def evidence_context_matches(paired, rust_root):
    """Change 9: never attribute another build's suite results to this inventory."""
    try:
        from boot_gate import validate_boot_gate_data
        manifests = json.loads((paired / 'runtime-manifests.json').read_text())
        if manifests != json.loads((paired / 'runtime-manifests-after.json').read_text()):
            return False
        paired_source = json.loads((paired / 'provenance.json').read_text())
        paired_gate = validate_boot_gate_data(json.loads((paired / 'boot-gate.json').read_text()))
        independent = json.loads((rust_root / 'rust-provenance.json').read_text())
        rust_gate = validate_boot_gate_data(independent['boot_gate'])
        if not manifests['rust'] or manifests['rust'] != independent['runtime_manifest']:
            return False
        for side in ('java', 'rust'):
            runtime_digest = manifest_digest(manifests[side])
            if (not manifests[side] or runtime_digest != paired_gate[side].get('runtime_source_sha256')
                    or runtime_digest != rust_gate[side].get('runtime_source_sha256')):
                return False
            source = paired_source[side]
            if (not re.fullmatch('[0-9a-f]{40}', source['revision'])
                    or not re.fullmatch('[0-9a-f]{64}', source['tracked_diff_sha256'])
                    or source['artifact_sha256'] != paired_gate[side]['artifact_sha256']
                    or source['artifact_sha256'] != rust_gate[side]['artifact_sha256']):
                return False
        return (paired_source['rust']['artifact_sha256'] == independent['binary_sha256']
                and all(paired_source['rust'][key] == independent['source'][key]
                        for key in ('revision', 'tracked_diff_sha256')))
    except (OSError, ValueError, KeyError, TypeError):
        return False


# Phase 2 Change 18: approved compatibility is distinct from literal database equality.
from phase_two_contract import BUSINESS_CASES, CONVERSION_OUTPUTS, CONVERSION_NUMBERS, business_contracts, selected_rows_match
BUSINESS_CASE_ORDER = tuple(case[0] for case in BUSINESS_CASES)
REQUIRED_BUSINESS_CASES = frozenset(BUSINESS_CASE_ORDER)


def approved_compatibility_complete(paired, result, rust_complete, context_matches, counts):
    try:
        import contextlib
        import io
        import tempfile
        from datetime import datetime, timezone
        from decimal import Decimal
        from phase_two_db import load_controller
        from acceptance.ui.data_clock import read_assignment, verify_persisted_millis
        if not (rust_complete and context_matches and counts['pass'] > 0
                and counts['fail'] == counts['skip'] == 0
                and result['business_all_passed'] is True and result['runtime_source_unchanged'] is True
                and result['whole_database_equal_with_existing_approvals'] is True):
            return False
        cases = result['business']
        if [c['case'] for c in cases] != list(BUSINESS_CASE_ORDER):
            return False
        evidence = Path(result['evidence'])
        if evidence.resolve() != (paired / 'database').resolve():
            return False
        captures = ['provenance.json', 'approved-differences-input.json', 'business-results.json', 'supplied-data-clock',
                    'database/java-snapshot.json', 'database/rust-snapshot.json', 'database/comparison.json',
                    'database/verification.json', 'database/shutdown.json', 'database/approved-differences.json',
                    'database/data-clock-proof/proof.json']
        for case in cases:
            for side in ('java', 'rust'):
                captures.extend(f"business/{case['case']}/{side}/{name}" for name in ('before.json', 'after.json', 'response', 'post-headers', 'service.log'))
        hashes = json.loads((paired / 'comparison-inputs.json').read_text())['sha256']
        if set(hashes) != set(captures) or any(hashes[name] != sha256(paired / name) for name in captures):
            return False
        if json.loads((paired / 'business-results.json').read_text()) != cases:
            return False
        provenance = json.loads((paired / 'provenance.json').read_text())
        if hashes['approved-differences-input.json'] != provenance['approvals_sha256']:
            return False
        rules = json.loads((paired / 'approved-differences-input.json').read_text(), parse_float=Decimal)
        if rules != json.loads((evidence / 'approved-differences.json').read_text(), parse_float=Decimal):
            return False
        verification = json.loads((evidence / 'verification.json').read_text())
        if (not all(verification[name] is True for name in ('servers_started', 'shutdown_verified', 'final_databases_equal', 'passed'))
                or verification['approved_differences_sha256'] != hashes['database/approved-differences.json']):
            return False
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            controller = load_controller()
            if not controller.snapshot_compare(evidence / 'java-snapshot.json', evidence / 'rust-snapshot.json',
                                               Path(temporary), approved_differences=rules, emit_report=False):
                return False
            derived = json.loads((Path(temporary) / 'comparison.json').read_text())
        retained = json.loads((evidence / 'comparison.json').read_text())
        verdicts = ('comparison_passed', 'schema_dump_equal', 'row_and_sequence_values_equal',
                    'schema_equal_after_approved_differences', 'records_equal_after_approved_differences',
                    'statistics_equal_after_approved_differences')
        if (result['raw_whole_database_equal'] != (derived['schema_dump_equal'] and derived['row_and_sequence_values_equal'])
                or any(retained[name] != derived[name] for name in verdicts)):
            return False
        clock = json.loads((evidence / 'data-clock-proof/proof.json').read_text())
        if (clock != result['data_clock_proof'] or clock['passed'] is not True
                or clock['startup_seed']['passed'] is not True or clock['sequence_bank']['passed'] is not True
                or [a['operation'] for a in clock['assignments']] != ['create', 'update']):
            return False
        for name in ('startup_seed', 'sequence_bank'):
            proof = clock[name]
            verify_persisted_millis(proof['supplied_epoch_ms'], proof['persisted_epoch_ms'])
        epochs = [a['supplied_epoch_ms'] for a in clock['assignments']]
        if epochs != [clock['startup_seed']['supplied_epoch_ms'], clock['startup_seed']['supplied_epoch_ms'] + 1]:
            return False
        if clock['sequence_bank']['supplied_epoch_ms'] != epochs[0]:
            return False
        for assignment in clock['assignments']:
            verify_persisted_millis(assignment['supplied_epoch_ms'],
                                   {side: [assignment['persisted'][side]['stamp_ms']] for side in ('java', 'rust')})
        if json.loads((evidence / 'shutdown.json').read_text()) != result['shutdown']:
            return False
        for side in ('java', 'rust'):
            stop = result['shutdown'][side]
            if stop['forced_kill'] is not False or stop['errors'] or stop['missing_shutdown_markers']:
                return False
        contracts = business_contracts()
        previous_rows = {}
        for index, case in enumerate(cases):
            contract = contracts[case['case']]
            if case['service'] != contract['service']:
                return False
            assignment = epochs[-1] + index + 1
            if not (case['passed'] is True and case['raw_selected_rows_equal'] is True and case['data_clock_enabled'] is True
                    and case['raw_rows_required_for_pass'] is True and case['raw_selected_rows_encoding']
                    and case['supplied_epoch_ms'] == assignment):
                return False
            if case['case'] in ('convert-forward', 'convert-reverse'):
                outputs = [case['engines'][side]['service_outputs'] for side in ('java', 'rust')]
                if (outputs[0] != CONVERSION_OUTPUTS[case['case']] or outputs[0] != outputs[1]
                        or Decimal(outputs[0]['convertedAmount']) != CONVERSION_NUMBERS[case['case']]):
                    return False
            values = []
            for side in ('java', 'rust'):
                detail = case['engines'][side]
                directory = paired / 'business' / case['case'] / side
                before, raw = (directory / 'before.json').read_bytes(), (directory / 'after.json').read_bytes()
                if (detail['expected_state_passed'] is not True or sha256(directory / 'after.json') != detail['after_sha256']
                        or sha256(directory / 'before.json') != detail['before_sha256']
                        or raw != detail['after_utf8'].encode('utf-8') or before != detail['before_utf8'].encode('utf-8')):
                    return False
                rows = json.loads(raw, parse_float=Decimal)
                before_rows = json.loads(before, parse_float=Decimal)
                if not selected_rows_match(rows, contract['after']) or not selected_rows_match(before_rows, contract['before']):
                    return False
                if contract['target'] in previous_rows and before != previous_rows[contract['target']]:
                    return False
                statuses = re.findall(r'^HTTP/\S+ (\d{3})', (directory / 'post-headers').read_text(), re.M)
                if not statuses:
                    return False
                status = int(statuses[-1])
                payload = json.loads((directory / 'response').read_text())
                # Phase 2 Change 18: bind retained execution inputs to the fixed case contract.
                parameters = payload.get('currentParameters')
                expected_parameters = {'serviceName': contract['service'], **contract['parameters']}
                if (not isinstance(parameters, dict)
                        or any(parameters.get(key) != value for key, value in expected_parameters.items())):
                    return False
                errors = payload.get('errors') or payload.get('errorMessages') or payload.get('error') or []
                if case['case'] == 'duplicate-enum-refused':
                    if not (errors or status >= 400):
                        return False
                elif not 200 <= status < 400 or errors:
                    return False
                outputs = dict(re.findall(r'^==> ([^:]+): (.*)$', (directory / 'service.log').read_text(), re.M))
                if outputs != detail['service_outputs']:
                    return False
                if case['case'].startswith(('create-', 'update-', 'store-')):
                    proof = detail['data_clock_proof']
                    if (proof['passed'] is not True or proof['expected_epoch_ms'] != assignment
                            or Decimal(proof['persisted_epoch_ms']) != assignment or len(rows) != 1):
                        return False
                    stamp = datetime.fromisoformat(rows[0]['last_updated_stamp'])
                    stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
                    delta = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
                    millis = delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000
                    if delta.microseconds % 1000 or millis != assignment:
                        return False
                elif case['case'].startswith('delete-'):
                    if rows != []:
                        return False
                elif before != raw:
                    return False
                values.append((before, raw))
            if values[0] != values[1]:
                return False
            previous_rows[contract['target']] = values[0][1]
        return read_assignment(paired / 'supplied-data-clock') == epochs[-1] + len(cases)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--paired', default='paired-05')
    parser.add_argument('--rust-results', type=Path, help='Separate output of phase_two_rust.py; defaults to --run')
    args = parser.parse_args()
    root = args.run.resolve()
    paired = root / args.paired
    rust_root = args.rust_results.resolve() if args.rust_results else root
    result = json.loads((paired / 'result.json').read_text())
    inventory = json.loads((paired / 'inventory.json').read_text())
    context_matches = evidence_context_matches(paired, rust_root)
    rust_complete = rust_evidence_complete(rust_root)
    attributable = context_matches and rust_complete
    suites = []
    for directory in ['rust-junit', 'rust-expanded-junit', 'rust-acceptance-junit']:
        for path in sorted((rust_root / directory).glob('TEST-*.xml')):
            suite = ET.parse(path).getroot()
            cases = []
            for case in suite.findall('testcase'):
                failure = case.find('failure')
                error = case.find('error')
                skipped = case.find('skipped')
                cases.append({'name': case.get('name'), 'status': 'fail' if failure is not None or error is not None else 'skip' if skipped is not None else 'pass',
                              'details': ''.join(case.itertext()).strip()})
            suites.append({'name': suite.get('name'), 'evidence': str(path), 'cases': cases,
                           'java_comparison': 'not run as paired Java spec; Rust assertions only',
                           'suite': 'acceptance' if 'acceptance' in directory else 'regression'})
    for suite in suites if attributable else []:
        if not suite['name'] or '.' not in suite['name']:
            continue
        component, name = suite['name'].split('.', 1)
        for item in inventory['rust']['specs']:
            if f'/{component}/' in item['path'] and item['path'].endswith('/' + name + '.spec.js'):
                item['status'] = 'pass' if all(c['status'] == 'pass' for c in suite['cases']) else 'fail_or_skip'
                item['executed_evidence'] = suite['evidence']
    coverage = rust_root / 'rust-service-coverage.txt'
    for line in coverage.read_text().splitlines() if attributable and coverage.exists() else []:
        match = re.match(r'\s+called\s+(\d+)\s+(\S+)', line)
        if match and match[2] in inventory['rust']['services']:
            inventory['rust']['services'][match[2]].update(status='called_in_rust_specs', count=int(match[1]), evidence=str(coverage),
                                                        caveat='Call count includes expected refusals and nested calls; not per-service success proof.')
    for probe in result.get('business', []):
        for side in ['java', 'rust']:
            item = inventory[side]['services'].setdefault(probe['service'], {'type': 'implicit entity-auto', 'counterpart': True})
            item['status'] = 'paired_probe_pass' if probe['passed'] else 'paired_probe_fail'
    evidence = Path(result['evidence'])
    db_summary = json.loads((evidence / 'summary.json').read_text())
    counts = {state: sum(c['status'] == state for s in suites for c in s['cases']) for state in ['pass', 'fail', 'skip']}
    rust_complete = rust_complete and counts['pass'] > 0
    budgets = []
    for file in rust_root.glob('rust-*.log'):
        budgets.extend({'log': str(file), 'line': line.strip()} for line in file.read_text().splitlines() if 'over its budget' in line)
    summary = {
        'phase': 2, 'phase_passed': bool(result['raw_whole_database_equal'] and result['business_all_passed'] and rust_complete and context_matches and counts['fail'] == 0 and counts['skip'] == 0),
        'approved_compatibility_passed': approved_compatibility_complete(paired, result, rust_complete and not budgets, context_matches, counts),
        'approved_compatibility_scope': {
            'paired_business_case_ids': sorted(REQUIRED_BUSINESS_CASES),
            'rust_suites': expected_suites(),
            'database_state': str(evidence / 'comparison.json'),
            'scope': 'Only the named paired probes, selected Rust assertions, and retained database states.',
            'all_service_behavior_verified': False, 'ui_operation_coverage_verified': False},
        'rust_execution_evidence_complete': rust_complete,
        'paired_and_rust_evidence_context_matches': context_matches,
        'rust_results_attributed_to_paired_inventory': attributable,
        'reason': 'See separate raw database, approved compatibility, paired probe and independent Rust-suite verdicts. Active exceptions are retained separately.',
        'paired_run': str(paired),
        'rust_results': str(rust_root),
        'reproduction_commands': str(rust_root / 'rust-commands.json') if (rust_root / 'rust-commands.json').exists() else None,
        'raw_selected_row_verdicts_verified_as_bytes': all(c.get('raw_selected_rows_encoding') for c in result['business']),
        'raw_whole_database_equal': result['raw_whole_database_equal'],
        'whole_database_equal_with_existing_approvals': result['whole_database_equal_with_existing_approvals'],
        'paired_business_cases': len(result['business']),
        'paired_business_passes': sum(c['passed'] for c in result['business']),
        'raw_selected_rows_equal_cases': sum(c['raw_selected_rows_equal'] and bool(c.get('raw_selected_rows_encoding')) for c in result['business']),
        'projected_business_deltas_equal_cases': sum(c.get('projected_deltas_equal', False) for c in result['business']),
        'business_projection_exclusions': ['last_updated_stamp'],
        'service_output_comparisons': [{'case': c['case'], 'raw_outputs_equal': c['engines']['java'].get('service_outputs') == c['engines']['rust'].get('service_outputs'), 'expected_numeric_results_passed': all(x['expected_state_passed'] for x in c['engines'].values())} for c in result['business'] if c['case'].startswith('convert-')],
        'rust_case_counts': counts, 'rust_spec_count': len(suites), 'budget_findings': budgets,
        'uncovered_operations': {side: sorted(name for name, item in inventory[side]['services'].items()
                                             if item.get('status') not in ('paired_probe_pass',))
                                 for side in ('java', 'rust')},
        'uncovered_operations_scope': 'Services without a successful paired Java/Rust probe; independent calls do not establish parity.',
        'database_relation_counts': {name: len(db_summary[name]) for name in ['java_only_relations', 'rust_only_relations', 'shared_relation_differences', 'differing_tables']},
        'exact_database_differences': str(evidence / 'comparison.json'),
        'exact_schema_diff': str(evidence / 'schema.diff'),
        'remaining_schema_diff_after_existing_approvals': str(evidence / 'unapproved-schema.diff'),
        'suites': suites,
        'limitations': [
            'No Mantle/ERP components installed. Historical shipment/order specs are inapplicable; no old stack imported.',
            'Source inventory is not service coverage. Unexecuted services and specs remain explicitly not_run.',
            'Same service name means a potential counterpart, not proof of equivalent behavior.',
            'Rust spec calls are distinguished from paired Java execution. Source-only current services have no named Java counterpart.',
            'Independent Rust suite databases do not establish Java database parity.',
            'Raw selected rows retain generated timestamps. Projected deltas are diagnostics and exclude last_updated_stamp. Approved compatibility requires literal selected-row bytes and supplied-clock proof.',
            'Canonical comparator compares schema text, typed JSON row multisets and sequence state; not physical database pages.',
            'OpenSearch-dependent workflows were not selected; optional Java OpenSearch remains unavailable.',
            'Native sequences and full schema captured only after verified graceful shutdown, not per-request transaction barriers.',
        ],
    }
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (root / 'coverage-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    text = [
        '# Change 2: database and business validation', '',
        f"Whole database: raw equality **{summary['raw_whole_database_equal']}**; existing-approval equality **{summary['whole_database_equal_with_existing_approvals']}**. Raw phase gate passed: {summary['phase_passed']}; approved compatibility passed: {summary['approved_compatibility_passed']}.", '',
        f"Paired runner reports: {summary['paired_business_passes']}/{summary['paired_business_cases']} passing cases and {summary['raw_selected_rows_equal_cases']} matching selected-row checkpoints. The approved gate independently checks retained contracts and bytes. Projections remain diagnostic and omit last_updated_stamp.", '',
        f"Rust: {counts['pass']} passing, {counts['fail']} failing, {counts['skip']} skipped feature assertions across {len(suites)} specs. Independent Rust assertions are not paired Java results.", '',
        'Evidence:', '',
        '- summary.json: verdicts, individual spec/case results, limitations, budget findings.',
        '- coverage-inventory.json: source service/spec inventory, potential named counterparts, actual execution status.',
        f'- {args.paired}/business-results.json: every request result, before/after selected rows, exact row diffs and business deltas.',
        f'- {evidence.relative_to(root)}/comparison.json: exact UTF-8/hex schema and typed canonical row/sequence differences, raw and approved verdicts separately.',
        f'- {args.paired}/provenance.json: source revisions, working-diff hashes, artifacts and approvals hashes.', '',
        'Choices for end review:', '',
        '- Retain raw captures and the exact selected rule bytes. Keep projections diagnostic.',
        f"- Raw phase gate: {summary['phase_passed']}. Approved compatibility: {summary['approved_compatibility_passed']}.",
        '- Service output byte verdicts and numeric-result verdicts are separate in summary.json.',
        '- Do not claim complete process coverage: unrun and noncomparable services remain inventoried.',
        '- Component budget warnings and command exit codes remain recorded; no budgets changed.', '',
    ]
    (root / 'HANDOFF.md').write_text('\n'.join(text))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('suites','limitations')}, indent=2))


if __name__ == '__main__':
    main()
