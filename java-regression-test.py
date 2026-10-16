#!/usr/bin/env python3
"""Initialize and build both engines with their own runtimes.

Build both engines, boot against disposable PostgreSQL, and stop both processes.
Deterministic clocks, entropy, and transaction barriers are not implemented yet.
"""

import argparse
from collections import Counter
from decimal import Decimal
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from schema_mapping import MappingCollision, NameMapping


ROOT = Path(__file__).resolve().parent
REPOSITORIES = ("moqui-framework", "mr-moqui")
POSTGRES_IMAGE = "postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"


def git(*args):
    subprocess.run(["git", *map(str, args)], check=True)


def build_engines(java_home=None):
    environment = os.environ.copy()
    if java_home:
        environment["JAVA_HOME"] = str(Path(java_home).resolve())
        environment["PATH"] = str(Path(java_home).resolve() / "bin") + os.pathsep + environment.get("PATH", "")

    manifest = ROOT / ".runs" / "build.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.unlink(missing_ok=True)
    engines = (
        ("java", "moqui-framework", ["./gradlew", "--no-daemon", "clean", "build"], "moqui.war"),
        ("rust", "mr-moqui", ["cargo", "build", "--locked", "-p", "moqui"], "target/debug/moqui"),
    )
    artifacts = {}
    for name, checkout, command, artifact in engines:
        directory = ROOT / checkout
        runtime = directory / "runtime"
        if runtime.is_symlink() or not (runtime / "conf" / "MoquiDevConf.xml").is_file():
            raise SystemExit(f"Missing private runtime configuration: {runtime}")
        print(f"Building {name}: {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=directory, env=environment, check=True)
        executable = directory / artifact
        if not executable.is_file():
            raise SystemExit(f"Build did not produce {executable}")
        if name == "rust" and not os.access(executable, os.X_OK):
            raise SystemExit(f"Rust artifact is not executable: {executable}")
        with executable.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        artifacts[name] = {
            "artifact": str(executable),
            "runtime": str(runtime),
            "sha256": checksum,
        }
    manifest.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"Both engines built; artifact/runtime paths recorded in {manifest}")


def demo_conf(source, destination, db_port, password, http_port):
    """Preserve each engine's dev/demo settings, overriding only test connectivity."""
    tree = ET.parse(source)
    root = tree.getroot()
    properties = {
        "entity_ds_db_conf": "postgres",
        "entity_ds_host": "127.0.0.1",
        "entity_ds_port": str(db_port),
        "entity_ds_database": "moqui",
        "entity_ds_schema": "public",
        "entity_ds_user": "moqui",
        "entity_ds_password": password,
        "entity_ds_sslmode": "disable",
        "entity_empty_db_load": "all",
        "webapp_http_port": str(http_port),
        "webapp_https_enabled": "false",
        "cluster_https_port": "0",
        "opensearch_run": "false",
    }
    for name, value in properties.items():
        node = root.find(f"default-property[@name='{name}']")
        if node is None:
            node = ET.SubElement(root, "default-property", {"name": name})
        node.set("value", value)
    # The generated configuration contains disposable database credentials.
    destination.touch(mode=0o600)
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def wait_for_ports(processes, ports, timeout, boot_logs=None):
    """Wait for demo loading to complete and both HTTP ports to listen."""
    waiting = set(processes)
    deadline = time.monotonic() + timeout
    while waiting:
        for name in list(waiting):
            process = processes[name]
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited before readiness; see its boot log")
            if boot_logs:
                marker = ("records (with types from empty-db-load:" if name == "java"
                          else "Table check and empty-db load finished")
                if marker not in boot_logs[name].read_text(errors="replace"):
                    continue
            try:
                with socket.create_connection(("127.0.0.1", ports[name]), timeout=0.2):
                    pass
            except OSError:
                continue
            waiting.remove(name)
            print(f"{name} reached port {ports[name]}", flush=True)
        if waiting and time.monotonic() >= deadline:
            raise TimeoutError(f"HTTP-port readiness timed out: {', '.join(sorted(waiting))}")
        if waiting:
            time.sleep(0.1)


