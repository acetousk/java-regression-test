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
import re
import secrets
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from startup_exceptions import apply_approved_differences


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


def demo_conf(source, destination, db_port, password, http_port, crypt_pass):
    """Preserve dev/demo settings, overriding test connectivity and the shared test key."""
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
        "entity_ds_crypt_pass": crypt_pass,
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
    """Wait for completed application initialization and both HTTP ports to listen."""
    waiting = set(processes)
    deadline = time.monotonic() + timeout
    while waiting:
        for name in list(waiting):
            process = processes[name]
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited before readiness; see its boot log")
            if boot_logs:
                markers = (("records (with types from empty-db-load:", "Moqui Framework initialized in")
                           if name == "java" else
                           ("Table check and empty-db load finished", "Listening for HTTP on"))
                text = boot_logs[name].read_text(errors="replace")
                if not all(marker in text for marker in markers):
                    continue
                # MoquiStart initializes the webapp before registering Jetty's shutdown hook.
                if name == "java" and not re.search(r"Started (?:oejs\.)?Server@", text):
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


def stop_engines(processes, boot_logs, timeout):
    """Signal both engines first; verify only shutdown evidence written after SIGTERM."""
    offsets = {name: path.stat().st_size for name, path in boot_logs.items()}
    report = {}
    deadline = time.monotonic() + timeout
    for name, process in processes.items():
        report[name] = {"forced_kill": False, "errors": []}
        if process.poll() is not None:
            report[name]["errors"].append("Engine exited before shutdown was requested")
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for name, process in processes.items():
        result = report[name]
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            result["forced_kill"] = True
            result["errors"].append("Graceful shutdown timed out; SIGKILL required")
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        result["returncode"] = process.returncode
        allowed_codes = (0, 128 + signal.SIGTERM, -signal.SIGTERM) if name == "java" else (0,)
        if process.returncode not in allowed_codes:
            result["errors"].append(f"Unexpected exit code: {process.returncode}")
        with boot_logs[name].open("rb") as stream:
            stream.seek(offsets[name])
            text = stream.read().decode("utf-8", errors="replace")
        markers = (("ArtifactHitBins stored", "Moqui ExecutionContextFactory Destroyed")
                   if name == "java" else ("ArtifactHitBins stored",))
        result["missing_shutdown_markers"] = [marker for marker in markers if marker not in text]
        if result["missing_shutdown_markers"]:
            result["errors"].append("Missing post-SIGTERM flush/completion evidence")
    return report


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


def startup_summary(java, rust):
    """Diagnostic inventory only: Rust-only objects are reported, never excluded."""
    relations, tables = [], []
    for snapshot in (java, rust):
        inventory, rows = {}, {}
        for record in snapshot["records"]:
            item = json.loads(record, parse_int=Decimal, parse_float=Decimal)
            if "relation" in item:
                inventory[item["relation"]] = item
            if "table" in item and "row" in item:
                rows.setdefault(item["table"], []).append(item["row"])
        relations.append(inventory)
        tables.append(rows)

    def counts(values):
        return Counter(json.dumps(canonical(value), separators=(",", ":")) for value in values)

    differing_tables = {}
    for table in sorted(tables[0].keys() | tables[1].keys()):
        left, right = (side.get(table, []) for side in tables)
        left_counts, right_counts = counts(left), counts(right)
        if left_counts == right_counts:
            continue
        columns = sorted(set().union(*(row.keys() for row in left + right)))
        differing_tables[table] = {
            "java_rows": len(left), "rust_rows": len(right),
            "java_unmatched_rows": sum((left_counts - right_counts).values()),
            "rust_unmatched_rows": sum((right_counts - left_counts).values()),
            # Column multisets locate likely causes; they do not establish row equality.
            "differing_column_multisets": [column for column in columns if
                counts([column in row, row.get(column)] for row in left) !=
                counts([column in row, row.get(column)] for row in right)],
        }
    # Diagnostics only: compare each operation's bin hit-count multiset without
    # timing/sequence-id noise. Do not sum bins: that would conceal duplicates.
    bin_groups = []
    identity = ("artifact_type", "artifact_sub_type", "artifact_name")
    for side in tables:
        groups = {}
        for row in side.get("public.artifact_hit_bin", []):
            key = tuple(row.get(field) for field in identity)
            groups.setdefault(key, []).append(str(row.get("hit_count")))
        bin_groups.append({key: sorted(values) for key, values in groups.items()})
    operation_differences = [
        {**dict(zip(identity, key)), "java_hit_counts": bin_groups[0].get(key, []),
         "rust_hit_counts": bin_groups[1].get(key, [])}
        for key in sorted(bin_groups[0].keys() | bin_groups[1].keys(), key=repr)
        if bin_groups[0].get(key, []) != bin_groups[1].get(key, [])
    ]
    return {
        "artifact_bin_operations": {
            "diagnostic_only": True,
            "operation_bin_multisets_equal": not operation_differences,
            "java_bins": sum(len(values) for values in bin_groups[0].values()),
            "rust_bins": sum(len(values) for values in bin_groups[1].values()),
            "differing_operations": operation_differences,
        },
        "relation_inventory_available": bool(relations[0]) and bool(relations[1]),
        "java_only_relations": sorted(relations[0].keys() - relations[1].keys()),
        "rust_only_relations": sorted(relations[1].keys() - relations[0].keys()),
        "shared_relation_differences": {
            name: {"java": relations[0][name], "rust": relations[1][name]}
            for name in sorted(relations[0].keys() & relations[1].keys())
            if relations[0][name] != relations[1][name]
        },
        "differing_tables": differing_tables,
        "differences_excluded": False,
    }


