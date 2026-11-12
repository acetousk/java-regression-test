"""Change 7: shared fail-closed phase-one prerequisite checks."""
import hashlib
import json
from pathlib import Path
import shutil


def copy_verified_artifacts(artifacts, checksums, destination):
    """Phase 1, Change 4: launch private verified copies, never mutable build outputs."""
    copied = {}
    for side, source in artifacts.items():
        if side not in ('java', 'rust') or side not in checksums:
            raise ValueError('Artifact copy requires a known engine and checksum')
        target = Path(destination) / side / ('moqui.war' if side == 'java' else 'moqui')
        target.parent.mkdir(parents=True, exist_ok=True)
        with Path(source).open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024*1024)
        with target.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != checksums[side]:
            raise ValueError('Artifact changed while preparing launch: ' + side)
        target.chmod(0o500 if side == 'rust' else 0o400)
        copied[side] = target
    return copied

def shutdown_valid(report):
    return (set(report) == {'java', 'rust'} and all(
        item.get('errors') == [] and item.get('forced_kill') is False
        and item.get('missing_shutdown_markers') == []
        and item.get('returncode') in ((0, 143, -15) if side == 'java' else (0,))
        for side, item in report.items()))

def validate_boot_gate(path):
    return validate_boot_gate_data(json.loads(path.read_text()))

def validate_boot_gate_data(gate):
    verification = gate.get('verification', {})
    if not (gate.get('passed') is True and gate.get('http_ready') is True
            and gate.get('runtime_errors', []) == []
            and gate.get('artifact_errors', []) == []
            and verification.get('servers_started') is True
            and verification.get('shutdown_verified') is True
            and shutdown_valid(gate.get('shutdown', {}))):
        raise ValueError('Boot gate does not prove readiness and graceful shutdown')
    for side in ('java', 'rust'):
        digest = gate.get(side, {}).get('artifact_sha256', '')
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Boot gate lacks artifact checksum: '+side)
    return gate

def require_matching_boot_gate(path, artifacts, runtimes=None):
    gate = validate_boot_gate(path)
    for side, artifact in artifacts.items():
        with artifact.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != gate[side]['artifact_sha256']:
            raise ValueError('Artifact differs from boot gate: ' + side)
    # Phase 1, Change 3: a verified executable cannot certify a different runtime profile.
    if runtimes is not None:
        from runtime_identity import runtime_manifest, manifest_digest
        if set(runtimes) != set(artifacts):
            raise ValueError('Every verified artifact needs its runtime source')
        for side, runtime in runtimes.items():
            if manifest_digest(runtime_manifest(runtime)) != gate[side].get('runtime_source_sha256'):
                raise ValueError('Runtime source differs from boot gate: ' + side)
    return gate
