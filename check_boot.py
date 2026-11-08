#!/usr/bin/env python3
"""Check prebuilt Java/Rust startup, HTTP readiness and shutdown on fresh databases.

The ordinary harness still captures and compares the databases. That verdict is
recorded separately: this command's exit status proves boot, not database parity.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("controller", ROOT / "java-regression-test.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def artifact_evidence(checkout, artifact):
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    diff = subprocess.check_output(["git", "-C", str(checkout), "diff", "HEAD", "--"])
    dirty = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True)
    with artifact.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"revision": revision, "dirty": bool(dirty), "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
            "artifact": str(artifact), "artifact_sha256": checksum}


def http_readiness(ports, gate):
    """Require actual health JSON and a rendered page, not only a listening socket."""
    for side, path in (("java", "/status"), ("rust", "/health")):
        url = f"http://127.0.0.1:{ports[side]}{path}"
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
            valid = isinstance(payload, dict) and (
                payload.get("ready") is True if side == "rust" else "JavaRuntime" in payload)
            if response.status != 200 or not valid:
                raise RuntimeError(f"{side} HTTP readiness failed: {response.status}, {payload!r}")
            gate[side]["http_readiness"] = {"url": url, "status": response.status, "body": payload}
        with urlopen(f"http://127.0.0.1:{ports[side]}/", timeout=30) as response:
            content = response.read()
            if response.status != 200 or not content:
                raise RuntimeError(f"{side} root page failed: HTTP {response.status}, {len(content)} bytes")
            gate[side]["http_root"] = {"status": response.status, "bytes": len(content),
                                       "final_url": response.url}
    gate["http_ready"] = True


def check(args):
    runs = ROOT / ".runs"
    runs.mkdir(exist_ok=True)
    # Change 5: Hold the shared harness lock before changing manifests or gate evidence.
    with (runs / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another regression run is already active") from error
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S.%fZ")
        output = (args.evidence_dir or runs / "boot-check" / run_id).resolve()
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        evidence = output / run_id
        gate = {"passed": False, "status": "running", "run_evidence": str(evidence),
                "scope": "fresh database startup, HTTP readiness and graceful shutdown; not database or UI parity"}
        write_json(output / "gate.json", gate)
        completed = False
        try:
            directories = controller.engine_directories(args)
            manifest = {}
            for side, checkout in directories.items():
                artifact = checkout / "moqui.war" if side == "java" else controller.rust_artifact(checkout)
                gate[side] = artifact_evidence(checkout, artifact)
                manifest[side] = {"artifact": str(artifact), "runtime": str(checkout / "runtime"),
                                  "checkout": str(checkout), "sha256": gate[side]["artifact_sha256"]}
            write_json(runs / "build.json", manifest)
            try:
                controller.boot_and_stop(args, evidence_dir=evidence,
                                         readiness_check=lambda ports: http_readiness(ports, gate))
            except (Exception, SystemExit) as error:
                # A snapshot mismatch is retained verbatim; it cannot turn into a parity pass.
                gate["harness_result"] = f"{type(error).__name__}: {error}"
            completed = True
        finally:
            for name in ("shutdown", "verification"):
                path = evidence / f"{name}.json"
                if path.exists():
                    gate[name] = json.loads(path.read_text())
            shutdown = gate.get("shutdown", {})
            verification = gate.get("verification", {})
            gate["database_parity_passed"] = verification.get("final_databases_equal")
            gate["passed"] = bool(completed and gate.get("http_ready")
                                  and verification.get("servers_started")
                                  and verification.get("shutdown_verified")
                                  and set(shutdown) == {"java", "rust"}
                                  and all(not item["errors"] and not item["forced_kill"]
                                          for item in shutdown.values()))
            gate["status"] = "completed" if completed else "interrupted_or_setup_failed"
            write_json(output / "gate.json", gate)
            print(f"Boot gate {'PASSED' if gate['passed'] else 'FAILED'}: {output / 'gate.json'}", flush=True)
            print(f"Database parity verdict (separate): {gate['database_parity_passed']}", flush=True)
        return 0 if gate["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-port", type=int, default=18080)
    parser.add_argument("--rust-port", type=int, default=18081)
    parser.add_argument("--java-checkout", type=Path, help="Prebuilt Java checkout; defaults to moqui-framework")
    parser.add_argument("--rust-checkout", type=Path, help="Prebuilt Rust checkout; defaults to mr-moqui")
    parser.add_argument("--evidence-dir", type=Path, help="Directory for gate.json and private run evidence")
    parser.add_argument("--boot-timeout", type=float, default=600)
    parser.add_argument("--shutdown-timeout", type=float, default=120)
    args = parser.parse_args()
    if args.java_port == args.rust_port or not all(1 <= port <= 65535 for port in (args.java_port, args.rust_port)):
        parser.error("Java and Rust need distinct valid HTTP ports")
    if args.boot_timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error("Timeouts must be positive")
    args.java_home = None
    args.deterministic = False
    args.keep_databases = False
    args.exclude_rust_only = False
    args.source_root = ROOT
    return check(args)


if __name__ == "__main__":
    raise SystemExit(main())
