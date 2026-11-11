#!/usr/bin/env python3
"""Change 2: reproduce the 45 selected Rust business/acceptance specs without building."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from boot_gate import require_matching_boot_gate
from runtime_identity import require_runtime_copy, runtime_manifest, manifest_digest

INITIAL = ['Units', 'ResourceOwners', 'ChatKeys', 'AdminAccessServices']
EXPANDED = {
    'framework': ['XmppServices', 'WebPush', 'Voicemail', 'Voice', 'Transfer', 'SqlServices',
                  'SipDevice', 'RingGroup', 'ResourceSearchExclusions', 'RecentAuth', 'PushDevice',
                  'Ivr', 'EdgeVoice', 'DocumentExpression', 'ChatKeyBackup', 'Calls', 'CallRecording',
                  'CallQueue', 'CallHandling', 'CallEncryption', 'CallCaptions', 'BusinessDatasets', 'AdminSessions'],
    'tools': ['Etl', 'DocumentExport', 'ConfReload', 'Constitution'],
    'example': ['Files', 'Wiki', 'GitHosting', 'Chat', 'MailClient'],
    'basic-comms': ['BasicComms', 'BasicCommsTexts', 'BasicCommsSync', 'BasicCommsInbox',
                    'BasicCommsFiles', 'BasicCommsEncrypted', 'BasicCommsChat', 'BasicCommsCalls'],
}


def run_plans(output):
    selected = ','.join(f'{component}/{spec}' for component, specs in EXPANDED.items() for spec in specs)
    return [
        ('rust-business', 'rust-junit', ['framework', '--spec', ','.join(INITIAL)]),
        ('rust-expanded', 'rust-expanded-junit', ['--spec', selected, '--coverage-report', str(output / 'rust-service-coverage.txt')]),
        ('rust-acceptance', 'rust-acceptance-junit', ['tools', '--acceptance', '--spec', 'EtlLoad']),
    ]


def expected_suites():
    return {
        'rust-junit': ['framework.' + name for name in INITIAL],
        'rust-expanded-junit': [component + '.' + name for component, specs in EXPANDED.items() for name in specs],
        'rust-acceptance-junit': ['tools.EtlLoad'],
    }


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint(checkout):
    return {'revision': subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip(),
            'tracked_diff_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', str(checkout), 'diff', 'HEAD'])).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-gate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True, help='Private copied runtime from phase_two_db.py')
    args = parser.parse_args()
    # Change 7: both artifacts must match the same successful phase-one context.
    gate = require_matching_boot_gate(args.boot_gate, {
        'java': ROOT / 'moqui-framework/moqui.war',
        'rust': ROOT / 'mr-moqui/target/debug/moqui'})
    output, runtime = args.output.resolve(), args.runtime.resolve()
    if not (runtime / 'conf/MoquiDevConf.xml').is_file():
        parser.error('runtime must contain conf/MoquiDevConf.xml')
    if runtime == (ROOT / 'mr-moqui/runtime').resolve():
        parser.error('Use a private copied runtime, not the shared checkout runtime')
    # Change 10: fingerprint what MOQUI_RUNTIME will execute, not just its checkout.
    runtime_source = require_runtime_copy(runtime, ROOT / 'mr-moqui/runtime')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = ROOT / 'mr-moqui/target/debug/moqui'
    with binary.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    plans = run_plans(output)
    for name, junit, _ in plans:
        if (output / (name + '.log')).exists() or (output / junit).exists():
            parser.error('Existing Rust run evidence would be overwritten; choose a new output directory')
    provenance = {'runtime_manifest': runtime_source, 'runtime_source_sha256': manifest_digest(runtime_source),
                  'source': source_fingerprint(ROOT / 'mr-moqui'),
                  'binary_sha256': checksum, 'expected_suites': expected_suites(),
                  'boot_gate': gate, 'boot_gate_source': str(args.boot_gate.resolve())}
    (output / 'rust-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    results = []
    for name, junit, selectors in plans:
        if runtime_manifest(runtime) != runtime_source:
            raise ValueError('Runtime source changed before suite launch')
        command = [str(binary), 'test', *selectors, '--junit', str(output / junit), '--keep']
        with (output / (name + '.log')).open('w') as log:
            run = subprocess.run(command, env={**os.environ, 'MOQUI_RUNTIME': str(runtime)}, stdout=log, stderr=subprocess.STDOUT)
        if runtime_manifest(runtime) != runtime_source:
            raise ValueError('Runtime source changed during suite execution')
        results.append({'runtime_source_sha256': manifest_digest(runtime_source), 'command': command, 'runtime': str(runtime), 'binary_sha256': checksum,
                        'junit_sha256': {p.name: sha256(p) for p in sorted((output / junit).glob('TEST-*.xml'))},
                        'expected_suites': expected_suites()[junit],
                        'returncode': run.returncode, 'log': str(output / (name + '.log'))})
        (output / 'rust-commands.json').write_text(json.dumps(results, indent=2) + '\n')
        print(f'{name}: exit {run.returncode}', flush=True)
    return int(any(r['returncode'] != 0 for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
