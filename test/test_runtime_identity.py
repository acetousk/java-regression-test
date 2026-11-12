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

    def test_runner_rejects_stale_runtime_before_process_launch(self):
        spec = importlib.util.spec_from_file_location('runtime_runner', ROOT / 'tools/phase_two_rust.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'private'
            (runtime / 'conf').mkdir(parents=True)
            (runtime / 'conf/MoquiDevConf.xml').write_text('<moqui-conf/>')
            argv = ['runner', '--output', str(root / 'output'), '--runtime', str(runtime), '--boot-gate', 'unused']
            with patch.object(sys, 'argv', argv), patch.object(runner, 'require_matching_boot_gate', return_value={}), patch.object(runner.subprocess, 'run') as launch:
                with self.assertRaises(ValueError): runner.main()
                launch.assert_not_called()

    def test_runner_records_matching_copy_and_refuses_mid_run_changes(self):
        import json
        from types import SimpleNamespace
        spec = importlib.util.spec_from_file_location('runtime_runner', ROOT / 'tools/phase_two_rust.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'mr-moqui/runtime'
            for name in ('base-component', 'dev-component', 'component', 'conf'):
                (source / name).mkdir(parents=True)
            (source / 'conf/MoquiDevConf.xml').write_text('<moqui-conf/>')
            binary = root / 'mr-moqui/target/debug/moqui'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'fixture')
            war = root / 'moqui-framework/moqui.war'
            war.parent.mkdir(parents=True)
            war.write_bytes(b'java fixture')
            gate = {side: {'artifact_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for side, path in {'java': war, 'rust': binary}.items()}
            gate['rust']['runtime_source_sha256'] = manifest_digest(runtime_manifest(source))
            for mutate in (False, True):
                runtime, output = root / str(mutate), root / ('output-' + str(mutate))
                shutil.copytree(source, runtime)
                def execute(command, **kwargs):
                    self.assertEqual(Path(command[0]), output / "artifacts/rust/moqui")
                    self.assertEqual(Path(command[0]).read_bytes(), b"fixture")
                    if mutate: (runtime / 'component/service.xml').write_text('changed')
                    return SimpleNamespace(returncode=0)
                argv = ['runner', '--output', str(output), '--runtime', str(runtime), '--boot-gate', 'unused']
                with patch.object(sys, 'argv', argv), patch.object(runner, 'ROOT', root), patch.object(runner, 'require_matching_boot_gate', return_value=gate), patch.object(runner, 'source_fingerprint', return_value={}), patch.object(runner.subprocess, 'run', side_effect=execute):
                    if mutate:
                        with self.assertRaises(ValueError): runner.main()
                        self.assertFalse((output / 'rust-commands.json').exists())
                    else:
                        self.assertEqual(runner.main(), 0)
                        provenance = json.loads((output / 'rust-provenance.json').read_text())
                        self.assertEqual(provenance['runtime_manifest'], runtime_manifest(runtime))
                        commands = json.loads((output / 'rust-commands.json').read_text())
                        self.assertEqual(len(commands), 3)
                        self.assertTrue(all(c['runtime_source_sha256'] == provenance['runtime_source_sha256'] for c in commands))
