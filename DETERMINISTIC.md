# Deterministic transaction comparison

This mode tests an interface and database parity; enabling it does not establish parity.
The engines must actually emit matching operations and persist matching state.
See [integration results](DETERMINISTIC-RESULTS.md) for actual evidence and the
current operation-order blocker.

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
`MOQUI_DETERMINISTIC_LOG` path. The loopback hook accepts protocol-v1 JSON POSTs at
`/transaction`. Begin events contain engine-local sequence, parent sequence, and
artifact identity/stack (`type`, `sub_type`, `name`). Completion events contain the
assigned operation id and `committed`, `rolled_back`, or `begin_failed` outcome.

Neither engine receives a begin response until both arrive with matching metadata
and order. Both receive the same operation id and epoch milliseconds, advancing
one millisecond per paired operation from 1760000000000. Joined transactions reuse
their operation; independent nested transactions obtain another operation and
restore their parent's assigned clock afterward. Bootstrap/nontransactional work
must be represented explicitly rather than silently using real time.

At each paired completion, while both application lanes wait for acknowledgement,
the harness captures both databases and runs the existing full snapshot comparator.
Only the reviewed differences apply. A mismatch fails the barrier and all further
operations. Successful comparison acknowledges both engines. Final snapshots are
still compared after verified graceful shutdown. Real monotonic clocks protect
hook/network/transaction deadlines and are not logical data clocks.

## Evidence and interpretation

- `.runs/<run>/verification.json`: overall `passed` verdict, server readiness,
  verified shutdown, final database equality, and the reviewed-rule file hash.
  A transaction-only verdict is not a successful full run.
- `.runs/<run>/deterministic-report.json`: paired requests/responses, operation
  order verdict, comparison count, engine-log verification, first failure.
- `.runs/<run>/{java,rust}-deterministic.log`: ordered engine JSONL records.
- `.runs/<run>/transactions/op-XXXXXXXX/`: snapshots, exact byte differences,
  schema diffs and summary after each matched transaction.
- Existing boot logs, shutdown report, and final snapshots remain available.

An empty, incomplete, unmatched, or failed stream is never a successful proof.
A successful hook assignment alone is not a database comparison. Engine logs must
match acknowledged hook events. Snapshot files may contain sensitive application
data: do not publish them indiscriminately.

## Known constraints

The coordinator intentionally does not align different transaction topologies,
ignore extra engine operations, reorder work, replace one database with the other,
or normalize timestamps outside the reviewed statistics exceptions. Existing
schema/content/runtime differences may therefore stop a deterministic run early.

Per-completion captures compare committed state, not uncommitted parent transaction
contents. Sequence values are non-MVCC and remain strict. Correct captures require
the engines to honor their single application-execution lane, including background
writers. Deterministic time does not by itself control entropy, external services,
or arbitrary third-party clocks. Full startup parity is a separate verified result,
not a consequence of introducing this protocol.
