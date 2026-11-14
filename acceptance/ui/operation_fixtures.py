"""Change 6: explicit fixtures for operations in disposable acceptance databases.

Setup SQL is evidence, not an exercised UI operation. This module never starts an
engine, sends a message, runs a job, or contacts a printer. Missing optional schema
is retained as failed fixture metadata, so unrelated operations can still run.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

STAMP = '2026-01-01 00:00:00'
PREFIX = 'Sample25'


def _literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bytes):
        return "decode('" + value.hex() + "','hex')"
    return "'" + str(value).replace("'", "''") + "'"


def _identifier(value):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', value):
        raise ValueError('Invalid fixture SQL identifier')
    return '"' + value + '"'


def _groups():
    """Dependency order; explicit IDs avoid consuming application sequences."""
    yield 'enum_type', 'enumeration_type', [{'enum_type_id': PREFIX+'Type', 'description': 'Sample25 fixtures'}], ['enum_type_id']
    yield 'enums', 'enumeration', [dict(enum_id=f'{PREFIX}Enum{i:02}', enum_type_id=PREFIX+'Type', description=f'Sample25 value {i:02}', sequence_num=i) for i in range(21)], ['enum_id']
    yield 'users', 'user_account', [dict(user_id=PREFIX+suffix, username='sample25.'+suffix.lower(), user_full_name='Sample25 '+suffix, disabled='N', require_password_change='N', email_address='sample25.'+suffix.lower()+'@example.invalid') for suffix in ['User', 'Other']], ['user_id']
    yield 'groups', 'user_group', [dict(user_group_id=f'{PREFIX}Group{i:02}', description=f'Sample25 group {i:02}') for i in range(21)], ['user_group_id']
    yield 'member', 'user_group_member', [dict(user_group_id=PREFIX+'Group00', user_id=PREFIX+'User', from_date=STAMP)], ['user_group_id', 'user_id', 'from_date']
    yield 'artifact_group', 'artifact_group', [dict(artifact_group_id=PREFIX+'Artifacts', description='Sample25 isolated artifacts')], ['artifact_group_id']
    yield 'artifact_member', 'artifact_group_member', [dict(artifact_group_id=PREFIX+'Artifacts', artifact_name='create#moqui.basic.Enumeration', artifact_type_enum_id='AT_SERVICE', name_is_pattern='N', inherit_authz='N')], ['artifact_group_id', 'artifact_name', 'artifact_type_enum_id']
    yield 'documents', 'data_document', [dict(data_document_id=PREFIX+('Document' if i == 0 else f'Document{i:02}'), document_name=f'Sample25 document {i:02}', primary_entity_name='moqui.basic.Enumeration', index_name='sample25') for i in range(21)], ['data_document_id']
    yield 'document_field', 'data_document_field', [dict(data_document_id=PREFIX+('Document' if i == 0 else f'Document{i:02}'), field_seq_id='01', field_path='enumId', field_name_alias='enumId', sequence_num=1) for i in range(21)], ['data_document_id', 'field_seq_id']
    yield 'messages', 'localized_message', [dict(original=f'Sample25 message {i:02}', locale='de', localized=f'Prüfung {i:02}') for i in range(21)], ['original', 'locale']
    yield 'entity_fields', 'localized_entity_field', [dict(entity_name='moqui.basic.Enumeration', field_name='description', pk_value=f'{PREFIX}Enum{i:02}', locale='de', localized=f'Wert {i:02}') for i in range(21)], ['entity_name', 'field_name', 'pk_value', 'locale']
    yield 'printer', 'network_printer', [dict(network_printer_id=PREFIX+'Printer', server_host='127.0.0.1', server_port=9, printer_name='Sample25Sink', description='No real printer: emulator required before sending')], ['network_printer_id']
    yield 'print_jobs', 'print_job', [dict(print_job_id=f'{PREFIX}Print{i:02}', created_date=STAMP, network_printer_id=PREFIX+'Printer', username='sample25.user', job_name=f'Sample25 print {i:02}', content_type='text/plain', document=('Sample25 document %02d\n' % i).encode(), copies=1, status_id='EsComplete', job_id=100+i, duplex='N', page_ranges='1-2') for i in range(21)], ['print_job_id']
    yield 'job', 'service_job', [dict(job_name=PREFIX+'Job', description='Sample25 manual fixture job', service_name='create#moqui.basic.Enumeration', paused='Y')], ['job_name']
    yield 'job_parameters', 'service_job_parameter', [dict(job_name=PREFIX+'Job', parameter_name=k, parameter_value=v) for k,v in {'enumId': PREFIX+'JobResult', 'enumTypeId': PREFIX+'Type', 'description': 'Sample25 job result'}.items()], ['job_name', 'parameter_name']
    yield 'job_runs', 'service_job_run', [dict(job_run_id=f'{PREFIX}Run{i:02}', job_name=PREFIX+'Job', user_id=PREFIX+'User', start_time=STAMP, end_time=STAMP, has_error='N', messages='Sample25 fixture; not an executed job') for i in range(21)], ['job_run_id']
    yield 'message_type', 'system_message_type', [dict(system_message_type_id=PREFIX+'MessageType', description='Sample25 fixture; no sender or consumer configured', content_type='application/json')], ['system_message_type_id']
    # Non-dispatchable rows support browsing. Sender/consumer actions need an emulator contract first.
    yield 'system_messages', 'system_message', [dict(system_message_id=f'{PREFIX}Message{i:02}', system_message_type_id=PREFIX+'MessageType', status_id='SmsgError', is_outgoing='N', init_date=STAMP, message_text='{"sample25":true}', fail_count=0) for i in range(21)], ['system_message_id']
    yield 'instance', 'instance_host', [dict(instance_host_id=PREFIX+'Host', host_protocol='http', host_address='127.0.0.1', admin_port=9)], ['instance_host_id']


def extra_fixture_groups(groups):
    # Phase 3, Change 12: explicit private inputs use the same owned-database guards.
    seen=set()
    for group in groups:
        label,table,records,keys=(group[name] for name in ('name','table','records','keys'))
        _identifier(label); _identifier(table)
        if label in seen or not records or not keys:
            raise ValueError('Fixture group requires unique name, records and keys')
        seen.add(label)
        columns=set(records[0])
        if not set(keys)<=columns:
            raise ValueError('Fixture keys must exist in every record')
        for column in columns: _identifier(column)
        for record in records:
            if set(record)!=columns or any(not (value is None or isinstance(value,(str,int,float))) for value in record.values()):
                raise ValueError('Fixture records require equal columns and scalar values')
        yield label,table,records,keys


def setup_operation_fixtures(ports, containers, evidence, selection, *, disposable=False, extra_groups=()):
    """Return per-side verified parameters, SQL proof, failures and prerequisites.

    Caller must pass exactly its newly created container IDs and affirm ownership.
    Setup failures are nonfatal per fixture, but are never reported as covered.
    The caller must skip dependent execution with an explicit fixture-failed result.
    """
    if not disposable or set(containers) != {'java', 'rust'} or set(ports) != set(containers):
        raise ValueError('Requires both owned disposable engines and containers')
    if any(not re.fullmatch(r'(?:phase-three|moqui-regression)-[A-Za-z0-9_.-]+', c) for c in containers.values()):
        raise ValueError('Container is not from the disposable acceptance lifecycle')
    if len(set(containers.values())) != 2:
        raise ValueError('Java and Rust must not share a database')
    selection = json.loads(Path(selection).read_text()) if isinstance(selection, (str, Path)) else selection
    if selection.get('frozen') is not True or len(selection.get('selected', [])) != 25:
        raise ValueError('Requires the frozen 25-screen selection')
    evidence = Path(evidence)
    directory = evidence / 'operation-fixtures'
    directory.mkdir(parents=True, exist_ok=False)
    groups=list(_groups())+list(extra_fixture_groups(extra_groups))
    if len({group[0] for group in groups})!=len(groups):
        raise ValueError('Extra fixture names must not replace built-in fixtures')
    metadata = {'setup_kind': 'fixture-only SQL; bypasses service and UI behavior',
                'scope': 'Representative operation inputs, not all possible input domains',
                'selected_keys': [x['key'] for x in selection['selected']],
                'sides': {}, 'unsupported_operations': [
                    {'operation': 'verifyUserAuthcFactorTotp parent transition', 'status': 'unresolved-service', 'reason': 'verify#UserAuthcFactorTotp is absent on both sides; embedded dialog uses validate#UserAuthcFactorCode instead'},
                    {'operation': 'reset password, send authentication codes, subscriber notifications', 'status': 'requires-local-emulator', 'reason': 'SMTP/SMS capture must be configured before execution; no external delivery authorized'},
                    {'operation': 'getServerPrinters or physical print submission', 'status': 'requires-local-emulator', 'reason': 'Fixture printer has no active endpoint; local IPP sink required'},
                    {'operation': 'system message send/consume and bulk variants', 'status': 'requires-local-emulator', 'reason': 'No sender/consumer is configured; fixture rows are browse-only and not evidence of dispatch'},
                    {'operation': 'password login as fixture user', 'status': 'requires-password-setup', 'reason': 'No password hash seeded; use the real password service before attempting credential login'}]}
    parameters = {
        'users': {'userId': [PREFIX+'User', PREFIX+'Other']},
        'groups': {'userGroupId': [PREFIX+'Group00']},
        'artifact_group': {'artifactGroupId': [PREFIX+'Artifacts']},
        'documents': {'dataDocumentId': [PREFIX+'Document']},
        'printer': {'networkPrinterId': [PREFIX+'Printer']},
        'print_jobs': {'printJobId': [PREFIX+'Print00']},
        'job': {'jobName': [PREFIX+'Job']},
        'job_runs': {'jobRunId': [PREFIX+'Run00']},
        'system_messages': {'systemMessageId': [PREFIX+'Message00']},
        'message_type': {'systemMessageTypeId': [PREFIX+'MessageType']},
        'instance': {'instanceHostId': [PREFIX+'Host']},
        'enums': {'enumId': [PREFIX+'Enum00'], 'entityName': ['moqui.basic.Enumeration']},
    }
    for side, container in containers.items():
        side_dir = directory / side
        side_dir.mkdir()
        result = {'requiredparams': {}, 'fixtures': [], 'failed': []}
        metadata['sides'][side] = result
        for label, table, records, keys in groups:
            columns = list(records[0])
            names = ','.join(map(_identifier, columns))
            values = ',\n'.join('('+','.join(_literal(row[c]) for c in columns)+')' for row in records)
            condition = ' OR '.join('('+' AND '.join(_identifier(k)+'='+_literal(row[k]) for k in keys)+')' for row in records)
            # Each table fixture is atomic. Never overwrite pre-existing IDs or silently ignore conflicts.
            sql = f'BEGIN;\nINSERT INTO public.{_identifier(table)} ({names}) VALUES {values};\nCOMMIT;\n'
            proof = f'SELECT row_to_json(r) FROM (SELECT * FROM public.{_identifier(table)} WHERE {condition} ORDER BY '+','.join(map(_identifier, keys))+') r;\n'
            (side_dir/(label+'.setup.sql')).write_text(sql)
            (side_dir/(label+'.proof.sql')).write_text(proof)
            command = ['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'moqui', '-d', 'moqui']
            completed = subprocess.run(command, input=sql.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            (side_dir/(label+'.stderr')).write_bytes(completed.stderr)
            item = {'name': label, 'table': table, 'expected_rows': len(records), 'returncode': completed.returncode, 'status': 'fixture-failed'}
            result['fixtures'].append(item)
            if completed.returncode == 0:
                read = subprocess.run(command, input=proof.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                (side_dir/(label+'.rows.jsonl')).write_bytes(read.stdout)
                (side_dir/(label+'.proof.stderr')).write_bytes(read.stderr)
                item.update(proof_returncode=read.returncode, proof_sha256=hashlib.sha256(read.stdout).hexdigest())
                try:
                    rows = [json.loads(line) for line in read.stdout.splitlines() if line]
                    valid = read.returncode == 0 and len(rows) == len(records)
                    # Validate explicit fixture values, not just row count. PostgreSQL bytea is hex text.
                    expected = [{k: ('\\x'+v.hex() if isinstance(v, bytes) else v.replace(' ', 'T') if v == STAMP else v) for k,v in row.items()} for row in records]
                    by_key = {tuple(str(row.get(k)) for k in keys): row for row in rows}
                    valid = valid and all(all(str(by_key.get(tuple(str(wanted[k]) for k in keys), {}).get(k)) == str(value) for k,value in wanted.items()) for wanted in expected)
                except (ValueError, TypeError):
                    valid = False
                if valid:
                    item['status'] = 'verified'
                    result['requiredparams'].update(parameters.get(label, {}))
            if item['status'] != 'verified':
                result['failed'].append(label)
            (directory/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    metadata['complete'] = all(not s['failed'] for s in metadata['sides'].values())
    metadata['pagination'] = {'fixture_rows': 21, 'requested_page_size': 10, 'note': 'Driver must verify actual page size and exercise next/previous; row count alone is not pagination coverage'}
    (directory/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    return metadata
