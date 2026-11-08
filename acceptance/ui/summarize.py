#!/usr/bin/env python3
"""Change 3: keep raw equality separate from usable-screen coverage."""
import difflib
import json
from pathlib import Path
import sys

def summarize(run):
    summary = json.loads((run/'summary.json').read_text())
    inventory = json.loads((run/'inventory.json').read_text())
    captures = summary['captures']
    # Login is captured before authentication; do not count the later skip as uncovered.
    uncovered = [item for item in summary['unroutable'] if not (
        inventory['screens']['rust'].get(item['key'], {}).get('route') == '/Login'
        and any(c['route'] == '/Login' for c in captures))]
    problems = []
    valid_captures = []
    for capture in captures:
        reasons = []
        if capture.get('missingParameters'):
            reasons.append('missing record parameters: '+', '.join(capture['missingParameters']))
        for side, result in capture['sides'].items():
            if result.get('errorPage'): reasons.append(side+': login/error page instead of target')
            if result.get('unexpectedRedirect'): reasons.append(side+': unexpected redirect')
            if result.get('error'): reasons.append(side+': capture failed')
            if result.get('status', 0) != 200: reasons.append(side+': HTTP '+str(result.get('status')))
            if result.get('readinessError'): reasons.append(side+': client readiness timeout')
            if result.get('pageErrors'): reasons.append(side+': client exception')
            if result.get('httpErrors'): reasons.append(side+': failed resource request')
            body = run/capture['evidence']/(side+'.response.html')
            dom = run/capture['evidence']/(side+'.dom.html')
            content = b'\n'.join(p.read_bytes() for p in (body,dom) if p.exists())
            if b'Required parameter missing' in content:
                reasons.append(side+': parameter-error response')
            if any(marker in content for marker in (b'Error rendering',b'Exception in render')):
                reasons.append(side+': rendering-error response/DOM')
        if reasons: problems.append({'route': capture['route'], 'reasons': reasons})
        else: valid_captures.append(capture)
        for kind in ('response','dom'):
            paths = [run/capture['evidence']/(side+'.'+kind+'.html') for side in ('java','rust')]
            if all(p.exists() for p in paths):
                # Diagnostic only; raw comparison already used the complete byte buffers.
                diff = difflib.unified_diff(paths[0].read_text(errors='replace').splitlines(True), paths[1].read_text(errors='replace').splitlines(True), fromfile='java', tofile='rust')
                (paths[0].parent/(kind+'.diff')).write_text(''.join(diff))
    result = {'change': 3, 'raw_parity_passed': summary.get('rawParityPassed',False) and not problems and not uncovered,
              'capture_complete': summary.get('complete',False),
              'inventory': {'rust_screens':len(inventory['screens']['rust']), 'java_screens':len(inventory['screens']['java']),
                            'shared_screens':len(inventory['shared']), 'rust_only':len(inventory['rust_only']), 'java_only':len(inventory['java_only'])},
              'route_mode_pairs': len(captures),
              'usable_route_mode_pairs': len(valid_captures),
              'usable_shared_screens': len({c['key'] for c in valid_captures}),
              'current_only_screens_without_java_counterpart': inventory['rust_only'],
              'qvt_pairs': sum('qvt' in c for c in captures),
              'qvt_equal_pairs': sum(c.get('qvt',{}).get('equal',False) for c in captures),
              'raw_equal': {kind:sum(c.get(kind,{}).get('equal',False) for c in captures) for kind in ('html','dom','pixels')},
              'usable_raw_equal': {kind:sum(c.get(kind,{}).get('equal',False) for c in valid_captures) for kind in ('html','dom','pixels')},
              'pixel_equal_routes': [c['route'] for c in captures if c.get('pixels',{}).get('equal')],
              'coverage_problems':problems, 'uncovered_screens':uncovered,
              'limitations':['No business fixtures created; detail IDs are chosen from values in rendered links shared by both engines.',
                             'A successful capture does not establish complete business workflow coverage.',
                             'Response bodies are browser transport-decoded bytes; DOM is browser serialization.',
                             'No tolerances, masks, approvals or normalizations. UI evolution and infrastructure/session entropy remain raw mismatches.',
                             'Email/special-purpose screens need dedicated scenarios. Only installed components are inventoried.']}
    (run/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(summarize(Path(sys.argv[1])),indent=2))
