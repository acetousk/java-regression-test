"""Change 3: equal HTTP 200 error pages are evidence, never usable coverage."""
import json
from pathlib import Path
import tempfile
import unittest

from summarize import summarize


class CoverageReporting(unittest.TestCase):
    def test_saved_dom_render_error_invalidates_apparent_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            captures = []
            for name, dom in [('ready', '<p>Ready</p>'), ('broken', '<p>Error rendering screen</p>')]:
                evidence = run/name
                evidence.mkdir()
                for side in ('java', 'rust'):
                    (evidence/(side+'.response.html')).write_text('<html>shell</html>')
                    (evidence/(side+'.dom.html')).write_text(dom)
                captures.append({'key': name, 'route': '/'+name, 'evidence': name,
                                 'sides': {side: {'status': 200} for side in ('java', 'rust')},
                                 **{kind: {'equal': True} for kind in ('html', 'dom', 'pixels')}})
            (run/'summary.json').write_text(json.dumps({'captures': captures, 'unroutable': [],
                                                       'complete': True, 'rawParityPassed': True}))
            (run/'inventory.json').write_text(json.dumps({'screens': {'java': {}, 'rust': {}},
                                                         'shared': [], 'rust_only': [], 'java_only': []}))
            result = summarize(run)
            self.assertFalse(result['raw_parity_passed'])
            self.assertEqual(result['route_mode_pairs'], 2)
            self.assertEqual(result['usable_route_mode_pairs'], 1)
            self.assertEqual(result['raw_equal'], dict.fromkeys(('html', 'dom', 'pixels'), 2))
            self.assertEqual(result['usable_raw_equal'], dict.fromkeys(('html', 'dom', 'pixels'), 1))
            self.assertEqual(result['coverage_problems'][0]['route'], '/broken')
