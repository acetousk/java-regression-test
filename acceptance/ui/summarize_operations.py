#!/usr/bin/env python3
"""Change 6: distinguish inventory, attempted actions, assertions and exact parity."""
import json
from pathlib import Path
import sys


def summarize(directory):
    directory = Path(directory)
    selection = json.loads((directory/'selection.json').read_text())
    result = json.loads((directory/'operations-result.json').read_text())
    rows = {s['key']: {'screen':s['key'], 'reported_cases':0, 'attempted_pairs':0,
                      'postconditions_completed_both':0, 'exact_passes':0,
                      'unexercised_cases':0, 'capture_error_pairs':0,
                      'equal_response_pairs':0, 'equal_dom_pairs':0,
                      'equal_rgba_pairs':0, 'equal_database_pairs':0} for s in selection['selected']}
    for case in result['operations']:
        key = case['id'].split(':html:',1)[0].split(':qapps:',1)[0]
        row = rows[key]
        row['reported_cases'] += 1
        row['exact_passes'] += case.get('passed') is True
        if not case.get('evidence'):
            row['unexercised_cases'] += 1
            continue
        row['attempted_pairs'] += 1
        metadata = []
        for side in ('java','rust'):
            path = directory/case['evidence']/(side+'.metadata.json')
            metadata.append(json.loads(path.read_text()) if path.exists() else {})
        case_metadata = json.loads((directory/case['evidence']/'case.json').read_text())
        operation = case_metadata['operation']
        steps = operation.get('steps', []) + operation.get('postconditions', [])
        interactive = any(step['action'] not in ('visible','text','value') for step in steps)
        last_action = max((i for i, step in enumerate(steps) if step['action'] not in ('visible','text','value')), default=-1)
        asserted = any(step['action'] in ('visible','text','value') and step.get('selector') != 'body' for step in steps[last_action+1:])
        row['postconditions_completed_both'] += interactive and asserted and all(m.get('exercised') is True for m in metadata)
        row['capture_error_pairs'] += any(m.get('errors') for m in metadata)
        for counter, channel in [('equal_response_pairs','http'),('equal_dom_pairs','dom'),
                                 ('equal_rgba_pairs','rgba'),('equal_database_pairs','database')]:
            row[counter] += case.get(channel,{}).get('equal') is True
    totals = {key:sum(row[key] for row in rows.values()) for key in next(iter(rows.values())) if key != 'screen'}
    return {'passed':result.get('passed') is True, 'sample_seed':selection['seed'],
            'scope':'Finite inventory candidates and representative inputs; overlapping field, transition and mode cases are not unique business operations.',
            'assertion_note':'Postconditions completed counts interactive cases with a specific assertion; baseline and generic body-visible checks are excluded. Field edits are not submissions. Capture/application errors remain separate, so this is not a functional certification.',
            'database_note':'Full serialized snapshots from live engines; no synchronized transaction barrier.',
            'expected_cases':result['expectedCount'], 'missing_cases':len(result['missing']),
            'totals':totals, 'screens':list(rows.values())}


if __name__ == '__main__':
    directory = Path(sys.argv[1])
    report = summarize(directory)
    (directory/'operations-summary.json').write_text(json.dumps(report,indent=2)+'\n')
    lines = ['# Sampled operation results', '', f"Exact parity: **{'PASS' if report['passed'] else 'FAIL'}**.", '', report['scope'], '', report['assertion_note'], '',
             '| Screen | Attempted pairs | Postconditions completed both | Exact passes | Unexercised cases |',
             '|---|---:|---:|---:|---:|']
    for row in report['screens']:
        lines.append('| '+row['screen']+' | '+' | '.join(str(row[key]) for key in ['attempted_pairs','postconditions_completed_both','exact_passes','unexercised_cases'])+' |')
    lines += ['', report['database_note'], '', 'Missing expected cases: '+str(report['missing_cases'])+'.', '']
    (directory/'operations-summary.md').write_text('\n'.join(lines))
    print(json.dumps({key:report[key] for key in ('passed','expected_cases','missing_cases','totals')},indent=2))
