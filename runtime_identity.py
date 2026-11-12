"""Change 10: identity of runtime source inputs, independent of mutable run state."""
import hashlib
import json
from pathlib import Path

# Root-only run outputs are never executable source. Configuration is included;
# generated connection/clock overrides live in separate retained run configs.
# Root .env is included because engines load its configuration before startup.
SOURCE_ROOTS = ('base-component', 'dev-component', 'component', 'conf', 'lib', 'classes', 'src', 'template')
OPTIONAL_ROOTS = {'dev-component', 'lib', 'classes', 'src', 'template'}
# Source packages can use build-like names; only repository metadata is excluded.
GENERATED_DIRECTORIES = {'.git'}


def runtime_manifest(runtime):
    runtime = Path(runtime)
    files = {}
    # Phase 1, Change 3: dotenv and version metadata are loaded runtime inputs.
    for name in ('.env', 'version.json'):
        path = runtime / name
        files['@file/' + name] = hashlib.sha256(b'present' if path.is_file() else b'absent').hexdigest()
        if path.exists() and not path.is_file():
            raise ValueError('Runtime input is not a file: ' + name)
        if path.is_file():
            with path.open('rb') as stream:
                files[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    for name in SOURCE_ROOTS:
        directory = runtime / name
        if directory.is_symlink():
            raise ValueError('Runtime source directory symlink is unsupported: ' + name)
        # Phase 1, Change 3: Java runtime classpath and source inputs also bind the profile.
        if not directory.is_dir() and name not in OPTIONAL_ROOTS:
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
                with path.open('rb') as stream:
                    files[relative.as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
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
