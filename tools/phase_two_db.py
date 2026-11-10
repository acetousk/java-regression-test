#!/usr/bin/env python3
"""Change 1: isolated current-checkout business probes and strict database comparison.

The whole-database comparator retains raw and pre-existing approval verdicts.
Business projections remain diagnostic and omit generated last_updated_stamp.
With --data-clock, supplied timestamp proof and raw selected-row equality are
required as well; projections alone never establish whole-database equality. No checkout, build manifest, or approval file is edited.
"""
import argparse
import contextlib
import hashlib
from collections import Counter
from decimal import Decimal
import difflib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_controller():
    spec = importlib.util.spec_from_file_location('phase_two_controller', ROOT / 'java-regression-test.py')
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    return c


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, default=lambda x: {'decimal': str(x)} if isinstance(x, Decimal) else str(x)) + '\n')


def inventory(output):
    inventories = {}
    for side, repo in [('java', 'moqui-framework'), ('rust', 'mr-moqui')]:
        base = ROOT / repo
        roots = list((base / 'runtime').glob('*-component/*')) + list((base / 'runtime/component').glob('*'))
        if side == 'java':
            roots.append(base / 'framework')
        services = {}
        specs = []
        for component in roots:
            descriptor = component / 'component.xml'
            if descriptor.exists() and ET.parse(descriptor).getroot().get('disabled') == 'true':
                continue
            for path in sorted((component / 'service').rglob('*.xml')):
                try:
                    tree = ET.parse(path)
                except ET.ParseError:
                    continue
                prefix = '.'.join(path.relative_to(component / 'service').with_suffix('').parts)
                for service in tree.getroot().findall('service'):
                    name = prefix + '.' + service.get('verb', '') + ('#' + service.get('noun') if service.get('noun') else '')
                    services[name] = {'source': str(path.relative_to(base)), 'type': service.get('type', 'inline'), 'status': 'not_run'}
            for suite in ['test', 'acceptance']:
                for path in sorted((component / suite).rglob('*.spec.js')):
                    specs.append({'path': str(path.relative_to(base)), 'suite': suite, 'status': 'not_run'})
        inventories[side] = {'services': services, 'specs': specs, 'installed_components': [p.name for p in (base / 'runtime/component').iterdir() if p.is_dir()]}
    for side, other in [('java', 'rust'), ('rust', 'java')]:
        for name, item in inventories[side]['services'].items():
            item['counterpart'] = name in inventories[other]['services']
            if not item['counterpart']:
                item['comparison'] = 'no named counterpart; not comparable'
    dump(output / 'inventory.json', inventories)
    return inventories


def private_checkout(side, output):
    source = ROOT / ('moqui-framework' if side == 'java' else 'mr-moqui')
    target = output / 'engines' / side
    shutil.copytree(source / 'runtime', target / 'runtime', ignore=shutil.ignore_patterns('log', 'db', 'txlog', 'sessions', 'script-classes', 'save', '.env', 'install', 'opensearch'))
    if side == 'java':
        os.link(source / 'moqui.war', target / 'moqui.war')
    return target