STATISTICS_TABLES = ("public.artifact_hit_bin", "public.artifact_hit")


def statistics_equal(normalized):
    """The artifact statistics alone, after approved differences: every hit and bin row, and the hit bin
    sequence position. Timestamps of other tables do not decide this verdict; the full gate still does."""
    def rows(snapshot):
        selected = []
        for record in snapshot["records"]:
            table, row = record.get("table"), record.get("row")
            if table in STATISTICS_TABLES:
                selected.append(record)
            elif table == "public.sequence_value_item" and row.get("seq_name") in (
                    "moqui.server.ArtifactHit", "moqui.server.ArtifactHitBin"):
                selected.append({"table": table, "row": {"seq_name": row["seq_name"], "seq_num": row.get("seq_num")}})
        return Counter(json.dumps(canonical(record), separators=(",", ":")) for record in selected)
    return rows(normalized[0]) == rows(normalized[1])


def snapshot_compare(left, right, report_dir):
    """Compare complete captured row multisets, retaining duplicate rows."""
    java, rust = (json.loads(path.read_text()) for path in (left, right))
    (report_dir / "summary.json").write_text(json.dumps(startup_summary(java, rust), indent=2) + "\n")
    rows = []
    for snapshot in (java, rust):
        rows.append(Counter(json.dumps(canonical(json.loads(
            record, parse_int=Decimal, parse_float=Decimal,
        )), ensure_ascii=True, separators=(",", ":")) for record in snapshot["records"]))
    java_rows, rust_rows = rows
    approved = json.loads((ROOT / "approved-startup-differences.json").read_text())
    normalized, applied = apply_approved_differences(java, rust, approved)
    accepted_rows = [Counter(json.dumps(canonical(record), ensure_ascii=True, separators=(",", ":"))
                             for record in snapshot["records"]) for snapshot in normalized]
    accepted_schema_equal = normalized[0]["schema"] == normalized[1]["schema"]
    equal = accepted_schema_equal and accepted_rows[0] == accepted_rows[1]
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
        "byte_encoding": "UTF-8 schema text and canonical JSON records; hex is exact",
        "schema_byte_differences": schema_bytes,
        "record_byte_differences": [
            {"side": side, "count": count, "hex": record.encode("utf-8").hex()}
            for side, differences in (("java", java_rows - rust_rows), ("rust", rust_rows - java_rows))
            for record, count in sorted(differences.items())
        ],
        "approved_differences_applied": applied,
        "unapproved_record_byte_differences": [
            {"side": side, "count": count, "hex": record.encode("utf-8").hex()}
            for side, differences in (("java", accepted_rows[0] - accepted_rows[1]),
                                      ("rust", accepted_rows[1] - accepted_rows[0]))
            for record, count in sorted(differences.items())
        ],
        "schema_equal_after_approved_differences": accepted_schema_equal,
        "records_equal_after_approved_differences": accepted_rows[0] == accepted_rows[1],
        "statistics_equal_after_approved_differences": statistics_equal(normalized),
        "comparison_passed": equal,
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
    (report_dir / "unapproved-schema.diff").write_text("".join(difflib.unified_diff(
        normalized[0]["schema"].splitlines(keepends=True), normalized[1]["schema"].splitlines(keepends=True),
        fromfile="java-schema-after-approved-differences", tofile="rust-schema-after-approved-differences",
    )))
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
    crypt_pass = secrets.token_hex(32)
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
            demo_conf(runtime / "conf/MoquiDevConf.xml", conf, db_port, password, ports[name], crypt_pass)

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
        shutdown = stop_engines(processes, {name: evidence / f"{name}-boot.log" for name in processes},
                                args.shutdown_timeout)
        for log in logs:
            log.close()
        (evidence / "shutdown.json").write_text(json.dumps(shutdown, indent=2) + "\n")
        try:
            if started:
                if any(result["errors"] for result in shutdown.values()):
                    raise RuntimeError(f"Graceful shutdown verification failed; inspect {evidence / 'shutdown.json'}")
                print("Both engines shut down gracefully and flushed artifact bins.", flush=True)
                # Step 4: Snapshot and compare only after verified graceful shutdown.
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
SELECT json_build_object(
  'relation', n.nspname || '.' || c.relname, 'kind', c.relkind,
  'columns', (SELECT json_agg(json_build_object(
    'name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
    'not_null', a.attnotnull, 'default', pg_get_expr(d.adbin, d.adrelid)) ORDER BY a.attnum)
    FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    WHERE a.attrelid=c.oid AND a.attnum > 0 AND NOT a.attisdropped))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm', 'v', 'f') AND n.nspname !~ '^pg_'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relname;
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
                print("Startup snapshots match after approved differences (not a complete logical-equivalence proof).", flush=True)
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
    parser.add_argument("--shutdown-timeout", type=float, default=120,
                        help="Seconds allowed for graceful shutdown and statistics flush (default: 120)")
    parser.add_argument("--keep-databases", action="store_true",
                        help="Keep PostgreSQL containers after application shutdown for inspection")
    args = parser.parse_args()
    if args.java_port == args.rust_port or not all(1 <= p <= 65535 for p in (args.java_port, args.rust_port)):
        parser.error("Java and Rust need distinct valid HTTP ports")
    if args.boot_timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error("--boot-timeout and --shutdown-timeout must be positive")

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
