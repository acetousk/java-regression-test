# Java / Rust Moqui regression tests

For the opt-in transaction-clock coordinator and worktree integration, see
[Deterministic transaction comparison](DETERMINISTIC.md). This mode pairs the
engines' committed write transactions using PostgreSQL change data capture and
compares both databases after each pair; operation order and logs are not compared.

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

The target is identical schema and data after empty-database startup for the shared
framework. Rust additions must be inventoried separately, not silently ignored.
No application components are installed for this baseline.

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

Rust builds share `${XDG_CACHE_HOME:-$HOME/.cache}/moqui/target` by default.
Set `CARGO_TARGET_DIR=/path` to override, or `CARGO_TARGET_DIR=` to opt out and
use the original checkout-local build/run paths.

Shared mode locks build-and-copy with the same protocol as guarded `moq`, records
and launches private `.runs/bin/moqui`, and preserves running executable inodes.
Checkout switches invalidate local/path packages only; registry/git dependencies
stay cached and same-checkout builds remain incremental. No existing processes are
stopped or restarted, and old checkout caches are not migrated or removed.
Use guarded controller/`moq` builds only; bare Cargo bypasses these safeguards.
Do not run `cargo clean` against a shared cache in use.

Step 3 creates two fresh, disposable PostgreSQL containers using PostgreSQL 18.6,
locked to the immutable image index
`postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`
in `java-regression-test.py` (no command-line version override),
verifies identical image IDs and empty databases, and starts both engines. Java
uses port 8080 and Rust 8081. Neither runtime currently ships a dedicated demo
configuration, so the controller copies each `MoquiDevConf.xml` to a private run
configuration, retains its demo loading (`entity_empty_db_load=all`), and overrides
PostgreSQL connectivity. Both engines receive the same randomly generated,
per-run field-encryption passphrase through their private configs and child
process environments, overriding existing runtime keys without modifying `.env`. It downloads PostgreSQL JDBC 42.7.7 into Java's runtime
when missing. It never resets or connects to a pre-existing database.

Step 3 waits for seed loading and completed application initialization, including
Java's final Jetty server-start event (after shutdown-hook registration), as well
as listening TCP ports. It sends SIGTERM to both process groups before waiting
up to 120 seconds for shutdown. Each engine must log a new artifact-bin flush
after SIGTERM; Java must also report final factory destruction. Forced kills,
unexpected exits, or missing shutdown evidence fail the run before snapshots.
Shutdown verification is recorded in `shutdown.json`. Run evidence uses UTC
timestamp directories: `.runs/YYYY-MM-DD_HH-MM-SS.ffffffZ/`.

### Step 4 — per-transaction incremental PostgreSQL verification

The acceptance contract is matching PostgreSQL changes/state per committed write
transaction, under existing approved differences—not identical engine operations.
Java and Rust may perform different reads, pool validation and internal calls.
Transaction completion calls the running Python controller, which consumes changes
**from each PostgreSQL database** and blocks each writer until its peer's write
transaction compares equal. Mismatches stop execution. Reads and rollbacks do not
need matching operation identities. Engine-reported write sets are not evidence.
Reuse the running controller; resume waiting engines on completion events, not
sleeps or timed polling.

Implementation requirements:

1. Establish equivalent initial databases and install PostgreSQL change capture
   **before either engine starts**. Persist the baseline and each database's own
   capture cursor; LSNs/transaction IDs are local and must not be compared across
   databases.
2. Hook transaction completion and pair committed write transactions in order.
   Hold both writers until Python acknowledges database equality. Retain nested
   transaction context; internal operation identities/order are diagnostics only.
3. Implement `diff_compare()` using the existing PostgreSQL CDC reader as its
   input. Apply complete, ordered committed transactions to separate canonical
   state indexes; handle inserts, updates, deletes and truncation, including old
   keys/key changes and missing/null values. Recompare affected keys/relations
   against the verified prior state, preserving duplicates and numeric precision.
   Compare state, not raw WAL text or physical row/event order. No full dump or
   table scan on every transaction. Apply only the existing reviewed differences.
