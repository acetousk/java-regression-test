"""Change 7: shared fail-closed phase-one prerequisite checks."""
import hashlib
import json

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
            and verification.get('servers_started') is True
            and verification.get('shutdown_verified') is True
            and shutdown_valid(gate.get('shutdown', {}))):
        raise ValueError('Boot gate does not prove readiness and graceful shutdown')
    for side in ('java', 'rust'):
        digest = gate.get(side, {}).get('artifact_sha256', '')
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Boot gate lacks artifact checksum: '+side)
    return gate

def require_matching_boot_gate(path, artifacts):
    gate = validate_boot_gate(path)
    for side, artifact in artifacts.items():
        with artifact.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != gate[side]['artifact_sha256']:
            raise ValueError('Artifact differs from boot gate: ' + side)
    return gate
