"""Change 6: unfiltered application exports, with a consistent snapshot per engine."""
import contextlib
from evidence_archive import archive_file
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('ui_snapshot_controller', ROOT/'java-regression-test.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@contextlib.contextmanager
def exported_snapshot(container):
    # Phase 3, Change 13: keep the exporter alive until both captures have imported it.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['docker','exec','-i',container,'psql','-X','-qAt',
            '-v','ON_ERROR_STOP=1','-U','moqui','-d','moqui'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            process.stdin.write('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n')
            process.stdin.flush()
            if not select.select([process.stdout],[],[],15)[0]:
                raise TimeoutError('PostgreSQL snapshot export timed out')
            snapshot_id = process.stdout.readline().strip()
            if not re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+',snapshot_id):
                raise RuntimeError('PostgreSQL did not return an exported snapshot ID')
            yield snapshot_id
        finally:
            try:
                if process.poll() is None:
                    process.stdin.write('ROLLBACK;\n')
                    process.stdin.flush()
                    process.stdin.close()
                    process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                process.stdout.close()


def sequence_alignment(raw_path, structured_path):
    """Sequence counters are not MVCC data. Require both captures to observe equal state."""
    statements = re.findall(r"^SELECT pg_catalog\.setval\('((?:[^']|'')*)', (-?\d+), (true|false)\);$",
                           raw_path.read_text(), re.M)
    dumped = {name.replace("''", "'"):(int(value),called=='true') for name,value,called in statements}
    rows = [json.loads(line) for line in json.loads(structured_path.read_text())['records']]
    typed = {row['sequence']:(row['state']['last_value'],row['state']['is_called']) for row in rows if 'sequence' in row}
    return dumped == typed and len(dumped) == len(statements)


def capture(container, destination, structured):
    with exported_snapshot(container) as snapshot_id:
        # pg_dump includes every application schema, row, sequence and large object.
        with destination.open('wb') as output:
            subprocess.run(['docker','exec',container,'pg_dump','-U','moqui','-d','moqui',
                '--snapshot='+snapshot_id,'--restrict-key=MoquiOperation','--lock-wait-timeout=5000'],
                stdout=output,stderr=subprocess.PIPE,check=True,timeout=120)
        c.capture_snapshot(container, structured, snapshot_id=snapshot_id)
        count_sql = ("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET TRANSACTION SNAPSHOT '"+
            snapshot_id+"'; SELECT count(*) FROM pg_largeobject_metadata; ROLLBACK;")
        large_objects = int(subprocess.check_output(['docker','exec','-i',container,'psql','-X','-qAt',
            '-v','ON_ERROR_STOP=1','-U','moqui','-d','moqui'],input=count_sql,text=True,timeout=30).strip())
    return {'snapshotId':snapshot_id,'largeObjectCount':large_objects,
        'sequenceStateAligned':sequence_alignment(destination,structured),
        'rawSha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'structuredSha256':hashlib.sha256(structured.read_bytes()).hexdigest()}


def main():
    evidence, destination = map(Path, sys.argv[1:3])
    containers = json.loads((evidence/'operation-containers.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    structured_dir=destination/'structured'
    structured_dir.mkdir()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {side:pool.submit(capture,containers[side],destination/(side+'.sql'),structured_dir/(side+'.json')) for side in ('java','rust')}
        captures = {side:job.result() for side,job in jobs.items()}
    equal = (destination/'java.sql').read_bytes() == (destination/'rust.sql').read_bytes()
    rules_path=evidence/'comparison-differences.json'
    rules_bytes=rules_path.read_bytes()
    rules=json.loads(rules_bytes)
    approved_equal=c.snapshot_compare(structured_dir/'java.json',structured_dir/'rust.json',structured_dir,
        approved_differences=rules,emit_report=False)
    artifacts={path.name:archive_file(path) for path in sorted(structured_dir.iterdir()) if path.is_file()}
    (structured_dir/'artifact-manifest.json').write_text(json.dumps(artifacts,indent=2))
    complete=all(info['largeObjectCount']==0 and info['sequenceStateAligned'] for info in captures.values())
    approved={'status':'compared','complete':complete,'passed':complete and approved_equal,
        'rulesSha256':hashlib.sha256(rules_bytes).hexdigest(),'evidencePath':str(structured_dir),
        'artifactManifest':str(structured_dir/'artifact-manifest.json'),
        'contract':'Separate typed schema/row/sequence comparison with recorded rules; harness observation schema excluded. Row snapshots match raw pg_dump. Sequences must independently match captured dump state. Large objects must be absent. No paired transaction barrier.',
        'captures':captures}
    result = {'status':'compared','complete':True,'equal':equal,'exclusions':[],
        'evidencePath':str(destination),'approvedStructured':approved,
        'contract':'Unfiltered pg_dump plain application database export bytes. System catalogs are outside pg_dump scope. Each engine has its own exported snapshot; no cross-engine transaction barrier.'}
    (destination/'comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
