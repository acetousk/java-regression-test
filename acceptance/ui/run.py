#!/usr/bin/env python3
"""Change 2: isolated acceptance UI capture; never reuse another phase's runtime."""
import argparse
import signal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('controller', ROOT / 'java-regression-test.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

def inventory():
    found = {}
    for side, repo in [('java', 'moqui-framework'), ('rust', 'mr-moqui')]:
        sources = list((ROOT / repo / 'runtime').glob('*component/*/screen/**/*.xml'))
        if side == 'java':
            sources += list((ROOT / repo / 'framework/screen').rglob('*.xml'))
        screens = {}
        for p in sources:
            try:
                tree = ET.parse(p).getroot()
            except ET.ParseError:
                continue
            if tree.tag != 'screen':
                continue
            rel = str(p).split('/screen/', 1)[1]
            component = p.parts[p.parts.index('screen') - 1]
            key = component + '/' + rel
            route = None
            if component == 'webroot' and rel.startswith('webroot/'):
                route = '/' + rel[len('webroot/'): -4]
            elif component == 'tools' and rel.split('/')[0].split('.')[0] in ('System', 'Tools'):
                parts = rel[:-4].split('/')
                parts[0] = parts[0].lower()
                route = '/apps/' + '/'.join(parts)
            screens[key] = {'source': str(p.relative_to(ROOT)), 'route': route,
                            'render_modes': [mode.strip() for mode in tree.get('render-modes', '').split(',') if mode.strip()],
                            'required_parameters': [n.get('name') for n in tree.findall('parameter') if n.get('required') == 'true']}
        found[side] = screens
    # Change 5: select real shared service definitions, never service-directory links.
    services = {}
    for side, repo in [('java', 'moqui-framework'), ('rust', 'mr-moqui')]:
        paths = list((ROOT/repo/'runtime').glob('*component/*/service/**/*.xml'))
        if side == 'java':
            paths += list((ROOT/repo/'framework/service').rglob('*.xml'))
        names = set()
        for path in paths:
            try:
                tree = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            if tree.tag != 'services':
                continue
            prefix = str(path).split('/service/', 1)[1][:-4].replace('/', '.')
            names.update(prefix+'.'+node.get('verb')+'#'+node.get('noun', '')
                         for node in tree.findall('service') if node.get('verb'))
        services[side] = names
    shared = sorted(found['rust'].keys() & found['java'].keys())
    return {'screens': found, 'shared': shared,
            'shared_services': sorted(services['java'] & services['rust']),
            'rust_only': sorted(found['rust'].keys() - found['java'].keys()),
            'java_only': sorted(found['java'].keys() - found['rust'].keys())}

# Change 9: share readiness/shutdown validation with phase-two entry points.
from boot_gate import shutdown_valid, validate_boot_gate

def runner_provenance():
    # Change 2: capture the acceptance implementation as well as engine diffs.
    sources = sorted(Path(__file__).parent.glob('*')) + [ROOT/'java-regression-test.py']
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources if path.is_file()}

def cleanup(processes, logs, containers, evidence):
    report, failures = {}, []
    try:
        report = c.stop_engines(processes, {s:evidence/(s+'-boot.log') for s in processes}, 120)
    except BaseException as error:
        failures.append('shutdown verification: '+repr(error))
    finally:
        # A verifier failure cannot leave owned processes or databases running.
        for side, process in processes.items():
            try:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        failures.append(side+': fallback forced kill')
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
            except ProcessLookupError:
                pass
            except Exception as error:
                failures.append(side+': cleanup '+repr(error))
        for log in logs.values():
            try: log.close()
            except Exception as error: failures.append('log close: '+repr(error))
        for name in containers.values():
            try:
                subprocess.run(['docker','rm','-f','-v',name],stdout=subprocess.DEVNULL,check=True,timeout=30)
            except Exception as error: failures.append('container cleanup: '+repr(error))
        (evidence/'shutdown.json').write_text(json.dumps(report,indent=2))
        (evidence/'cleanup.json').write_text(json.dumps({'errors':failures},indent=2))
    return shutdown_valid(report) and not failures

def validate_operation_inputs(selection_path, plan_path):
    # Change 6: reject accidental sample drift before creating any runtime.
    selection = json.loads(selection_path.read_text())
    plan = json.loads(plan_path.read_text())
    selected = selection.get('selected', [])
    keys = [row['key'] for row in selected]
    ranked = sorted(selection['eligible'], key=lambda key: hashlib.sha256(
        (selection['seed']+'\0'+key).encode()).hexdigest())
    if (selection.get('frozen') is not True or len(set(selection['eligible'])) != len(selection['eligible'])
            or len(set(keys)) != 25 or keys != ranked[:25]):
        raise ValueError('Operation sample is not the frozen reproducible 25-screen selection')
    if len(plan.get('screens', [])) != 25 or set(row['key'] for row in plan.get('screens', [])) != set(keys):
        raise ValueError('Operation plan does not inventory all 25 selected screens')
    for row in selected:
        if not row.get('routes') or any(not route.startswith(('/apps/', '/qapps/')) for route in row['routes']):
            raise ValueError('Invalid sample route')
    return selection, plan