def sql(container, query):
    return subprocess.check_output(['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'moqui', '-d', 'moqui'], input=query.encode('utf-8'))


def invoke(side, port, name, params, directory):
    """Two curl calls: bind authentication/session first, then authenticated POST."""
    directory.mkdir(parents=True, exist_ok=True)
    base = f'http://localhost:{port}'
    cookies, headers = directory / 'cookies', directory / 'headers'
    subprocess.run(['curl', '-sS', '--max-time', '60', '--user', 'john.doe:moqui', '-c', str(cookies), '-D', str(headers), base + '/apps/tools/Service/ServiceRun', '-o', str(directory / 'login.html')], check=True)
    text = headers.read_text()
    token = re.search(r'^x-csrf-token:\s*(\S+)', text, re.I | re.M)
    if not token:
        raise RuntimeError(f'{side}: no CSRF token; see {headers}')
    command = ['curl', '-sS', '--max-time', '60', '-b', str(cookies), '-c', str(cookies), '-H', 'Accept: application/json', '-H', 'X-Requested-With: XMLHttpRequest', '-H', 'X-CSRF-Token: ' + token[1], '-D', str(directory / 'post-headers'), '-o', str(directory / 'response'), '-w', '%{http_code}', base + '/apps/tools/Service/ServiceRun/run']
    for key, value in {'moquiFormName': 'ServiceParameters', 'serviceName': name, 'moquiSessionToken': token[1], 'submitButton': 'submitButton', **params}.items():
        command += ['--form-string', key + '=' + str(value)]
    log = directory.parents[2] / 'engines' / side / 'runtime/log/moqui.log'
    offset = log.stat().st_size
    status = subprocess.check_output(command, text=True)
    with log.open('rb') as stream:
        stream.seek(offset)
        service_log = stream.read().decode('utf-8', errors='replace')
    (directory / 'service.log').write_text(service_log)
    payload = json.loads((directory / 'response').read_text())
    service_errors = payload.get('errors') or payload.get('errorMessages') or payload.get('error') or []
    return {'service_errors': service_errors, 'request_succeeded': 200 <= int(status) < 400 and not service_errors, 'http_status': int(status), 'body': (directory / 'response').read_text(),
            'service_outputs': dict(re.findall(r'^==> ([^:]+): (.*)$', service_log, re.M))}


def business(ports, containers, output, canonical, clock=None):
    # Explicit IDs preserve row correspondence. Neither clocks nor whole DBs are normalized.
    cases = [
        ('create-type', 'create#moqui.basic.EnumerationType', {'enumTypeId': 'PHASE2_TYPE', 'description': 'Phase two enum type'}, 'enumeration_type', 'enum_type_id', 'PHASE2_TYPE', 'description', 'Phase two enum type'),
        ('create-enum', 'create#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'enumTypeId': 'PHASE2_TYPE', 'description': 'Created', 'sequenceNum': '7'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Created'),
        ('duplicate-enum-refused', 'create#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'enumTypeId': 'PHASE2_TYPE', 'description': 'Must not overwrite'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Created'),
        ('update-enum', 'update#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'description': 'Updated'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Updated'),
        ('store-enum', 'store#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM', 'description': 'Stored'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', 'description', 'Stored'),
        ('delete-enum', 'delete#moqui.basic.Enumeration', {'enumId': 'PHASE2_ENUM'}, 'enumeration', 'enum_id', 'PHASE2_ENUM', None, None),
        ('delete-type', 'delete#moqui.basic.EnumerationType', {'enumTypeId': 'PHASE2_TYPE'}, 'enumeration_type', 'enum_type_id', 'PHASE2_TYPE', None, None),
        ('create-unit-a', 'create#moqui.basic.Uom', {'uomId': 'PHASE2_M', 'uomTypeEnumId': 'UT_LENGTH_MEASURE', 'description': 'Phase two metres'}, 'uom', 'uom_id', 'PHASE2_M', 'description', 'Phase two metres'),
        ('create-unit-b', 'create#moqui.basic.Uom', {'uomId': 'PHASE2_CM', 'uomTypeEnumId': 'UT_LENGTH_MEASURE', 'description': 'Phase two centimetres'}, 'uom', 'uom_id', 'PHASE2_CM', 'description', 'Phase two centimetres'),
        ('create-conversion', 'create#moqui.basic.UomConversion', {'uomConversionId': 'PHASE2_CONV', 'uomId': 'PHASE2_M', 'toUomId': 'PHASE2_CM', 'conversionFactor': '100', 'fromDate': '2020-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
        ('convert-forward', 'org.moqui.impl.BasicServices.convert#Uom', {'uomId': 'PHASE2_M', 'toUomId': 'PHASE2_CM', 'amount': '2', 'effectiveDate': '2026-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
        ('convert-reverse', 'org.moqui.impl.BasicServices.convert#Uom', {'uomId': 'PHASE2_CM', 'toUomId': 'PHASE2_M', 'amount': '200', 'effectiveDate': '2026-01-01 00:00:00'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 100),
        ('update-conversion', 'org.moqui.impl.BasicServices.update#UomConversion', {'uomConversionId': 'PHASE2_CONV', 'conversionFactor': '200'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', 'conversion_factor', 200),
        ('delete-conversion', 'delete#moqui.basic.UomConversion', {'uomConversionId': 'PHASE2_CONV'}, 'uom_conversion', 'uom_conversion_id', 'PHASE2_CONV', None, None),
        ('delete-unit-b', 'delete#moqui.basic.Uom', {'uomId': 'PHASE2_CM'}, 'uom', 'uom_id', 'PHASE2_CM', None, None),
        ('delete-unit-a', 'delete#moqui.basic.Uom', {'uomId': 'PHASE2_M'}, 'uom', 'uom_id', 'PHASE2_M', None, None),
    ]
    results = []
    for label, service, params, table, pk, key, field, expected in cases:
        # Change 5: only advance after the previous pair and its SQL readback have completed.
        if clock is not None:
            clock.advance(clock.epoch_ms + 1)
        record = {'case': label, 'service': service, 'engines': {}}
        for side in ('java', 'rust'):
            dest = output / 'business' / label / side
            dest.mkdir(parents=True)
            query = f"SELECT COALESCE(json_agg(t ORDER BY t.{pk}),'[]') FROM {table} t WHERE {pk}='{key}'"
            before_bytes = sql(containers[side], query)
            (dest / 'before.json').write_bytes(before_bytes)
            before = json.loads(before_bytes, parse_float=Decimal)
            try:
                response = invoke(side, ports[side], service, params, dest)
                after_bytes = sql(containers[side], query)
                (dest / 'after.json').write_bytes(after_bytes)
                after = json.loads(after_bytes, parse_float=Decimal)
                ok = (len(after) == 1 and after[0][field] == expected) if field else not after
                if label in ('convert-forward', 'convert-reverse'):
                    converted = response['service_outputs'].get('convertedAmount')
                    ok = ok and converted is not None and Decimal(converted) == (200 if label == 'convert-forward' else 2) and before == after
                if label == 'duplicate-enum-refused':
                    ok = ok and before_bytes == after_bytes and bool(response['service_errors'] or response['http_status'] >= 400)
                else:
                    ok = ok and response['request_succeeded']
                stamp_proof = None
                if clock is not None and (label.startswith(('create-', 'update-', 'store-'))):
                    persisted = sql(containers[side], f"SELECT extract(epoch FROM last_updated_stamp)*1000 FROM {table} WHERE {pk}='{key}'").decode().strip()
                    stamp_proof = {'expected_epoch_ms': clock.epoch_ms, 'persisted_epoch_ms': persisted,
                                   'passed': bool(persisted) and Decimal(persisted) == clock.epoch_ms}
                    ok = ok and stamp_proof['passed']
                record['engines'][side] = {'data_clock_proof': stamp_proof, 'before': before, 'after': after, 'before_utf8': before_bytes.decode('utf-8'), 'after_utf8': after_bytes.decode('utf-8'), 'before_sha256': hashlib.sha256(before_bytes).hexdigest(), 'after_sha256': hashlib.sha256(after_bytes).hexdigest(), 'expected_state_passed': ok, **response}
            except Exception as error:
                record['engines'][side] = {'error': str(error), 'expected_state_passed': False, 'after': []}
        a, b = [record['engines'][s]['after'] for s in ('java', 'rust')]
        raw = [record['engines'][side].get('after_utf8') for side in ('java', 'rust')]
        record['raw_selected_rows_equal'] = all(x is not None for x in raw) and raw[0].encode('utf-8') == raw[1].encode('utf-8')
        record['raw_selected_rows_encoding'] = 'Ordered PostgreSQL json_agg output, UTF-8 including psql trailing newline; no parsing or normalization'
        record['semantic_decimal_encoding'] = 'Decimal diagnostic values serialize as {decimal: exact-text}; original bytes retained in before.json/after.json'
        projected = [[{k: v for k, v in row.items() if k != 'last_updated_stamp'} for row in rows] for rows in (a, b)]
        record['projection_exclusions'] = ['last_updated_stamp']
        record['projected_selected_rows_equal'] = projected[0] == projected[1]
        record['business_deltas'] = {}
        for side, detail in record['engines'].items():
            def bag(rows):
                return Counter(json.dumps(canonical({k:v for k,v in row.items() if k != 'last_updated_stamp'}), sort_keys=True, separators=(',', ':')) for row in rows)
            before, after = bag(detail.get('before', [])), bag(detail['after'])
            record['business_deltas'][side] = {'removed': sorted((before-after).elements()), 'added': sorted((after-before).elements())}
        record['projected_deltas_equal'] = record['business_deltas']['java'] == record['business_deltas']['rust']
        record['passed'] = all(r['expected_state_passed'] for r in record['engines'].values()) and record['projected_selected_rows_equal'] and record['projected_deltas_equal'] and (clock is None or record['raw_selected_rows_equal'])
        record['data_clock_enabled'] = clock is not None
        record['raw_rows_required_for_pass'] = clock is not None
        record['exact_row_diff'] = ''.join(difflib.unified_diff((raw[0] or '').splitlines(True), (raw[1] or '').splitlines(True), fromfile='java', tofile='rust'))
        results.append(record)
        dump(output / 'business-results.json', results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-clock', action='store_true', help='Change 5: supply and prove shared file data time; require raw selected-row equality')
    parser.add_argument('--data-clock-epoch-ms', type=int, help='Initial supplied time; defaults to one real UTC epoch sampled before both boots')
    parser.add_argument('--java-home', help='Java 21+ home; otherwise run with mise exec')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output, 0o700)
    inventory(output)
    provenance = {}
    for side, repo, artifact in [('java', 'moqui-framework', 'moqui.war'), ('rust', 'mr-moqui', 'target/debug/moqui')]:
        checkout = ROOT / repo
        with (checkout / artifact).open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        provenance[side] = {'revision': subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip(), 'artifact_sha256': checksum, 'tracked_diff_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', str(checkout), 'diff', 'HEAD'])).hexdigest()}
    provenance['approvals_sha256'] = hashlib.sha256((ROOT / 'approved-differences.json').read_bytes()).hexdigest()
    dump(output / 'provenance.json', provenance)
    c = load_controller()
    clock = None
    if args.data_clock:
        from acceptance.ui.data_clock import SuppliedDataClock
        clock = SuppliedDataClock(output / 'supplied-data-clock', args.data_clock_epoch_ms if args.data_clock_epoch_ms is not None else time.time_ns() // 1_000_000)
        original_demo_conf = c.demo_conf
        def isolated_clock_conf(source, destination, *values):
            original_demo_conf(source, destination, *values)
            tree = ET.parse(destination)
            root = tree.getroot()
            for name, value in {**clock.environment(), 'scheduled_job_check_time': '0'}.items():
                node = root.find(f"default-property[@name='{name}']")
                if node is None:
                    node = ET.SubElement(root, 'default-property', {'name': name})
                node.set('value', value)
            service = root.find('service-facade')
            if service is None:
                service = ET.SubElement(root, 'service-facade')
            service.set('scheduled-job-check-time', '0')
            tree.write(destination)
        c.demo_conf = isolated_clock_conf
    elif args.data_clock_epoch_ms is not None:
        parser.error('--data-clock-epoch-ms requires --data-clock')
    # Change 1: imported harness gets a private ROOT; never replace .runs/build.json.
    c.ROOT = output
    (output / '.runs').mkdir(exist_ok=True)
    checkouts = {side: private_checkout(side, output) for side in ('java', 'rust')}
    c.rust_artifact = lambda _: ROOT / 'mr-moqui/target/debug/moqui'
    evidence = output / 'database'
    summary = {'phase': 2, 'scope': 'installed framework only; no Mantle or ERP components installed', 'raw_whole_database_equal': False}
    def ready(ports):
        summary['evidence'] = str(evidence)
        # The harness owns its random container names. Resolve only the unique
        # ephemeral DB ports in this run's generated configs; never reuse a DB.
        candidates = subprocess.check_output(['docker', 'ps', '--filter', 'name=moqui-regression-', '--format', '{{.Names}}'], text=True).splitlines()
        containers = {}
        for side in ports:
            conf = ET.parse(evidence / f'{side}-demo.xml').getroot()
            db_port = conf.find("default-property[@name='entity_ds_port']").get('value')
            matches = [name for name in candidates if name.endswith('-' + side) and subprocess.check_output(['docker', 'port', name, '5432/tcp'], text=True).strip() == '127.0.0.1:' + db_port]
            if len(matches) != 1:
                raise RuntimeError(f'Expected exactly one disposable {side} DB for this run')
            containers[side] = matches[0]
        if clock is not None:
            from acceptance.ui.data_clock_proof import prove_data_clock
            summary['data_clock_proof'] = prove_data_clock(ports, containers, evidence, clock, disposable=True)
        summary['business'] = business(ports, containers, output, c.canonical, clock)
    options = SimpleNamespace(java_port=28080, rust_port=28081, boot_timeout=600, shutdown_timeout=120, java_home=args.java_home,
                              java_checkout=checkouts['java'], rust_checkout=checkouts['rust'], deterministic=False,
                              keep_databases=False, exclude_rust_only=False, source_root=ROOT)
    try:
        with (output / 'controller.log').open('w') as log, contextlib.redirect_stdout(log):
            c.boot_and_stop(options, evidence_dir=evidence, readiness_check=ready)
    except (Exception, SystemExit) as error:
        summary['controller_result'] = f'{type(error).__name__}: {error}'
    if 'evidence' in summary:
        evidence = Path(summary['evidence'])
        report = json.loads((evidence / 'comparison.json').read_text()) if (evidence / 'comparison.json').exists() else {}
        summary['raw_whole_database_equal'] = bool(report.get('schema_dump_equal') and report.get('row_and_sequence_values_equal'))
        summary['whole_database_equal_with_existing_approvals'] = report.get('comparison_passed', False)
        summary['shutdown'] = json.loads((evidence / 'shutdown.json').read_text())
    summary['business_all_passed'] = bool(summary.get('business')) and all(x['passed'] for x in summary['business'])
    dump(output / 'result.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('business',)}, indent=2))
    return 0 if summary['raw_whole_database_equal'] and summary['business_all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
