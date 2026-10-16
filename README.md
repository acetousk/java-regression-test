# Java / Rust Moqui regression tests

```text
java-regression-test/
  java-regression-test.py
  mise.toml
  moqui-framework/          # Pinned Java framework submodule
    runtime/                # Pinned nested Java runtime submodule
      component/            # Java dependencies
  mr-moqui/                 # Pinned Rust repository submodule
    runtime/                # Rust's own tracked runtime
      component/            # Rust dependencies, including its Mantle forks
```

There is no shared runtime, top-level runtime directory, or runtime symlink.
Each engine is built and started from its own checkout using its own runtime.

Install the toolchains and run all four steps using mise (requires Linux and a
working Docker-compatible CLI):

```sh
cd /home/user/moqui/java-regression-test
mise trust
mise install
mise run build
```

Every run starts from the pinned source revisions (not upstream HEAD), builds
Java with Gradle `clean build` and Rust incrementally with `cargo build --locked`,
and creates new empty databases. Rust compiler caches are preserved. Existing database containers are never reused,
even with `--keep-databases`. Local source edits are not discarded.

Step 1 initializes the pinned repositories and private Java runtime. Step 2 builds
`moqui-framework/moqui.war` and `mr-moqui/target/debug/moqui`. Artifact paths,
checksums, and their separate runtime paths are recorded in `.runs/build.json`
only after both builds succeed. Gradle comes from the Java checkout's wrapper;
the controller has no third-party Python dependencies.

Step 3 creates two fresh, disposable PostgreSQL containers using PostgreSQL 18.6,
locked to the immutable image index
`postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`
in `java-regression-test.py` (no command-line version override),
verifies identical image IDs and empty databases, and starts both engines. Java
uses port 8080 and Rust 8081. Neither runtime currently ships a dedicated demo
configuration, so the controller copies each `MoquiDevConf.xml` to a private run
configuration, retains its demo loading (`entity_empty_db_load=all`), and overrides
PostgreSQL connectivity. It downloads PostgreSQL JDBC 42.7.7 into Java's runtime
when missing. It never resets or connects to a pre-existing database.

Once both engines are listening on their TCP ports, step 3 stops both application
process groups. Early exits and startup timeouts fail the run.

Step 4 connects with container-local `psql` and creates snapshots inline in
`java-regression-test.py`, then calls its `snapshot_compare()` function.
`diff_compare()` is the separate incremental entry point and currently fails
explicitly because change tracking has not been implemented. It captures schema-only dumps, table/materialized-view
rows, and sequence states. Rows use a typed JSON representation with exact numeric
precision and sorted object keys; comparison ignores row order but preserves
duplicates. Row reads use a read-only repeatable-read transaction. Schema capture
and sequence reads require idle databases: sequences are not MVCC-snapshot data.
Differences fail the run and produce `comparison.json` and `schema.diff`.
The complete comparison report is also printed on failure: every differing schema
byte range includes both byte offsets and exact hex bytes, and every unmatched
canonical row/sequence record includes exact UTF-8 hex bytes and its multiplicity.
Nothing is truncated. These are comparison-encoding bytes, not storage-page bytes.
Failure output contains database values; treat terminal/CI logs as sensitive.

This is an initial snapshot comparator, **not the complete equivalence tool in the
plan**. Schema dumps are compared textually; custom-type canonicalization, large
objects, foreign-table contents, precise primary-key/column diagnostics, and
incremental change tracking are not implemented. No equivalence baseline is
established for incremental mode. TCP accessibility is not verified HTTP health.

Snapshots, configs, reports, and logs remain under `.runs/<run-id>/`; the directory
is private because it contains database contents and disposable credentials.
Containers are removed on exit, including comparison failure. To keep them alive
after both applications stop:

```sh
mise exec -- python java-regression-test.py --keep-databases
```

The controller prints password-free connection commands for each container:

```sh
docker exec -it <container-name> psql -U moqui -d moqui
```

It also prints `docker rm -f -v <container-name>` for manual cleanup.

Generated configs retain each runtime's other dev settings; external effects are
not stubbed yet. Use only isolated test environments.

Override ports and timeout with:

```sh
mise exec -- python java-regression-test.py --java-port 8080 --rust-port 8081 --boot-timeout 600
```

### Optional Rust only comparison scope

`--exclude-rust-only` enables the checked-in `rust-only-sources.json`; default
comparison is unchanged. Capture, runtime files, Java logging, and schema dumps
are never modified. Schema differences (including operational DDL) still fail;
this feature excludes **rows only**, not schema objects or sequences.

Source-file exclusions resolve the five SFTP demo records (including nested job
parameters) and the four named authentication enum groups from Rust XML plus
entity PK metadata. There are 33 distinct Enumeration PKs and four types, but
34 Enumeration source occurrences: `OctGoogle` occurs in both OAuth and OIDC.
That source collision is retained, not silently assigned to either group.
Only a single Rust row with the exact source values and all unset fields null
can be excluded. Empty XML attributes load as null; only loader-generated
`lastUpdatedStamp` is disregarded for seed matching. Edited rows, extra values,
duplicate PKs, and keys present in Java remain visible. The manifest's narrow
Java physical-PK guards detect shared keys without schema normalization.

Explicit **operational** exclusions instead remove all Rust rows in precisely
`search.moqui_logs`, `search.moqui_http_log`, and `search.document_index`.
The manifest cites their Rust implementation. The last table is index registry
metadata, including business-index metadata, not the documents themselves.
Other search tables, artifact hits, cluster membership, and shared themes are
not excluded. No PostgreSQL search logging is added to Java.

`comparison.json` includes `rust_only_exclusions`: exact raw record/index,
source entity/PK/values and XML locator (or operational table/reason), source and
manifest SHA-256s, exclusion counts, and reasons for retaining seed candidates.
Raw snapshots are unchanged; audit reports contain sensitive row values too.

For offline integration, optional **keyword-only** arguments preserve the
existing three positional comparator arguments:

```python
snapshot_compare(java_snapshot, rust_snapshot, report_dir,
                 rust_only_manifest=Path("rust-only-sources.json"),
                 source_root=Path("/path/to/source-checkout-parent"))
```

`source_root` defaults to this harness directory and must contain `mr-moqui/`.
CLI equivalent: `--exclude-rust-only --source-root /path/to/source-checkout-parent`.
Missing source files or unexpected source counts fail clearly; there is no
implicit fallback to another worktree and no submodule initialization by the
filter. Unit tests build temporary source fixtures.

Integration with the independent schema-mapping work: apply exclusions to raw
snapshot dictionaries **before** any naming normalization, using
`rust_only.filter_snapshots(java, rust, manifest_path, source_root)`; it returns
`(java, filtered_rust, audit)`. Preserve `audit` in the combined report. Keep
schema-mapping options independent; this change does not normalize schema or
records and does not claim complete equivalence.

Run controller unit tests with `mise run test` (or all tests with
`python -m unittest discover -v`). End-to-end startup has not yet been
verified.

The parent Git submodule entries pin both framework commits. The Java framework's
nested submodule entry pins its runtime; Rust's runtime is already tracked by its
repository. Recursive submodule initialization clones missing repositories and
restores pins without advancing to upstream HEAD.

Java and Rust component dependencies must be installed and pinned independently;
never share their component directories. Component installation and deterministic
regression hooks are not implemented yet. Java requires its runtime setup before
the build; Rust ships its framework runtime files in its checkout.

The new nested runtime registration is staged in the Java framework checkout.
Commit and publish that framework change first, then update and commit the parent's
framework pin. Until then, fresh clones of the old framework commit do not contain
the runtime submodule registration.