def isolate_operation_scheduler(conf):
    # Change 6: background retention must not delete paired operation fixtures mid-run.
    tree = ET.parse(conf)
    root = tree.getroot()
    prop = root.find("default-property[@name='scheduled_job_check_time']")
    if prop is None:
        prop = ET.SubElement(root, 'default-property', {'name':'scheduled_job_check_time'})
    prop.set('value', '0')
    facade = root.find('service-facade')
    if facade is None:
        facade = ET.SubElement(root, 'service-facade')
    facade.set('scheduled-job-check-time', '0')
    tree.write(conf, encoding='unicode')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-gate',type=Path,help='Passed gate.json produced by check_boot.py')
    parser.add_argument('--inventory-only',action='store_true')
    # Change 6: sample operation execution shares the boot-gated disposable lifecycle.
    parser.add_argument('--operation-plan',type=Path)
    parser.add_argument('--selection',type=Path)
    parser.add_argument('--java-port',type=int,default=38080)
    parser.add_argument('--rust-port',type=int,default=38081)
    args=parser.parse_args()
    if not args.operation_plan and (args.java_port,args.rust_port)!=(38080,38081):
        parser.error('Custom ports require --operation-plan')
    if not args.inventory_only and args.boot_gate is None:
        parser.error('--boot-gate is required for capture')
    if args.operation_plan and not args.selection:
        parser.error('--selection is required with --operation-plan')
    if args.operation_plan:
        validate_operation_inputs(args.selection, args.operation_plan)
    gate=validate_boot_gate(args.boot_gate) if not args.inventory_only else None
    evidence = ROOT / '.runs/phase-three-ui' / time.strftime('%Y%m%d-%H%M%S')
    evidence.mkdir(parents=True, mode=0o700)
    inv = inventory()
    (evidence/'inventory.json').write_text(json.dumps(inv, indent=2))
    if args.inventory_only:
        print(evidence)
        return
    (evidence/'boot-gate.json').write_text(json.dumps(gate,indent=2))
    (evidence/'boot-gate-source.txt').write_text(str(args.boot_gate.resolve()))
    (evidence/'runner-provenance.json').write_text(json.dumps(runner_provenance(),indent=2))
    ports = {'java': args.java_port, 'rust': args.rust_port}
    if len(set(ports.values())) != 2 or any(not 1 <= p <= 65535 for p in ports.values()):
        parser.error('Engine ports must be distinct and between 1 and 65535')
    (evidence/'ports.json').write_text(json.dumps(ports))
    containers, processes, logs = {}, {}, {}
    password, crypt = secrets.token_hex(24), secrets.token_hex(32)
    result = None
    failure = None
    # Change 7: both disposable engines consume the same data-time assignment.
    # This is not a transaction barrier and never normalizes retained timestamps.
    from data_clock import SuppliedDataClock
    clock = SuppliedDataClock(evidence/'data-clock.millis', int(time.time() * 1000)) if args.operation_plan else None
    clock_env = clock.environment() if clock else {}
    try:
        for port in ports.values():
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
        for side, repo in [('java', 'moqui-framework'), ('rust', 'mr-moqui')]:
            checkout = ROOT/repo
            runtime = evidence/side/'runtime'
            shutil.copytree(checkout/'runtime', runtime, ignore=lambda folder, names: [n for n in names if n == '.git' or (Path(folder) == checkout/'runtime' and n in {'db','log','txlog','sessions','jackrabbit','sftp','script-classes'})])
            name = 'phase-three-' + evidence.name + '-' + side
            containers[side] = name
            subprocess.run(['docker','run','-d','--rm','--name',name,'-p','127.0.0.1::5432','--tmpfs','/var/lib/postgresql','-e','POSTGRES_USER=moqui','-e','POSTGRES_DB=moqui','-e','POSTGRES_PASSWORD',c.POSTGRES_IMAGE,'-c','max_prepared_transactions=100'], env={**os.environ,'POSTGRES_PASSWORD':password}, check=True, stdout=subprocess.DEVNULL)
            dbport = int(subprocess.check_output(['docker','port',name,'5432/tcp'],text=True).strip().rsplit(':',1)[1])
            deadline = time.monotonic()+60
            while subprocess.run(['docker','exec',name,'pg_isready','-U','moqui'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
                if time.monotonic()>deadline: raise TimeoutError(name)
                time.sleep(.2)
            conf = evidence/(side+'-conf.xml')
            c.demo_conf(runtime/'conf/MoquiDevConf.xml', conf, dbport,password,ports[side],crypt)
            if args.operation_plan:
                isolate_operation_scheduler(conf)
                (evidence/'operation-environment.json').write_text(json.dumps({
                    'scheduled_job_check_time':0,
                    'reason':'Keep fixture prestate stable; automatic scheduled execution is not covered by this run'}))
            overrides = {n.get('name'):n.get('value') for n in ET.parse(conf).getroot().findall('default-property')}
            artifact = checkout/('moqui.war' if side=='java' else 'target/debug/moqui')
            with artifact.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            (evidence/(side+'-provenance.json')).write_text(json.dumps({'artifact':str(artifact),'sha256':digest,'revision':subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip(),'untracked_sha256':{name:hashlib.sha256((checkout/name).read_bytes()).hexdigest() for name in subprocess.check_output(['git','-C',str(checkout),'ls-files','--others','--exclude-standard'],text=True).splitlines() if (checkout/name).is_file()},'tracked_diff_sha256':hashlib.sha256(subprocess.check_output(['git','-C',str(checkout),'diff','HEAD','--'])).hexdigest(),'dirty':subprocess.check_output(['git','-C',str(checkout),'status','--porcelain'],text=True)},indent=2))
            if digest != gate[side]['artifact_sha256']:
                raise ValueError(side+' artifact differs from the passed boot gate')
            if side=='java':
                cmd=['java',f'-Dmoqui.runtime={runtime}',f'-Dmoqui.conf={conf}','-jar',str(artifact),f'port={ports[side]}','no-run-es']
            else:
                cmd=[str(artifact),'--conf',str(conf),'--port',str(ports[side]),'--https-port','off','--no-run-es','-D','create-or-update=true']
            logs[side]=(evidence/(side+'-boot.log')).open('wb')
            processes[side]=subprocess.Popen(cmd,cwd=evidence/side,env={**os.environ,**overrides,**clock_env,'MOQUI_RUNTIME':str(runtime),'MOQUI_CONF':str(conf),'MOQUI_FRAMEWORK':str(runtime/'base-component/framework'),'TZ':'UTC'},stdout=logs[side],stderr=subprocess.STDOUT,start_new_session=True)
        c.wait_for_ports(processes,ports,600,{s:evidence/(s+'-boot.log') for s in processes})
        if clock:
            from acceptance.ui.data_clock_proof import prove_data_clock
            prove_data_clock(ports, containers, evidence, clock, disposable=True)
        from fixtures import create_document
        create_document(ports, containers, evidence)
        print('CAPTURE '+str(evidence),flush=True)
        if args.operation_plan:
            from operation_fixtures import setup_operation_fixtures
            selection=json.loads(args.selection.read_text())
            shutil.copyfile(args.selection,evidence/'selection.json')
            shutil.copyfile(args.operation_plan,evidence/'operation-plan.json')
            (evidence/'operation-containers.json').write_text(json.dumps(containers))
            setup_operation_fixtures(ports,containers,evidence,selection,disposable=True)
            capture_script='operations.cjs'
        else:
            capture_script='capture.cjs'
        result=subprocess.run(['node',str(ROOT/'acceptance/ui'/capture_script),str(evidence)],env={**os.environ,'OPERATION_PYTHON':sys.executable})
        (evidence/'capture-exit.json').write_text(json.dumps({'exit_code':result.returncode}))
        if (evidence/'operations-result.json').exists():
            subprocess.run([sys.executable,str(ROOT/'acceptance/ui/summarize_operations.py'),str(evidence)],check=True)
        if (evidence/'summary.json').exists():
            with (evidence/'result-output.json').open('w') as report:
                subprocess.run([sys.executable,str(ROOT/'acceptance/ui/summarize.py'),str(evidence)],stdout=report,check=True)
    except BaseException as error:
        failure = repr(error)
        raise
    finally:
        shutdown_ok=cleanup(processes,logs,containers,evidence)
        # An incomplete run must leave an explicit failed verdict, even on interruption.
        (evidence/'verdict.json').write_text(json.dumps({'capture_exit_code':result.returncode if result else None,
            'error':failure,'shutdown_passed':shutdown_ok,
            'passed':failure is None and result is not None and result.returncode==0 and shutdown_ok},indent=2))
    print(evidence,flush=True)
    sys.exit(0 if result.returncode == 0 and shutdown_ok else 1)

if __name__=='__main__': main()
