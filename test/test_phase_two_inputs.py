"""Phase 2 Change 11: reject invalid reviewed rules before any engine work."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phase_two_input_runner', ROOT / 'tools/phase_two_db.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class DifferenceInputTests(unittest.TestCase):
    def test_runtime_copy_keeps_nested_assets_named_like_run_state(self):
        # Phase 2 Change 12: a root snapshot directory is state; a nested save plugin is source.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'mr-moqui/runtime'
            nested = runtime / 'base-component/webroot/plugins/save'
            nested.mkdir(parents=True)
            (nested / 'plugin.js').write_bytes(b'asset')
            (runtime / 'save').mkdir()
            (runtime / 'save/database.dump').write_bytes(b'state')
            (runtime / '.env').write_bytes(b'local-config')
            with patch.object(runner, 'ROOT', root):
                checkout = runner.private_checkout('rust', root / 'run')
            self.assertEqual((checkout / 'runtime/base-component/webroot/plugins/save/plugin.js').read_bytes(), b'asset')
            self.assertFalse((checkout / 'runtime/save').exists())
            self.assertEqual((checkout / 'runtime/.env').read_bytes(), b'local-config')

    def test_invalid_rules_fail_before_gate_inventory_or_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rules = base / 'rules.json'
            for contents in ('{broken', '[]', '{}'):
                with self.subTest(contents=contents):
                    rules.write_text(contents)
                    argv = ['phase_two_db.py', '--boot-gate', str(base / 'gate.json'),
                            '--output', str(base / 'output'), '--differences', str(rules)]
                    with patch.object(sys, 'argv', argv), \
                            patch.object(runner, 'require_matching_boot_gate') as gate, \
                            patch.object(runner, 'inventory') as inventory, \
                            patch.object(runner, 'load_controller') as controller, \
                            contextlib.redirect_stderr(io.StringIO()), \
                            self.assertRaises(SystemExit) as error:
                        runner.main()
                    self.assertEqual(error.exception.code, 2)
                    gate.assert_not_called()
                    inventory.assert_not_called()
                    controller.assert_not_called()
                    self.assertFalse((base / 'output').exists())


if __name__ == '__main__':
    unittest.main()
