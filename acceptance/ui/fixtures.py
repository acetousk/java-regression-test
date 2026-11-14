"""Change 5: explicit UI record fixture, confined to the runner's disposable databases."""
import json
import re
import subprocess


def create_document(ports, containers, evidence):
    records = {}
    for side, port in ports.items():
        directory = evidence/'fixtures'/side
        directory.mkdir(parents=True)
        cookies, headers = directory/'cookies', directory/'headers'
        base = f'http://localhost:{port}'
        # Bind authentication and CSRF to one session; the POST never authenticates again.
        subprocess.run(['curl', '--fail-with-body', '-sS', '--max-time', '60', '--user', 'john.doe:moqui', '-c', str(cookies), '-D', str(headers), base+'/apps/tools/Service/ServiceRun', '-o', str(directory/'login.html')], check=True)
        token = re.search(r'^x-csrf-token:\s*(\S+)', headers.read_text(), re.I | re.M)
        if not token:
            raise RuntimeError(side+': fixture login supplied no CSRF token')
        values = {'moquiFormName':'ServiceParameters', 'serviceName':'create#moqui.entity.document.DataDocument',
                  'dataDocumentId':'UiAcceptanceDocument', 'documentName':'UI acceptance document',
                  'primaryEntityName':'moqui.basic.Enumeration', 'indexName':'uiacceptance',
                  'moquiSessionToken':token[1], 'submitButton':'submitButton'}
        command = ['curl', '--fail-with-body', '-sS', '--max-time', '60', '-b', str(cookies), '-H', 'Accept: application/json',
                   '-H', 'X-Requested-With: XMLHttpRequest', '-H', 'X-CSRF-Token: '+token[1],
                   '-o', str(directory/'response.json'), base+'/apps/tools/Service/ServiceRun/run']
        for key, value in values.items():
            command += ['--form-string', key+'='+value]
        subprocess.run(command, check=True)
        payload = json.loads((directory/'response.json').read_text())
        if payload.get('errors') or payload.get('errorMessages') or payload.get('error'):
            raise RuntimeError(side+': fixture service errors; see '+str(directory))
        row = subprocess.check_output(['docker', 'exec', containers[side], 'psql', '-U', 'moqui', '-d', 'moqui', '-At', '-c',
            "SELECT data_document_id || '|' || primary_entity_name FROM data_document WHERE data_document_id = 'UiAcceptanceDocument'"], text=True).strip()
        if row != 'UiAcceptanceDocument|moqui.basic.Enumeration':
            raise RuntimeError(side+': fixture service did not persist the requested record')
        records[side] = {'service':values['serviceName'], 'verified_row':row}
        logs = [evidence/side/'runtime/log/moqui.log', evidence/(side+'-boot.log')]
        (directory/'service-log.txt').write_text('\n'.join(line for log in logs if log.exists()
            for line in log.read_text(errors='replace').splitlines() if 'DataDocument' in line or 'ServiceRun/run' in line or 'ERROR' in line))
    (evidence/'fixture-evidence.json').write_text(json.dumps(records, indent=2))
    (evidence/'fixture-parameters.json').write_text(json.dumps({'dataDocumentId':['UiAcceptanceDocument']}))
