"""Change 6: unfiltered application exports, with a consistent snapshot per engine."""
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def capture(container, destination):
    # pg_dump includes every application schema, row, sequence and large object.
    # PostgreSQL system catalogs are outside its export contract; no application filter is used.
    with destination.open('wb') as output:
        subprocess.run(['docker','exec',container,'pg_dump','-U','moqui','-d','moqui',
                        '--restrict-key=MoquiOperation','--lock-wait-timeout=5000'],
                       stdout=output,stderr=subprocess.PIPE,check=True,timeout=120)


if __name__ == '__main__':
    evidence, destination = map(Path, sys.argv[1:3])
    containers = json.loads((evidence/'operation-containers.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(capture,containers[side],destination/(side+'.sql')) for side in ('java','rust')]
        for future in futures:
            future.result()
    equal = (destination/'java.sql').read_bytes() == (destination/'rust.sql').read_bytes()
    result = {'status':'compared','complete':True,'equal':equal,'exclusions':[],
              'evidencePath':str(destination),
              'contract':'Unfiltered pg_dump plain application database export bytes. PostgreSQL system catalogs are outside pg_dump scope. Each engine has its own consistent snapshot; no cross-engine transaction barrier.'}
    (destination/'comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
