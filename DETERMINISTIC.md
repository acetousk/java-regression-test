# Deterministic transaction comparison

This mode tests an interface and database parity; enabling it does not establish parity.
The engines must commit writes at matching boundaries and persist matching state.
See [integration results](DETERMINISTIC-RESULTS.md) for actual evidence.

## Running the isolated implementations

```sh
CARGO_TARGET_DIR=/home/user/moqui/mr-moqui-deterministic-target \
mise exec -- python java-regression-test.py --deterministic \
  --java-checkout /home/user/moqui/moqui-framework-deterministic \
  --rust-checkout /home/user/moqui/mr-moqui-deterministic \
  --differences approved-differences.json
```

Explicit worktrees are not reset to pinned submodules. Each needs its own private
runtime. Default invocations still initialize pinned repositories. Both engines
are built, then run against new disposable PostgreSQL containers with one shared
per-run field-encryption key. Existing containers are never reused/reset.

`--differences` selects the reviewed rule file (including a file named
`differences.json` if desired); the default is `approved-differences.json`.
The exact rules are copied into each run. No new data/schema exceptions are implied
by deterministic mode. `--exclude-rust-only` remains a separate, explicit option;
it is not enabled by deterministic mode.

## Protocol

The harness sets `MOQUI_DETERMINISTIC=true`, `MOQUI_DETERMINISTIC_HOOK`,
`MOQUI_DETERMINISTIC_ENGINE=java|rust`, `MOQUI_DETERMINISTIC_RUN`, and an absolute
`MOQUI_DETERMINISTIC_LOG` path. Each engine's transaction manager POSTs JSON to
`/transaction` on begin and on completion (`committed`, `rolled_back`, or `begin_failed`).

**Only PostgreSQL-derived per-transaction equality gates the run.**
The harness sets `MOQUI_DETERMINISTIC_OPERATIONS=false` and disables operation
identity checks. Java and Rust may execute different internal reads, metadata
calls and pool validation. Trace records remain diagnostic. Transaction hooks
retain commit, rollback and nested-write boundaries; committed write transactions
are paired in order and block until their database comparison succeeds.
No uncommitted-state equality is asserted. The optional operation-identity mode
remains available in the coordinator for focused tests, not the harness contract.

- **Begin** is answered at once with an engine-local operation id and the shared
  logical time: real UTC epoch milliseconds sampled once when the coordinator
  starts (`start_epoch_ms`), plus the number of write transactions paired so far.
  The assigned base is shared; different nesting still requires alignment.
- **Completion** reads that engine's PostgreSQL change data capture: a logical
  replication slot (`test_decoding`) created on each fresh container before the
  engine connects. Only transactions with an assigned xid appear, so reads and
  rollbacks are acknowledged at once. DDL-only transactions appear with no rows.
- A completion that committed changes **waits for the peer's next write**. Both
  committed states are then compared by `diff_compare()` with the reviewed
  differences, and both engines continue only on a match. Each side must
  have committed exactly one non-exempt transaction since the previous pair;
  batches fail closed because their intermediate states have not been compared.
- A Rust transaction that changes only approved `rust_only_tables` or inserts
  listed Rust seed rows has no Java peer; it is counted (`rust_only_writes`) and
  not paired. Its state remains subject to the reviewed rules at the next comparison.

Test containers run with `wal_level=logical` and `autovacuum=off`; autoanalyze
otherwise commits catalog-only transactions at arbitrary points in the stream.
`incremental.py` installs transactional PostgreSQL observation triggers before the
logical slot. Full old/new row images come from PostgreSQL, including unchanged
TOAST values; raw decoding row counts must agree with captured events. Inserts,
updates, deletes, duplicate rows and truncation update separate canonical multisets.
DDL event triggers invalidate metadata; only affected relations needing DDL row
rewrite/rename readback are rescanned. Ordinary operation checks do not dump or
scan user tables. Native sequence state is read at every paired check. A full
baseline is captured once before starting engines. Existing reviewed approval
rules run against the replayed state; unchanged canonical relation counters are
reused. This is not yet an O(changed-rows) normalizer: approval evaluation currently
walks the in-memory state.

Logical-slot before/after cursors and raw batches are journaled before replay.
Capture gaps, missing/disabled observation triggers, unsupported relations, missing
old rows and invalid events fail closed. The current adapter rejects materialized
views and foreign tables and quoted/nonstandard decoding relation identifiers.
A failed run cannot resume from an advanced slot; start a fresh run. The tracking
schema is test infrastructure and is excluded from application schema comparison.

