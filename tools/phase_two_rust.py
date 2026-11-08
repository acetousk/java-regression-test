#!/usr/bin/env python3
"""Change 2: reproduce the 43 selected Rust business/acceptance specs without building."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INITIAL = ['Units', 'ResourceOwners', 'ChatKeys', 'AdminAccessServices']
EXPANDED = {
    'framework': ['XmppServices', 'WebPush', 'Voicemail', 'Voice', 'Transfer', 'SqlServices',
                  'SipDevice', 'RingGroup', 'ResourceSearchExclusions', 'RecentAuth', 'PushDevice',
                  'Ivr', 'EdgeVoice', 'DocumentExpression', 'ChatKeyBackup', 'Calls', 'CallRecording',
                  'CallQueue', 'CallHandling', 'CallEncryption', 'CallCaptions', 'BusinessDatasets', 'AdminSessions'],
    'tools': ['Etl', 'DocumentExport'],
    'example': ['Files', 'Wiki', 'GitHosting', 'Chat', 'MailClient'],
    'basic-comms': ['BasicComms', 'BasicCommsTexts', 'BasicCommsSync', 'BasicCommsInbox',
                    'BasicCommsFiles', 'BasicCommsEncrypted', 'BasicCommsChat', 'BasicCommsCalls'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True, help='Private copied runtime from phase_two_db.py')
    args = parser.parse_args()
    output, runtime = args.output.resolve(), args.runtime.resolve()
    if not (runtime / 'conf/MoquiDevConf.xml').is_file():
        parser.error('runtime must contain conf/MoquiDevConf.xml')
    if runtime == (ROOT / 'mr-moqui/runtime').resolve():
        parser.error('Use a private copied runtime, not the shared checkout runtime')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = ROOT / 'mr-moqui/target/debug/moqui'
    with binary.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    selected = ','.join(f'{component}/{spec}' for component, specs in EXPANDED.items() for spec in specs)
    plans = [
        ('rust-business', 'rust-junit', ['framework', '--spec', ','.join(INITIAL)]),
        ('rust-expanded', 'rust-expanded-junit', ['--spec', selected, '--coverage-report', str(output / 'rust-service-coverage.txt')]),
        ('rust-acceptance', 'rust-acceptance-junit', ['tools', '--acceptance', '--spec', 'EtlLoad']),
    ]
    for name, junit, _ in plans:
        if (output / (name + '.log')).exists() or (output / junit).exists():
            parser.error('Existing Rust run evidence would be overwritten; choose a new output directory')
    results = []
    for name, junit, selectors in plans:
        command = [str(binary), 'test', *selectors, '--junit', str(output / junit), '--keep']
        with (output / (name + '.log')).open('w') as log:
            run = subprocess.run(command, env={**os.environ, 'MOQUI_RUNTIME': str(runtime)}, stdout=log, stderr=subprocess.STDOUT)
        results.append({'command': command, 'runtime': str(runtime), 'binary_sha256': checksum,
                        'returncode': run.returncode, 'log': str(output / (name + '.log'))})
        (output / 'rust-commands.json').write_text(json.dumps(results, indent=2) + '\n')
        print(f'{name}: exit {run.returncode}', flush=True)
    return int(any(r['returncode'] != 0 for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
