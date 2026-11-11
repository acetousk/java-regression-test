"""Change 10: identity of runtime source inputs, independent of mutable run state."""
import hashlib
import json
from pathlib import Path

# Root-only run outputs are never executable source. Configuration is included;
# generated connection/clock overrides live in separate retained run configs.
SOURCE_ROOTS = ('base-component', 'dev-component', 'component', 'conf')
GENERATED_DIRECTORIES = {'.git', 'target', '__pycache__'}


def runtime_manifest(runtime):
    runtime = Path(runtime)
    files = {}
    for name in SOURCE_ROOTS:
        directory = runtime / name
        if directory.is_symlink():
            raise ValueError('Runtime source directory symlink is unsupported: ' + name)
        if not directory.is_dir() and name != 'dev-component':
            raise ValueError('Runtime lacks source directory: ' + name)
        files['@directory/' + name] = hashlib.sha256(
            b'present' if directory.is_dir() else b'absent').hexdigest()
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(runtime)
            if any(part in GENERATED_DIRECTORIES for part in relative.parts):
                continue
            if path.is_symlink() and path.is_dir():
                raise ValueError('Runtime source directory symlink is unsupported: ' + str(relative))
            if path.is_file():
                files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError('Runtime source inventory is empty')
    return files


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require_runtime_copy(runtime, source):
    actual = runtime_manifest(runtime)
    if actual != runtime_manifest(source):
        raise ValueError('Copied runtime source differs from current checkout')
    return actual