def snapshot_compare(left, right, report_dir):
    """Compare complete captured row multisets, retaining duplicate rows."""
    def canonical(value):
        if isinstance(value, dict):
            return ["object", [[key, canonical(item)] for key, item in sorted(value.items())]]
        if isinstance(value, list):
            return ["array", [canonical(item) for item in value]]
        if isinstance(value, Decimal):
            # normalize() can round large values under the default Decimal context.
            number = format(value, "f")
            if "." in number:
                number = number.rstrip("0").rstrip(".")
            return ["number", "0" if value == 0 else number]
        return [type(value).__name__, value]

    java, rust = (json.loads(path.read_text()) for path in (left, right))
    def encoded(record):
        return json.dumps(canonical(record), ensure_ascii=True, separators=(",", ":"))

    rows, logical_rows, logical_schemas, mapping_errors = [], [], [], {}
    for side, snapshot in (("java", java), ("rust", rust)):
        records = [json.loads(record, parse_int=Decimal, parse_float=Decimal)
                   for record in snapshot["records"]]
        rows.append(Counter(encoded(record) for record in records))
        mapping = NameMapping()  # Separate collision registries for each database.
        try:
            logical_schemas.append(mapping.schema(snapshot["schema"]))
            logical_rows.append(Counter(encoded(mapping.record(record)) for record in records))
        except MappingCollision as error:
            mapping_errors[side] = str(error)
    java_rows, rust_rows = rows
    logical_schema_equal = not mapping_errors and logical_schemas[0] == logical_schemas[1]
    logical_rows_equal = not mapping_errors and logical_rows[0] == logical_rows[1]
    schema_equal = java["schema"] == rust["schema"]
    java_schema, rust_schema = (snapshot["schema"].encode("utf-8") for snapshot in (java, rust))
    schema_bytes = []
    # Positional byte ranges are exact and linear-time; a minimal edit alignment
    # on large, repetitive SQL dumps can take minutes. schema.diff gives line context.
    start = None
    length = max(len(java_schema), len(rust_schema))
    for offset in range(length + 1):
        different = offset < length and java_schema[offset:offset + 1] != rust_schema[offset:offset + 1]
        if different and start is None:
            start = offset
        elif not different and start is not None:
            left_bytes, right_bytes = java_schema[start:offset], rust_schema[start:offset]
            schema_bytes.append({
                "operation": "replace" if left_bytes and right_bytes else "delete" if left_bytes else "insert",
                "java_offset": min(start, len(java_schema)),
                "rust_offset": min(start, len(rust_schema)),
                "java_hex": left_bytes.hex(), "rust_hex": right_bytes.hex(),
            })
            start = None
    report = {
        "byte_encoding": "Physical UTF-8 schema text and canonical JSON records; hex is exact",
        "schema_byte_differences": schema_bytes,
        "record_byte_differences": [
            {"side": side, "count": count, "hex": record.encode("utf-8").hex()}
            for side, differences in (("java", java_rows - rust_rows), ("rust", rust_rows - java_rows))
            for record, count in sorted(differences.items())
        ],
        "physical_equal": schema_equal and java_rows == rust_rows,
        "logical_comparison": {
            "scope": "Conservative entity/field naming only; not complete database equivalence",
            "schema_equal": logical_schema_equal,
            "row_and_sequence_values_equal": logical_rows_equal,
            "equal": logical_schema_equal and logical_rows_equal,
            "mapping_errors": mapping_errors,
            "java_only_records": (list((logical_rows[0] - logical_rows[1]).elements())
                                  if not mapping_errors else None),
            "rust_only_records": (list((logical_rows[1] - logical_rows[0]).elements())
                                  if not mapping_errors else None),
        },
        "schema_dump_equal": schema_equal,
        "row_and_sequence_values_equal": java_rows == rust_rows,
        "java_only_records": list((java_rows - rust_rows).elements()),
        "rust_only_records": list((rust_rows - java_rows).elements()),
        "complete_logical_equivalence_verified": False,
    }
    (report_dir / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    (report_dir / "schema.diff").write_text("".join(difflib.unified_diff(
        java["schema"].splitlines(keepends=True), rust["schema"].splitlines(keepends=True),
        fromfile="java-schema", tofile="rust-schema",
    )))
    (report_dir / "logical-schema.diff").write_text(
        "Mapping failed: " + json.dumps(mapping_errors) + "\n" if mapping_errors else
        "".join(difflib.unified_diff(
            [json.dumps(statement) + "\n" for statement in logical_schemas[0]],
            [json.dumps(statement) + "\n" for statement in logical_schemas[1]],
            fromfile="java-logical-schema", tofile="rust-logical-schema",
        ))
    )
    equal = logical_schema_equal and logical_rows_equal
    if not equal:
        print(json.dumps(report, indent=2), flush=True)
    return equal


def diff_compare(left, right, report_dir):
    """Incremental comparison requires a verified baseline and gap-free tracking."""
    raise NotImplementedError("Incremental comparison requires change tracking; run snapshot_compare instead")


def boot_and_stop(args):
    # Reject occupied HTTP ports so another application's listener cannot pass readiness.
    for port in (args.java_port, args.rust_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))

    run_id = uuid.uuid4().hex
    evidence = ROOT / ".runs" / run_id
    evidence.mkdir(parents=True, mode=0o700)
    print(f"Startup evidence: {evidence}", flush=True)
    containers, processes, logs = {}, {}, []
    started = False
    password = secrets.token_hex(24)
    environment = os.environ.copy()
    if args.java_home:
        environment["JAVA_HOME"] = str(Path(args.java_home).resolve())
        environment["PATH"] = str(Path(args.java_home).resolve() / "bin") + os.pathsep + environment.get("PATH", "")
    # This is infrastructure entropy, not an application deterministic-input source.
    container_environment = {**os.environ, "POSTGRES_PASSWORD": password}
    ports = {"java": args.java_port, "rust": args.rust_port}
    try:
        # One fresh, storage-isolated container per engine; never reset an existing DB.
        for name, checkout in zip(("java", "rust"), REPOSITORIES):
            container = f"moqui-regression-{run_id}-{name}"
            containers[name] = container
            subprocess.run([
                "docker", "run", "--detach", "--rm", "--name", container,
                "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql",
                "--env", "POSTGRES_USER=moqui", "--env", "POSTGRES_DB=moqui",
                "--env", "POSTGRES_PASSWORD", "--env", "TZ=UTC",
                POSTGRES_IMAGE, "-c", "timezone=UTC", "-c", "max_prepared_transactions=100",
            ], env=container_environment, check=True, stdout=subprocess.DEVNULL)
            mapping = subprocess.check_output(
                ["docker", "port", container, "5432/tcp"], text=True
            ).strip()
            db_port = int(mapping.rsplit(":", 1)[1])
            deadline = time.monotonic() + args.boot_timeout
            while subprocess.run(
                ["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "moqui", "-d", "moqui"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{name} PostgreSQL did not become ready")
                time.sleep(0.2)
            image_id = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Image}}", container], text=True
            ).strip()
            (evidence / f"{name}-postgres-image.txt").write_text(image_id + "\n")
            table_count = subprocess.check_output([
                "docker", "exec", container, "psql", "-U", "moqui", "-d", "moqui", "-Atc",
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','S','v','m','f')",
            ], text=True).strip()
            if table_count != "0":
                raise RuntimeError(f"{name} database is not empty")
            runtime = ROOT / checkout / "runtime"
            conf = evidence / f"{name}-demo.xml"
            demo_conf(runtime / "conf/MoquiDevConf.xml", conf, db_port, password, ports[name])

        if (evidence / "java-postgres-image.txt").read_bytes() != (evidence / "rust-postgres-image.txt").read_bytes():
            raise RuntimeError("PostgreSQL containers resolved to different image IDs")

        # Java needs the PostgreSQL JDBC driver in its private runtime.
        driver = ROOT / "moqui-framework/runtime/lib/postgresql-42.7.7.jar"
        if not driver.exists():
            driver.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(
                "https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar",
                timeout=60,
            ) as response:
                payload = response.read()
            driver.write_bytes(payload)

        for name, checkout in zip(("java", "rust"), REPOSITORIES):
            directory = ROOT / checkout
            runtime = directory / "runtime"
            conf = evidence / f"{name}-demo.xml"
            if name == "java":
                command = ["java", f"-Dmoqui.runtime={runtime}", f"-Dmoqui.conf={conf}",
                           "-jar", str(directory / "moqui.war"), f"port={ports[name]}", "no-run-es"]
            else:
                command = [str(directory / "target/debug/moqui"), "--conf", str(conf),
                           "--port", str(ports[name]), "--https-port", "off", "--no-run-es"]
            log = (evidence / f"{name}-boot.log").open("wb")
            logs.append(log)
            overrides = {node.get("name"): node.get("value")
                         for node in ET.parse(conf).getroot().findall("default-property")}
            processes[name] = subprocess.Popen(
                command, cwd=directory, env={**environment, **overrides, "MOQUI_RUNTIME": str(runtime),
                    "MOQUI_CONF": str(conf), "MOQUI_FRAMEWORK": str(runtime / "base-component/framework"), "TZ": "UTC"},
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        wait_for_ports(processes, ports, args.boot_timeout,
                       {name: evidence / f"{name}-boot.log" for name in processes})
        started = True
        print("Both engines started; stopping both processes.", flush=True)
    finally:
        for process in processes.values():
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                except ProcessLookupError:
                    process.wait()
        for log in logs:
            log.close()
        try:
            if started:
                # Step 4: Snapshot and compare only after both application processes stop.
                for name, container in containers.items():
                    # The stopped applications must be the only database writers.
                    # Schema capture is separate; sequences are not MVCC data.
                    schema = subprocess.check_output([
                        "docker", "exec", container, "pg_dump", "-U", "moqui", "-d", "moqui",
                        "--schema-only", "--restrict-key=MoquiRegression",
                    ], text=True)
                    sql = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL timezone = 'UTC';
SET LOCAL datestyle = 'ISO, YMD';
SET LOCAL intervalstyle = 'postgres';
SET LOCAL extra_float_digits = 3;
SELECT format(
  'SELECT json_build_object(''table'', %L, ''row'', row_to_json(t)) FROM ONLY %I.%I t',
  n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm') AND n.nspname !~ '^pg_'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relname
\gexec
SELECT format(
  'SELECT json_build_object(''sequence'', %L, ''state'', row_to_json(t)) FROM %I.%I t',
  n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'S' AND n.nspname !~ '^pg_'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relname
\gexec
COMMIT;
"""
                    records = subprocess.check_output([
                        "docker", "exec", "-i", container, "psql", "-X", "-qAt",
                        "--set", "ON_ERROR_STOP=1", "-U", "moqui", "-d", "moqui",
                    ], input=sql, text=True).splitlines()
                    destination = evidence / f"{name}-snapshot.json"
                    destination.touch(mode=0o600)
                    destination.write_text(json.dumps({"schema": schema, "records": records}, indent=2) + "\n")
                if not snapshot_compare(evidence / "java-snapshot.json",
                                        evidence / "rust-snapshot.json", evidence):
                    raise SystemExit(f"Startup snapshots differ; inspect {evidence / 'comparison.json'}")
                print("Startup snapshots match under conservative name mapping; see comparison.json "
                      "for physical outcomes (not a complete logical-equivalence proof).", flush=True)
        finally:
            for name, container in containers.items():
                with (evidence / f"{name}-postgres.log").open("wb") as log:
                    subprocess.run(["docker", "logs", container], stdout=log, stderr=subprocess.STDOUT)
                if args.keep_databases:
                    print(f"Connect to {name}: docker exec -it {container} psql -U moqui -d moqui", flush=True)
                    print(f"Remove when finished: docker rm -f -v {container}", flush=True)
                else:
                    subprocess.run(["docker", "rm", "--force", "--volumes", container], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", help="JDK home for the Java build (Java 21 recommended)")
    parser.add_argument("--java-port", type=int, default=8080)
    parser.add_argument("--rust-port", type=int, default=8081)
    parser.add_argument("--boot-timeout", type=float, default=600)
    parser.add_argument("--keep-databases", action="store_true",
                        help="Keep PostgreSQL containers after application shutdown for inspection")
    args = parser.parse_args()
    if args.java_port == args.rust_port or not all(1 <= p <= 65535 for p in (args.java_port, args.rust_port)):
        parser.error("Java and Rust need distinct valid HTTP ports")
    if args.boot_timeout <= 0:
        parser.error("--boot-timeout must be positive")

    # Step 1: Initialize the pinned framework submodules and Java's private runtime.
    git("-C", ROOT, "submodule", "update", "--init", "--recursive", "--", *REPOSITORIES)

    for name in (*REPOSITORIES, "moqui-framework/runtime"):
        revision = subprocess.check_output(
            ["git", "-C", str(ROOT / name), "rev-parse", "HEAD"], text=True
        ).strip()
        print(f"{name}: {revision}", flush=True)
    # Step 2: Build Java's moqui.war and Rust's executable with separate runtimes.
    build_engines(args.java_home)

    # Step 3: Start both engines, wait for HTTP ports, then stop both processes.
    boot_and_stop(args)


if __name__ == "__main__":
    (ROOT / ".runs").mkdir(exist_ok=True)
    with (ROOT / ".runs/run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another regression run is already active")
        main()