Final incremental drain and final snapshot audit still run after verified graceful shutdown. Real monotonic
clocks protect hook/network/transaction deadlines and are not logical data clocks.

## Evidence and interpretation

- `.runs/<run>/verification.json`: overall `passed` verdict, server readiness,
  verified shutdown, final database equality, and the reviewed-rule file hash.
  A transaction-only verdict is not a successful full run.
- `.runs/<run>/deterministic-report.json`: paired writes (time, operation ids, row
  change counts, whether the raw CDC was identical), per-engine transaction counts,
  unpaired writes, trace counts, first failure.
- `.runs/<run>/transactions/write-XXXXXXXX/`: each side's CDC for that write, the
  PostgreSQL change batches and incremental comparison reports. `operation-XXXXXXXX/`
  contains per-operation reports; `final-drain/` contains the final incremental gate.
- `.runs/<run>/{java,rust}-baseline.json`: initial captured database states.
- `.runs/<run>/{java,rust}-changes.jsonl`: PostgreSQL cursor/batch journals.
- `.runs/<run>/{java,rust}-catalog.json`: last DDL metadata/sequence readback.
- `.runs/<run>/{java,rust}-deterministic.log`: engine JSONL records, including
  boot-time operation observations (see below). Diagnostics only.
- Existing boot logs, shutdown report, and final snapshots remain available.

`cdc_equal` is diagnostic: approved differences (templates, Rust-only rows) change
raw rows, so incremental state comparison is the gate. A run with no paired writes, an
unpaired write at shutdown, or any failed comparison is never a successful proof.
Snapshot and CDC files contain application data: do not publish them indiscriminately.

## Boot operation observations

The isolated engine worktrees now write `event="trace"` records to the same
`deterministic.log`, interleaved with their begin/complete hook records:

- `phase`: factory initialization (before the first bootstrap assignment).
- `metadata`: entity-definition loading.
- `AT_ENTITY`, `AT_SERVICE`, and other artifact types: stack entry/exit, including
  operations inside an existing transaction and cache-backed operations.
- `cache`: read-cache hits, misses or bypasses.
- `data`: file loading and individual record attempts.
- `jdbc`: SQL attempts and outcomes, including table/index/constraint DDL, ordinary
  reads/writes, and transaction/savepoint operations. Java also observes JDBC
  metadata result-set calls. Rust instrumentation is in the PostgreSQL driver.
- `coordinator`: begin requests recorded **before** waiting for the peer, so a
  rejected request no longer disappears from the engine log.

Each observation has a process-local `trace_sequence`, `kind`, `action`, `name`,
`outcome`, enclosing operation's `parent_sequence`, and assigned `time_epoch_ms`.
Time is null before an assignment; observations never manufacture a timestamp.
`enter`/`exit` describe stack lifetime, **not** successful commit. SQL `succeeded`
means execution returned successfully, not that its transaction committed.
Bound parameter values are not logged, but raw SQL may contain literal values:
these are private evidence files, not safe-to-publish telemetry. Log-write failures
stop deterministic execution. Disabled mode does not wrap JDBC or write traces.

The harness reports `operation_trace_counts` per engine. Full trace records remain
diagnostic and do not gate the harness. Artifact exits describe completion of
stack lifetime, not necessarily success; raw JDBC outcomes additionally distinguish
success and failure. Internal operation alignment is not an acceptance requirement.
Transaction-visible uncommitted readback is outside this committed-state contract.

## Verification tests

```sh
python -m unittest discover -s test
MOQUI_INCREMENTAL_POSTGRES_TEST=1 python -m unittest discover -s test -p test_incremental_postgres.py
```

The opt-in test starts two fresh pinned PostgreSQL containers, verifies real
insert/update/delete/truncate, rollback, large TOAST values, DDL/rename/CTAS,
sequence drift, broken capture detection, and paired operation/write/final-drain
barriers. It removes its own containers on completion. It is not a substitute
for passing the actual Java/Rust run.

## Known constraints

The coordinator does not reorder work, replace one database with the other, or
normalize timestamps outside the reviewed statistics exceptions. Engines must commit
their writes at the same boundaries (for example one transaction per data file, as
Java's loader does), or the first mismatching pair stops the run.

Captures compare committed state, not uncommitted parent transaction contents.
Sequence values are non-MVCC and remain strict. Concurrent writers inside one engine
fail the run. Deterministic time does not by itself control entropy, external
services, or arbitrary third-party clocks.
