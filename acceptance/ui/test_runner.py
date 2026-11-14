"""Failure-injection tests for Change 2 orchestration guards (no live servers)."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('ui_runner',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class RunnerGuards(unittest.TestCase):
    def test_inventory_distinguishes_service_definitions_and_render_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for repo in ('moqui-framework','mr-moqui'):
                component=root/repo/'runtime/base-component/tools'
                screen=component/'screen/Tools/Service/Runner.xml'
                screen.parent.mkdir(parents=True)
                screen.write_text('<screen render-modes="vue,qvue"><parameter name="serviceName" required="true"/></screen>')
                service=component/'service/example/Services.xml'
                service.parent.mkdir(parents=True)
                service.write_text('<services><service verb="get" noun="Example"/></services>')
            with patch.object(r,'ROOT',root):
                result=r.inventory()
            self.assertEqual(result['shared_services'],['example.Services.get#Example'])
            self.assertEqual(result['screens']['rust']['tools/Tools/Service/Runner.xml']['render_modes'],['vue','qvue'])

    def good_gate(self):
        shutdown={side:{'errors':[],'forced_kill':False,'missing_shutdown_markers':[], 'returncode':0} for side in ('java','rust')}
        return {'passed':True,'http_ready':True,'verification':{'servers_started':True,'shutdown_verified':True},'shutdown':shutdown,
                'java':{'artifact_sha256':'a'*64},'rust':{'artifact_sha256':'b'*64}}

    def test_gate_rejects_false_incomplete_and_forced_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gate.json';good=self.good_gate()
            path.write_text(json.dumps(good));self.assertEqual(r.validate_boot_gate(path),good)
            invalid=[]
            x=copy.deepcopy(good);x['passed']=False;invalid.append(x)
            x=copy.deepcopy(good);x['shutdown']['rust']['forced_kill']=True;invalid.append(x)
            x=copy.deepcopy(good);del x['verification'];invalid.append(x)
            for x in invalid:
                path.write_text(json.dumps(x))
                with self.assertRaises(ValueError):r.validate_boot_gate(path)

    def test_optimized_python_cannot_skip_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gate.json';path.write_text('{"passed": false}')
            result=subprocess.run([sys.executable,'-O',str(Path(__file__).with_name('run.py')),'--boot-gate',str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Boot gate does not prove',result.stderr)

    def test_cleanup_removes_owned_container_when_verifier_throws(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.c,'stop_engines',side_effect=RuntimeError('injected verifier failure')), patch.object(r.subprocess,'run') as remove:
            self.assertFalse(r.cleanup({}, {}, {'java':'owned-test-container'}, Path(tmp)))
            self.assertEqual(remove.call_args.args[0],['docker','rm','-f','-v','owned-test-container'])
            self.assertTrue(json.loads((Path(tmp)/'cleanup.json').read_text())['errors'])

    def test_forced_kill_and_shutdown_errors_fail(self):
        report=self.good_gate()['shutdown'];self.assertTrue(r.shutdown_valid(report))
        report['rust']['forced_kill']=True;self.assertFalse(r.shutdown_valid(report))
        report['rust']['forced_kill']=False;report['rust']['errors']=['missing teardown'];self.assertFalse(r.shutdown_valid(report))

    def test_startup_failure_still_writes_failed_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate = root/'gate.json'
            gate.write_text(json.dumps(self.good_gate()))
            rules_bytes=b'{ "ui_presentation": [] }\n'
            (root/'approved-differences.json').write_bytes(rules_bytes)
            with patch.object(r, 'ROOT', root), patch.object(r, 'inventory', return_value={}), \
                    patch.object(r, 'runner_provenance', return_value={}), \
                    patch.object(r, 'require_matching_boot_gate', return_value=self.good_gate()) as matched_gate, \
                    patch.object(r, 'copy_verified_artifacts', return_value={}) as copied_artifacts, \
                    patch.object(r.time, 'strftime', return_value='injected-startup-failure'), \
                    patch.object(r.socket, 'socket'), \
                    patch.object(r.shutil, 'copytree', side_effect=OSError('injected copy failure')), \
                    patch.object(r, 'cleanup', return_value=False) as cleanup, \
                    patch.object(sys, 'argv', ['run.py', '--boot-gate', str(gate)]):
                with self.assertRaisesRegex(OSError, 'injected copy failure'):
                    r.main()
            cleanup.assert_called_once()
            self.assertEqual(copied_artifacts.call_args.args[2],root/'.runs/phase-three-ui/injected-startup-failure/artifacts')
            self.assertEqual(matched_gate.call_args.kwargs['runtimes'], {
                'java':root/'moqui-framework/runtime', 'rust':root/'mr-moqui/runtime'})
            self.assertEqual((root/'.runs/phase-three-ui/injected-startup-failure/comparison-differences.json').read_bytes(), rules_bytes)
            verdict=json.loads((root/'.runs/phase-three-ui/injected-startup-failure/verdict.json').read_text())
            self.assertFalse(verdict['passed'])
            self.assertFalse(verdict['shutdown_passed'])
            self.assertIsNone(verdict['capture_exit_code'])
            self.assertIn('injected copy failure', verdict['error'])

    def test_both_artifacts_checked_before_inventory_copy_database_or_engine(self):
        import hashlib
        for mismatch in (None, 'java', 'rust', 'java-runtime', 'rust-runtime'):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                gate = self.good_gate()
                for side, relative in [('java', 'moqui-framework/moqui.war'), ('rust', 'mr-moqui/target/debug/moqui')]:
                    artifact = root / relative
                    artifact.parent.mkdir(parents=True)
                    artifact.write_bytes(side.encode())
                    gate[side]['artifact_sha256'] = hashlib.sha256(side.encode()).hexdigest()
                    if side == mismatch: artifact.write_bytes(b'rebuilt')
                    runtime=root/relative.split('/')[0]/'runtime'
                    for name in ('base-component','dev-component','component','conf'):
                        (runtime/name).mkdir(parents=True)
                    gate[side]['runtime_source_sha256']=r.manifest_digest(r.runtime_manifest(runtime))
                    if side+'-runtime' == mismatch:
                        (runtime/'conf/changed.xml').write_text('<conf/>')
                path = root / 'gate.json'
                path.write_text(json.dumps(gate))
                with patch.object(r, 'ROOT', root), patch.object(sys, 'argv', ['runner', '--boot-gate', str(path)]), \
                        patch.object(r, 'inventory', side_effect=RuntimeError('matching pair reached inventory')) as inventory, \
                        patch.object(r.shutil, 'copytree') as copy_runtime, \
                        patch.object(r.subprocess, 'run') as database, patch.object(r.subprocess, 'Popen') as engine:
                    if mismatch:
                        error=('Runtime source differs from boot gate: '+mismatch.removesuffix('-runtime')
                               if mismatch.endswith('-runtime') else 'Artifact differs from boot gate: '+mismatch)
                        with self.assertRaisesRegex(ValueError, error): r.main()
                        inventory.assert_not_called()
                        self.assertFalse((root / '.runs').exists())
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'matching pair reached inventory'): r.main()
                        inventory.assert_called_once()
                    copy_runtime.assert_not_called()
                    database.assert_not_called()
                    engine.assert_not_called()

if __name__=='__main__':unittest.main()
