#!/usr/bin/env python3
"""Change 3: consolidate private phase-two evidence without upgrading its verdicts."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def rust_evidence_complete(root):
    commands_path = root / 'rust-commands.json'
    if not commands_path.exists():
        return False
    commands = json.loads(commands_path.read_text())
    expected = {'rust-business.log', 'rust-expanded.log', 'rust-acceptance.log'}
    return (len(commands) == 3
            and {Path(item['log']).name for item in commands} == expected
            and all(item['returncode'] == 0 for item in commands)
            and all(any((root / directory).glob('TEST-*.xml')) for directory in
                    ('rust-junit', 'rust-expanded-junit', 'rust-acceptance-junit')))


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
    for suite in suites:
        component, name = suite['name'].split('.', 1)
        for item in inventory['rust']['specs']:
            if f'/{component}/' in item['path'] and item['path'].endswith('/' + name + '.spec.js'):
                item['status'] = 'pass' if all(c['status'] == 'pass' for c in suite['cases']) else 'fail_or_skip'
                item['executed_evidence'] = suite['evidence']
    coverage = rust_root / 'rust-service-coverage.txt'
    for line in coverage.read_text().splitlines() if coverage.exists() else []:
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
    rust_complete = rust_evidence_complete(rust_root) and counts['pass'] > 0
    budgets = []
    for file in rust_root.glob('rust-*.log'):
        budgets.extend({'log': str(file), 'line': line.strip()} for line in file.read_text().splitlines() if 'over its budget' in line)
    summary = {
        'phase': 2, 'phase_passed': bool(result['raw_whole_database_equal'] and result['business_all_passed'] and rust_complete and counts['fail'] == 0 and counts['skip'] == 0),
        'rust_execution_evidence_complete': rust_complete,
        'reason': 'See separate raw whole-database, existing-approval, business projection and independent Rust-suite verdicts; no approvals added.',
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
            'Business probes compare selected rows and deltas only, with generated timestamps explicitly excluded. Full DB comparator excludes none beyond separately reported existing approvals.',
            'Canonical comparator compares schema text, typed JSON row multisets and sequence state; not physical database pages.',
            'OpenSearch-dependent workflows were not selected; optional Java OpenSearch remains unavailable.',
            'Native sequences and full schema captured only after verified graceful shutdown, not per-request transaction barriers.',
        ],
    }
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (root / 'coverage-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    text = [
        '# Change 2: database and business validation', '',
        f"Whole database: raw equality **{summary['raw_whole_database_equal']}**; existing-approval equality **{summary['whole_database_equal_with_existing_approvals']}**. Phase gate passed: {summary['phase_passed']}.", '',
        f"Paired business scenarios: {summary['paired_business_passes']}/{summary['paired_business_cases']} pass expected persisted state/output and projected delta checks. {summary['raw_selected_rows_equal_cases']} selected-row checkpoints match raw; all other successful projections explicitly omit last_updated_stamp. This does not establish raw database equality.", '',
        f"Rust: {counts['pass']} passing, {counts['fail']} failing, {counts['skip']} skipped feature assertions across {len(suites)} specs. Includes the 100,000-row ETL acceptance scenario. These independently run assertions are not Java counterpart results.", '',
        'Evidence:', '',
        '- summary.json: verdicts, individual spec/case results, limitations, budget findings.',
        '- coverage-inventory.json: source service/spec inventory, potential named counterparts, actual execution status.',
        f'- {args.paired}/business-results.json: every request result, before/after selected rows, exact row diffs and business deltas.',
        f'- {evidence.relative_to(root)}/comparison.json: exact UTF-8/hex schema and typed canonical row/sequence differences, raw and approved verdicts separately.',
        f'- {args.paired}/provenance.json: source revisions, working-diff hashes, artifacts and approvals hashes.', '',
        'Choices for end review:', '',
        '- Retain intentional current schema/features and removed legacy statistics. Do not erase current functionality to make old Java match.',
        '- Keep phase gate failed; no new normalization, masks or approvals. Timestamp-free business projection is separately labeled.',
        '- Service output byte verdicts and numeric-result verdicts are separate in summary.json.',
        '- Do not claim complete process coverage: unrun and noncomparable services remain inventoried.',
        '- Component budget warnings and command exit codes remain recorded; no budgets changed.', '',
    ]
    (root / 'HANDOFF.md').write_text('\n'.join(text))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('suites','limitations')}, indent=2))


if __name__ == '__main__':
    main()
