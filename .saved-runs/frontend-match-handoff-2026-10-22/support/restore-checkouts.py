#!/usr/bin/env python3
"""Reconstruct pinned clean engine checkouts in a fresh harness clone.

Does not apply archived dirty patches or restore old private runtime state.
"""
import json
import subprocess
import sys
from pathlib import Path


def run(*args):
    subprocess.run(args, check=True)


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def clean_repo(path):
    # A directory inside another repository is not itself an engine checkout.
    if not (path / '.git').exists():
        return False
    if Path(output('git', '-C', str(path), 'rev-parse', '--show-toplevel')).resolve() != path.resolve():
        raise SystemExit(f'Unexpected repository root: {path}')
    if output('git', '-C', str(path), 'status', '--porcelain'):
        raise SystemExit(f'Refusing dirty repository: {path}')
    return True


def ensure_repo(path, url, revision):
    if not clean_repo(path):
        if path.exists() and any(path.iterdir()):
            raise SystemExit(f'Refusing nonempty directory without its own Git metadata: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        run('git', 'clone', url, str(path))
    run('git', '-C', str(path), 'fetch', 'origin', revision)
    run('git', '-C', str(path), 'checkout', '--detach', revision)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: restore-checkouts.py /absolute/path/to/fresh/frontend-match')
    root = Path(sys.argv[1]).resolve()
    if not (root / 'java-regression-test.py').is_file():
        raise SystemExit('Target must be a prepared regression harness checkout')
    manifest = json.loads((Path(__file__).resolve().parent.parent / 'manifest.json').read_text())
    repos = manifest['effective_repositories']
    for name, config in repos.items():
        path = root / name
        if name == '.runs/pr-invoice-current':
            if path.exists() and any(path.iterdir()):
                if not clean_repo(path):
                    raise SystemExit(f'Not a clean worktree: {path}')
                if output('git', '-C', str(path), 'rev-parse', 'HEAD') != config['revision']:
                    raise SystemExit(f'Existing worktree has another revision: {path}')
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                run('git', '-C', str(root / 'mr-moqui'), 'fetch', 'origin', config['revision'])
                run('git', '-C', str(root / 'mr-moqui'), 'worktree', 'add',
                    '-b', 'fix/html-invoice-form-metrics', str(path), config['revision'])
        else:
            ensure_repo(path, config['url'], config['revision'])
    print('Pinned clean engines restored. Preserved original patches remain unapplied.')


if __name__ == '__main__':
    main()