4. Cover **schema and sequence state**, not only row CDC. The current
   `test_decoding` stream does not provide full DDL/sequence coverage. Obtain
   schema changes from PostgreSQL catalog/event-trigger evidence and track
   affected sequence state explicitly. Missing tables/indexes must fail even
   when both row-change streams are empty.
5. Preserve transaction semantics: PostgreSQL logical decoding exposes committed
   changes, not uncommitted parent contents. Rollback discards transactional
   changes. Do not force extra commits or claim uncommitted-state verification.
   Independent nested commits and nontransactional sequence effects remain checked.
6. Persist operation identity, capture cursors, change batches, exact mismatches
   and acknowledgements. Capture gaps, missing peers, unknown/untracked writes,
   failed comparisons or incomplete shutdown must fail closed. Test deliberate
   row/schema/sequence divergence, rollback, nested transactions, no-ops and
   capture loss. Finish only after readiness, graceful shutdown and a final CDC
   drain leave no unmatched write transactions or changes.

Implemented verification path: `diff_compare()` replays full row images from
PostgreSQL trigger events carried through logical decoding. The controller invokes
it at committed-write barriers, rather than taking per-write row snapshots. DDL metadata and native sequence state remain
checked; only DDL-affected relations may need targeted row readback. A baseline is
captured before engines start; a final snapshot is retained as an independent audit.
See [protocol, limitations and evidence](DETERMINISTIC.md). Operation-identity
checks are disabled in the harness; PostgreSQL equality remains strict under the
existing approvals. Uncommitted state is not verified; unsupported capture paths
fail closed.

### Current snapshot comparator

The existing Step 4 implementation connects with container-local `psql`, creates
snapshots inline in `java-regression-test.py`, then calls `snapshot_compare()`.
It captures schema-only dumps, table/materialized-view rows, and sequence states. Rows use a typed JSON representation with exact numeric
precision and sorted object keys; comparison ignores row order but preserves
duplicates. Row reads use a read-only repeatable-read transaction. Schema capture
and sequence reads require idle databases: sequences are not MVCC-snapshot data.
Differences fail the run and produce `comparison.json`, `schema.diff`, and
`summary.json`. The summary inventories Java-only/Rust-only relations (including
empty tables), shared column/type/default/nullability differences, and unmatched
row counts and differing column multisets per table. Column multisets are only
diagnostics: equal column multisets do not imply equal rows. Rust-only does not
mean approved. `approved-differences.json` permits the exact reviewed
theme resource seeds, full-text storage designs, and explicitly listed statistics
timing fields documented in `STARTUP-PARITY.md`. Statistics timing includes
slow-hit classifications/counts, which depend on measured elapsed times; operation
identities, total hit counts, host values, duplicate rows, and schema remain strict.
`statistics_bin_boundaries` also accepts different bin splits when the aggregate
hit count and every non-timing field except the bin id match. Split bins are
collapsed only in the comparison copy; only id gaps caused by removed bins are
closed. Other id differences and sequence states remain strict.
Missing indexes, changed source text, and unexpected resources still fail.
Timestamps on shared theme rows and all other non-statistics rows remain compared.
Resources explicitly approved as absent on one engine are exempt as whole rows
(including their otherwise unmatchable timestamps). `summary.json` also reports
per-operation bin hit-count multisets without timing/id noise as a diagnostic
only; this does not relax the full snapshot gate.

Rust seed rows for Rust-only features are accepted only as the exact keys in
`rust_seed_additions`, and Java's LLM cleanup job rows only as the exact keys in
`java_seed_additions`. The statistics they cause (one refresh and one create per
row during the empty-database load) are accepted only when a bin differs by exactly
that many hits. `comparison.json` reports `statistics_equal_after_approved_differences`
for the artifact hit and bin rows and the hit sequence position; it is a separate
verdict, not a pass of the full gate. Rust counts its FK existence reads,
load-report counts, and create-or-update UPDATE probes that match no row under sub
types of their own (`fk-check`, `load-report`, `update-probe`); those
bins are set aside and listed (`rust_only_statistics`), not compared. The bins Java
writes after its factory restart are set aside only as the exact listed bins
(`java_restart`).

