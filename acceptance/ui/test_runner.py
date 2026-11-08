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
            with patch.object(r, 'ROOT', root), patch.object(r, 'inventory', return_value={}), \
                    patch.object(r, 'runner_provenance', return_value={}), \
                    patch.object(r.time, 'strftime', return_value='injected-startup-failure'), \
                    patch.object(r.socket, 'socket'), \
                    patch.object(r.shutil, 'copytree', side_effect=OSError('injected copy failure')), \
                    patch.object(r, 'cleanup', return_value=False) as cleanup, \
                    patch.object(sys, 'argv', ['run.py', '--boot-gate', str(gate)]):
                with self.assertRaisesRegex(OSError, 'injected copy failure'):
                    r.main()
            cleanup.assert_called_once()
            verdict=json.loads((root/'.runs/phase-three-ui/injected-startup-failure/verdict.json').read_text())
            self.assertFalse(verdict['passed'])
            self.assertFalse(verdict['shutdown_passed'])
            self.assertIsNone(verdict['capture_exit_code'])
            self.assertIn('injected copy failure', verdict['error'])

if __name__=='__main__':unittest.main()
