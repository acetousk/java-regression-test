"""Change 5: successful HTTP alone must never mark a fixture usable."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('ui_fixtures',Path(__file__).with_name('fixtures.py'))
f=importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

class FixtureVerification(unittest.TestCase):
    def test_missing_database_record_refuses_coverage_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def curl(command, **kwargs):
                output=Path(command[command.index('-o')+1])
                output.write_text('{}')
                if '-D' in command:
                    Path(command[command.index('-D')+1]).write_text('X-CSRF-Token: test-token\n')
            with patch.object(f.subprocess,'run',side_effect=curl), patch.object(f.subprocess,'check_output',return_value=''):
                with self.assertRaisesRegex(RuntimeError,'did not persist'):
                    f.create_document({'java':38080},{'java':'owned'},root)
            self.assertFalse((root/'fixture-parameters.json').exists())

if __name__=='__main__':unittest.main()