Raw `comparison.json`, `schema.diff`, and `summary.json` retain all differences.
`comparison.json` additionally lists applied approvals, remaining unapproved
record differences, and gate results after approvals. `unapproved-schema.diff`
contains the schema differences remaining after the exact approved FTS definitions
are removed. These allowances do not establish equivalent search behavior.
The complete comparison report is also printed on failure: every differing schema
byte range includes both byte offsets and exact hex bytes, and every unmatched
canonical row/sequence record includes exact UTF-8 hex bytes and its multiplicity.
Nothing is truncated. These are comparison-encoding bytes, not storage-page bytes.
Failure output contains database values; treat terminal/CI logs as sensitive.

This is an initial snapshot comparator, **not the complete equivalence tool in the
plan**. Schema dumps are compared textually; custom-type canonicalization, large
objects, foreign-table contents, precise primary-key/column diagnostics, and
unsupported incremental adapters remain incomplete. Incremental mode establishes
its own initial baseline and tracks ordinary PostgreSQL tables; it does not claim
uncommitted transaction visibility or full engine equivalence. Startup log events and TCP accessibility are not verified HTTP health.

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
mise exec -- python java-regression-test.py --java-port 8080 --rust-port 8081 --boot-timeout 600 --shutdown-timeout 120
```

Listed `rust_only_tables` are set aside with their rows, relation metadata, and
owned table/index/constraint DDL only when absent from Java. Raw evidence remains;
unlisted tables and shared columns are still compared.

`rust_only_columns` approves the three listed Rust column definitions, including
metadata and table DDL, only when absent from Java and nullable with no default.
Non-null values are not discarded: they remain a comparison failure.
`rust_only_ddl` approves only the exact `search` schema and `pg_trgm` extension
creation/ownership/comment blocks. It does not approve other objects inside the
schema, changed extension definitions, or objects also present in Java. All raw
snapshots and raw differences remain intact.

`template_differences` approves only the listed row keys and fields. Five reviewed
expression templates use the bidirectional `elvis_or` validator: it tokenizes
`${...}` expressions, converts Groovy `?:` to JavaScript `||` (and back), and
requires both canonical token streams to match the pinned Java template. Quoted
strings and literal text are preserved; expression whitespace is canonicalized.
Unsupported syntax, changed operands/text, duplicate or missing rows, and
unlisted templates remain strict. This is a bounded syntax validator, not a
claim that Groovy and JavaScript truthiness are equivalent for arbitrary values.
The listed job-detail URL uses an exact Java/Rust value pair instead. Approvals
change only comparison copies; timestamps and all other fields stay strict.

### Optional Rust only comparison scope

`--exclude-rust-only` enables the checked-in `rust-only-sources.json`; default
comparison is unchanged. Capture, runtime files, Java logging, and schema dumps
are never modified. Schema differences (including operational DDL) still fail;
this feature excludes **rows only**, not schema objects or sequences.

Source-file exclusions resolve the five SFTP demo records (including nested job
parameters) and the four named authentication enum groups from Rust XML plus
entity PK metadata: 33 distinct Enumeration PKs and four types (37 source
records). A PK that occurs in more than one source group is a source collision;
it is retained, not silently assigned to either group.
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
                 rust_only_manifest=controller.RUST_ONLY_SOURCES,
                 source_root=Path("/path/to/source-checkout-parent"))
```

`source_root` defaults to this harness directory and must contain `mr-moqui/`.
CLI equivalent: `--exclude-rust-only --source-root /path/to/source-checkout-parent`.
Missing source files or unexpected source counts fail clearly; there is no
implicit fallback to another worktree and no submodule initialization by the
filter. Unit tests build temporary source fixtures.

Integration with the independent schema-mapping work: apply exclusions to raw
snapshot dictionaries **before** any naming normalization, using
`controller.filter_snapshots(java, rust, manifest, source_root)`; it returns
`(java, filtered_rust, audit)`. Preserve `audit` in the combined report. Keep
schema-mapping options independent; this change does not normalize schema or
records and does not claim complete equivalence.

Run controller unit tests with `mise run test` (or all tests with
`python -m unittest discover -s test -v`). End-to-end builds/startup have been exercised; see `STARTUP-PARITY.md` for the
remaining parity gaps.

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
