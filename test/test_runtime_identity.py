import importlib.util
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_identity import runtime_manifest, require_runtime_copy, manifest_digest


class RuntimeTests(unittest.TestCase):
    def test_matching_copy_and_modified_executable_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, copy = root / 'source', root / 'copy'
            for name in ('base-component', 'dev-component', 'component', 'conf', 'lib', 'classes', 'src'):
                (source / name).mkdir(parents=True)
            inputs = ('base-component/test.spec.js', 'component/service.xml', 'conf/MoquiDevConf.xml',
                      'lib/dependency.jar', 'classes/override.properties', 'src/RuntimeHelper.java',
                      'classes/target/Helper.class', 'component/example/target/service.xml',
                      'component/example/__pycache__/module.pyc', '.env',
                      'template/screen-macro/render.ftl', 'version.json')
            for name in inputs:
                (source / name).parent.mkdir(parents=True, exist_ok=True)
                (source / name).write_text('original')
            shutil.copytree(source, copy)
            expected = require_runtime_copy(copy, source)
            (copy / 'log').mkdir()
            (copy / 'log/moqui.log').write_text('mutable')
            self.assertEqual(require_runtime_copy(copy, source), expected)
            for name in inputs:
                (copy / name).write_text('stale')
                with self.subTest(name=name), self.assertRaises(ValueError): require_runtime_copy(copy, source)
                (copy / name).write_text('original')
            (copy / 'component/unexpected.xml').write_text('extra')
            with self.assertRaises(ValueError): require_runtime_copy(copy, source)

