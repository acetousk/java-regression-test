"""Compare one screen with disposable databases using the existing startup controller."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--route')
    selection.add_argument('--random', action='store_true')
    parser.add_argument('--modes', default='apps,qapps')
    parser.add_argument('--dialog-id')
    parser.add_argument('--dialog-label')
    parser.add_argument('--java-checkout', type=Path, default=ROOT / 'moqui-framework')
    parser.add_argument('--rust-checkout', type=Path, default=ROOT / 'mr-moqui')
    parser.add_argument('--rust-binary', type=Path, help='Explicit prebuilt artifact; provenance records that it was not rebuilt')
    parser.add_argument('--java-home', type=Path)
    parser.add_argument('--java-port', type=int, default=0, help='0 selects an available port')
    parser.add_argument('--rust-port', type=int, default=0, help='0 selects an available port')
    parser.add_argument('--boot-timeout', type=int, default=300)
    parser.add_argument('--shutdown-timeout', type=int, default=120)
    args = parser.parse_args(argv)
    # Use the browser runner's validation before creating databases or launching engines.
    browser_args = ['--route', args.route] if args.route else ['--random']
    browser_args += ['--modes', args.modes]
    for key in ('dialog_id', 'dialog_label'):
        if getattr(args, key) is not None:
            browser_args += ['--' + key.replace('_', '-'), getattr(args, key)]
    subprocess.run(['node', '-e', "require('./compare-screen').options(process.argv.slice(1))", '--', *browser_args],
                   cwd=ROOT / 'ui-test', check=True)
    for key in ('java_port', 'rust_port'):
        if not 0 <= getattr(args, key) <= 65535:
            parser.error(f'--{key.replace("_", "-")} must be between 0 and 65535')
    if args.java_port and args.java_port == args.rust_port:
        parser.error('Java and Rust need different HTTP ports')
    return args, browser_args


def select_ports(args):
    # Hold both sockets while selecting, so automatic ports cannot select one another.
    sockets = []
    try:
        for key in ('java_port', 'rust_port'):
            sock = socket.socket()
            sockets.append(sock)
            sock.bind(('127.0.0.1', getattr(args, key)))
            setattr(args, key, sock.getsockname()[1])
    finally:
        for sock in sockets:
            sock.close()
    # The controller rechecks availability before startup; a port race fails safely.


def main(argv=None):
    args, browser_args = arguments(argv)
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location('screen_probe_controller', ROOT / 'java-regression-test.py')
    controller = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = controller
    spec.loader.exec_module(controller)
    args.java_checkout = args.java_checkout.resolve()
    args.rust_checkout = args.rust_checkout.resolve()
    if args.rust_binary:
        binary = args.rust_binary.resolve()
        controller.rust_artifact = lambda directory: binary
    for name, repo in controller.engine_directories(args).items():
        artifact = repo / 'moqui.war' if name == 'java' else controller.rust_artifact(repo)
        if not artifact.is_file():
            raise FileNotFoundError(f'Missing {name} artifact: {artifact}; build it or select --rust-binary')
    select_ports(args)
    original_conf = controller.demo_conf

    def demo_conf(source, destination, db_port, password, http_port, crypt_pass):
        original_conf(source, destination, db_port, password, http_port, crypt_pass)
        if http_port != args.rust_port:
            return
        tree = ET.parse(destination)
        screen = tree.getroot().find('screen-facade')
        if screen is None:
            screen = ET.SubElement(tree.getroot(), 'screen-facade')
        for mode, module in [('html', 'ScreenHtml.js'), ('qvt', 'ScreenQvt.js')]:
            output = screen.find(f"screen-text-output[@type='{mode}']")
            if output is None:
                output = ET.SubElement(screen, 'screen-text-output', {'type': mode, 'mime-type': 'text/html'})
            output.set('macro-template-location', f'component://framework/template/screen/{module}')
        tree.write(destination, encoding='unicode')

    def probe(args, evidence):
        provenance = {'limitation': 'Existing artifacts, not rebuilt by this command. Rust uses worktree runtime macro overrides. No engine-source parity claim.'}
        for name, repo in controller.engine_directories(args).items():
            artifact = repo / 'moqui.war' if name == 'java' else controller.rust_artifact(repo)
            with artifact.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            provenance[name] = {
                'checkout': str(repo),
                'revision': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                'status': subprocess.check_output(['git', '-C', str(repo), 'status', '--short'], text=True),
                'artifact': str(artifact), 'sha256': checksum,
            }
        (evidence / 'probe-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        subprocess.run(['node', str(ROOT / 'ui-test/compare-screen.js'), *browser_args],
                       env={**os.environ, 'MOQUI_RUN_DIR': str(evidence),
                            'JAVA_BASE_URL': f'http://127.0.0.1:{args.java_port}',
                            'RUST_BASE_URL': f'http://127.0.0.1:{args.rust_port}'}, check=True)

    controller.demo_conf = demo_conf
    controller.run_visual_tests = probe
    args.skip_step_4 = True
    args.deterministic = False
    args.keep_databases = False
    controller.boot_and_stop(args)


if __name__ == '__main__':
    main()
