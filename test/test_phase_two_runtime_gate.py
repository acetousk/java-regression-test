"""Phase 2 Change 14: runtime changes invalidate both phase-two entry points before launch."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime_identity import runtime_manifest, manifest_digest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeGateTests(unittest.TestCase):
    def test_entry_points_reject_changed_runtime_with_identical_artifacts(self):
        for name in ('phase_two_db', 'phase_two_rust'):
            spec = importlib.util.spec_from_file_location(name + '_gate_test', ROOT / 'tools' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for changed_side in ('java', 'rust'):
                with self.subTest(entry=name, side=changed_side), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    artifacts = {'java': root / 'moqui-framework/moqui.war',
                                 'rust': root / 'mr-moqui/target/debug/moqui'}
                    runtimes = {'java': root / 'moqui-framework/runtime', 'rust': root / 'mr-moqui/runtime'}
                    gate = {'passed': True, 'http_ready': True,
                            'verification': {'servers_started': True, 'shutdown_verified': True},
                            'shutdown': {side: {'errors': [], 'forced_kill': False,
                                               'missing_shutdown_markers': [], 'returncode': 0} for side in artifacts}}
                    for side, artifact in artifacts.items():
                        artifact.parent.mkdir(parents=True, exist_ok=True)
                        artifact.write_bytes(b'unchanged executable')
                        for folder in ('base-component', 'dev-component', 'component', 'conf'):
                            (runtimes[side] / folder).mkdir(parents=True)
                        (runtimes[side] / 'conf/profile.xml').write_text('<configuration/>')
                        gate[side] = {'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                      'runtime_source_sha256': manifest_digest(runtime_manifest(runtimes[side]))}
                    (root / 'gate.json').write_text(json.dumps(gate))
                    (root / 'differences.json').write_text('{"theme_resources":[],"full_text_indexes":[]}')
                    (runtimes[changed_side] / 'conf/profile.xml').write_text('<changed/>')
                    argv = [name, '--boot-gate', str(root / 'gate.json'), '--output', str(root / 'output')]
                    argv += (['--runtime', str(root / 'copy')] if name.endswith('rust') else
                             ['--differences', str(root / 'differences.json')])
                    with patch.object(module, 'ROOT', root), patch.object(sys, 'argv', argv), \
                            patch.object(module.subprocess, 'run') as launch, \
                            self.assertRaisesRegex(ValueError, 'Runtime source differs from boot gate: ' + changed_side):
                        module.main()
                    launch.assert_not_called()
                    self.assertFalse((root / 'output').exists())

    def test_mutation_after_gate_validation_cannot_certify_copied_runtime(self):
        import shutil
        from types import SimpleNamespace
        for name in ('phase_two_db', 'phase_two_rust'):
            spec = importlib.util.spec_from_file_location(name + '_race_test', ROOT / 'tools' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with self.subTest(entry=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifacts = {'java': root / 'moqui-framework/moqui.war',
                             'rust': root / 'mr-moqui/target/debug/moqui'}
                runtimes = {'java': root / 'moqui-framework/runtime', 'rust': root / 'mr-moqui/runtime'}
                gate = {'passed': True, 'http_ready': True,
                        'verification': {'servers_started': True, 'shutdown_verified': True},
                        'shutdown': {side: {'errors': [], 'forced_kill': False,
                                           'missing_shutdown_markers': [], 'returncode': 0} for side in artifacts}}
                for side, artifact in artifacts.items():
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    artifact.write_bytes(b'unchanged executable')
                    for folder in ('base-component', 'dev-component', 'component', 'conf'):
                        (runtimes[side] / folder).mkdir(parents=True)
                    (runtimes[side] / 'conf/MoquiDevConf.xml').write_text('<configuration/>')
                    gate[side] = {'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                  'runtime_source_sha256': manifest_digest(runtime_manifest(runtimes[side]))}
                (root / 'gate.json').write_text(json.dumps(gate))
                (root / 'differences.json').write_text('{"theme_resources":[],"full_text_indexes":[]}')
                copied = root / 'copy'
                shutil.copytree(runtimes['rust'], copied)
                validate = module.require_matching_boot_gate
                def validated_then_changed(*args, **kwargs):
                    result = validate(*args, **kwargs)
                    (runtimes['rust'] / 'conf/MoquiDevConf.xml').write_text('<changed/>')
                    (copied / 'conf/MoquiDevConf.xml').write_text('<changed/>')
                    return result
                argv = [name, '--boot-gate', str(root / 'gate.json'), '--output', str(root / 'output')]
                argv += (['--runtime', str(copied)] if name.endswith('rust') else
                         ['--differences', str(root / 'differences.json')])
                # Only Git provenance is mocked. Gate validation, copies, and digests remain real.
                def git_output(*args, **kwargs): return 'revision\n' if kwargs.get('text') else b''
                from contextlib import ExitStack
                with ExitStack() as stack:
                    stack.enter_context(patch.object(module, 'ROOT', root))
                    stack.enter_context(patch.object(sys, 'argv', argv))
                    stack.enter_context(patch.object(module, 'require_matching_boot_gate', side_effect=validated_then_changed))
                    launch = stack.enter_context(patch.object(module.subprocess, 'run'))
                    if name.endswith('db'):
                        stack.enter_context(patch.object(module, 'inventory'))
                        stack.enter_context(patch.object(module, 'load_controller', return_value=SimpleNamespace()))
                        stack.enter_context(patch.object(module.subprocess, 'check_output', side_effect=git_output))
                    with self.assertRaisesRegex(ValueError, 'Copied runtime source differs from boot gate: rust'):
                        module.main()
                    launch.assert_not_called()
