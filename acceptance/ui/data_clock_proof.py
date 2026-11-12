"""Prove supplied timestamps through real services and PostgreSQL reads on disposable engines."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from .data_clock import verify_persisted_millis

PROOF_ID = 'UiAcceptanceClockProof'


def _invoke(side, port, directory, service, name):
    directory.mkdir(parents=True, exist_ok=True)
    cookies, headers = directory / 'cookies', directory / 'headers'
    # Phase 2 Change 16: match the paired probes' IPv4 client address.
    base = f'http://127.0.0.1:{port}'
    # Change 5: two requests per invocation, binding POST CSRF to the authenticated GET session.
    subprocess.run(['curl', '--fail-with-body', '-sS', '--max-time', '60',
                    '--user', os.environ.get('MOQUI_USER', 'john.doe') + ':' + os.environ.get('MOQUI_PASSWORD', 'moqui'),
                    '-c', str(cookies), '-D', str(headers), base + '/apps/tools/Service/ServiceRun',
                    '-o', str(directory / 'login.html')], check=True)
    token = re.search(r'^x-csrf-token:\s*(\S+)', headers.read_text(), re.I | re.M)
    if not token:
        raise RuntimeError(side + ': clock proof login did not supply CSRF')
    values = {'moquiFormName': 'ServiceParameters', 'serviceName': service,
              'dataDocumentId': PROOF_ID, 'documentName': name,
              'moquiSessionToken': token[1], 'submitButton': 'submitButton'}
    if service.startswith('create#'):
        values.update(primaryEntityName='moqui.basic.Enumeration', indexName='clockproof')
    command = ['curl', '--fail-with-body', '-sS', '--max-time', '60', '-b', str(cookies),
               '-H', 'Accept: application/json', '-H', 'X-Requested-With: XMLHttpRequest',
               '-H', 'X-CSRF-Token: ' + token[1], '-o', str(directory / 'response.json'),
               base + '/apps/tools/Service/ServiceRun/run']
    for key, value in values.items():
        command.extend(['--form-string', key + '=' + value])
    subprocess.run(command, check=True)
    payload = json.loads((directory / 'response.json').read_text())
    if not isinstance(payload, dict) or any(payload.get(k) for k in ('errors', 'errorMessages', 'error')):
        raise RuntimeError(side + ': clock proof service reported failure; private response retained')


def _query(container):
    # Integer conversion is permitted only when the persisted value has exactly millisecond precision.
    query = """SELECT json_build_object('name', document_name,
        'stamp_ms', CASE WHEN extract(epoch FROM last_updated_stamp)*1000 =
            trunc(extract(epoch FROM last_updated_stamp)*1000)
            THEN (extract(epoch FROM last_updated_stamp)*1000)::bigint ELSE NULL END)
        FROM data_document WHERE data_document_id = 'UiAcceptanceClockProof'"""
    output = subprocess.check_output(['docker', 'exec', container, 'psql', '-U', 'moqui', '-d', 'moqui',
                                      '-At', '-v', 'ON_ERROR_STOP=1', '-c', query], text=True)
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError('clock proof expected exactly one persisted document')
    return rows[0]


def _startup_stamp(container):
    # This seed has no explicit lastUpdatedStamp in either installed definition.
    query = "SELECT extract(epoch FROM last_updated_stamp)*1000 FROM enumeration_type WHERE enum_type_id='ComparisonOperator'"
    output = subprocess.check_output(['docker', 'exec', container, 'psql', '-U', 'moqui', '-d', 'moqui',
                                      '-At', '-v', 'ON_ERROR_STOP=1', '-c', query], text=True).strip()
    from decimal import Decimal
    value = Decimal(output)
    if value != value.to_integral_value():
        raise RuntimeError('startup seed stamp has sub-millisecond precision')
    return int(value)


def _visit_sequence_stamp(container):
    """Phase 2 Change 15: sequence-bank writes must use the same assigned data time."""
    query = "SELECT extract(epoch FROM last_updated_stamp)*1000 FROM sequence_value_item WHERE seq_name='moqui.server.Visit'"
    output = subprocess.check_output(['docker', 'exec', container, 'psql', '-U', 'moqui', '-d', 'moqui',
                                      '-At', '-v', 'ON_ERROR_STOP=1', '-c', query], text=True).strip()
    from decimal import Decimal
    values = output.splitlines()
    if len(values) != 1:
        raise RuntimeError('clock proof expected one Visit sequence-bank row')
    value = Decimal(values[0])
    if not value.is_finite() or value != value.to_integral_value():
        raise RuntimeError('sequence-bank stamp has sub-millisecond precision or is nonfinite')
    return int(value)


def _verify_seed_definition():
    root = Path(__file__).resolve().parents[2]
    for relative in ('moqui-framework/framework/data/EntityTypeData.xml',
                     'mr-moqui/runtime/base-component/framework/data/EntityTypeData.xml'):
        nodes = [node for node in ET.parse(root / relative).getroot()
                 if node.tag == 'moqui.basic.EnumerationType' and node.get('enumTypeId') == 'ComparisonOperator']
        if len(nodes) != 1 or nodes[0].get('lastUpdatedStamp') is not None:
            raise RuntimeError('startup seed is missing or explicitly timestamped; cannot prove loader clock')


def prove_data_clock(ports, containers, evidence, clock, *, disposable=False):
    """Run after ready, before ordinary fixtures; leaves one proof document in each owned database.

    Engines must be quiescent and scheduled work disabled before this function starts. It advances the
    shared clock once between completed create/update pairs. It does not establish transaction pairing.
    """
    if not disposable or set(ports) != {'java', 'rust'} or set(containers) != {'java', 'rust'}:
        raise ValueError('clock proof requires both disposable engines')
    if len(set(containers.values())) != 2 or any(not re.fullmatch(r'(?:phase-three-[A-Za-z0-9_-]+|moqui-regression-[A-Za-z0-9_.-]+)', c)
                                               for c in containers.values()):
        raise ValueError('clock proof refuses non-owned database containers')
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports.values()):
        raise ValueError('invalid local proof port')
    directory = evidence / 'data-clock-proof'
    directory.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'scope': 'Service create/update last_updated_stamp equals supplied epoch milliseconds',
              'transaction_pairing': False, 'assignments': [],
              'optimistic_lock': {'verified': False, 'reason': 'Selected shared DataDocument entity has no optimistic-lock declaration; no stale rejection claimed.'}}
    try:
        _verify_seed_definition()
        startup = {side: [_startup_stamp(containers[side])] for side in ('java', 'rust')}
        verify_persisted_millis(clock.epoch_ms, startup)
        report['startup_seed'] = {'entity': 'moqui.basic.EnumerationType', 'key': 'ComparisonOperator',
                                  'supplied_epoch_ms': clock.epoch_ms, 'persisted_epoch_ms': startup, 'passed': True}
        for index, verb in enumerate(('create', 'update')):
            if index:
                clock.advance(clock.epoch_ms + 1)
            with clock.paired_operation() as expected:
                service = verb + '#moqui.entity.document.DataDocument'
                name = 'Clock proof ' + verb
                with ThreadPoolExecutor(max_workers=2) as pool:
                    jobs = [pool.submit(_invoke, side, ports[side], directory / verb / side, service, name)
                            for side in ('java', 'rust')]
                    for job in jobs:
                        job.result()
                rows = {side: _query(containers[side]) for side in ('java', 'rust')}
                if any(row.get('name') != name for row in rows.values()):
                    raise RuntimeError('clock proof service did not persist the requested document state')
                verify_persisted_millis(expected, {side: [row.get('stamp_ms')] for side, row in rows.items()})
                report['assignments'].append({'operation': verb, 'supplied_epoch_ms': expected, 'persisted': rows})
                if index == 0:
                    sequence = {side: [_visit_sequence_stamp(containers[side])] for side in ('java', 'rust')}
                    verify_persisted_millis(expected, sequence)
                    report['sequence_bank'] = {'entity': 'moqui.entity.SequenceValueItem', 'key': 'moqui.server.Visit',
                                               'supplied_epoch_ms': expected, 'persisted_epoch_ms': sequence, 'passed': True}
        report['passed'] = True
    finally:
        (directory / 'proof.json').write_text(json.dumps(report, indent=2) + '\n')
        # Private logs prove invocation separately from HTTP success; never publish cookies or raw logs.
        for side in ('java', 'rust'):
            lines = []
            for log in (evidence / (side + '-boot.log'), evidence / side / 'runtime/log/moqui.log'):
                if log.exists():
                    lines.extend(line for line in log.read_text(errors='replace').splitlines()
                                 if 'UiAcceptanceClockProof' in line or 'ServiceRun/run' in line)
            (directory / (side + '-service.log')).write_text('\n'.join(lines))
    return report
