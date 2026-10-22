# Deterministic integration results

## Scope

Two separate subagents implemented the engine changes in isolated worktrees:

- Java: `/home/user/moqui/moqui-framework-deterministic`, branch
  `test/deterministic-clock`, based on `llm-client` (`e71e4afb`).
- Rust: `/home/user/moqui/mr-moqui-deterministic`, branch
  `test/deterministic-clock`, based on `c3c7b4b`.

The original engine checkouts and Java's staged private-runtime setup were not
replaced. The Python harness uses the worktree options documented in
[DETERMINISTIC.md](DETERMINISTIC.md). No source changes were pushed.

## First real cross-engine run: FAIL, correctly

Latest evidence: `.runs/f314280c5fb7489080262be8f88da996/`, using Java
`4ad3d23ac914df0316364b95d6b48af43a41a1ce` and Rust
`e605b4f1f9d513fc3ced311e5784ccd77556eb8e`. The first run at
`.runs/8b12000788a54274a3525c539e6c0ebe/` found the same event-2 divergence.

The harness rebuilt both actual artifacts, created two new PostgreSQL 18.6
containers from the pinned immutable image, verified empty databases, and started
both engines with the same deterministic hook. Only the selected reviewed
`approved-differences.json` rules were supplied; their exact copy and hash are in
run evidence. Neither database was copied from another engine.

**Event 1 succeeded:** both real engines requested the same bootstrap operation,
received `op-00000001` / `time_epoch_ms=1760000000000`, and wrote matching assigned
time in their respective `deterministic.log` JSONL files.

**Event 2 diverged before permission to proceed:**

| Engine | Type | Subtype | Artifact |
| --- | --- | --- | --- |
| Java | `AT_ENTITY` | `list` | `moqui.entity.view.DbViewEntity` |
| Rust | `AT_OTHER` | `transaction` | `bootstrap` |

Both requests had sequence 2 / parent sequence 1. This is a real startup
operation/transaction-topology difference, not a wall-clock difference. The
coordinator rejected it rather than assigning another timestamp, skipping an
operation, or widening approved differences.

`verification.json` records `passed=false`, `servers_started=false`, and
`final_databases_equal=null`. No transaction-completion database comparison was
reached. Stopped database snapshots and shutdown/boot evidence were retained; the
test containers were removed. **This is not a full database-parity proof.**

## Real PostgreSQL coordinator/comparator test: PASS

Separate evidence:
`.runs/deterministic-agents/coordinator-postgres-probe/`.

This deliberately uses Python test clients, **not the Java/Rust engines**. It
verifies the remaining barrier/capture/comparison path against two fresh pinned
PostgreSQL 18.6 containers:

1. Both clients obtain exactly the same supplied timestamp and commit identical
   schema/data. The real full snapshot comparison passes; both completion requests
   are acknowledged.
2. A second transaction deliberately commits a different value on one side. The
   real comparator finds the difference and both completion requests receive HTTP
   409. The deterministic report remains failed.

No approval exceptions were used in this probe. Snapshots and exact comparison
reports are retained. This proves successful per-transaction capture/comparison
and rejection work with real PostgreSQL, but does not turn the failed engine run
above into a pass.

## Engine-local validation

- Rust commit `e605b4f1f9d513fc3ced311e5784ccd77556eb8e`: actual binary built;
  **878 core tests passed, 1 ignored**, plus the isolated protocol/failure suite.
  A fresh PostgreSQL server loaded 1,389 records, reached HTTP health 200, and
  shut down with **2,782 acknowledged hook events / zero open operations**.
- Java commits `2304779f7c7468a6cadef622a0e2709b1d3dbb6d` and
  `4ad3d23ac914df0316364b95d6b48af43a41a1ce`: actual WAR built;
  **15 focused tests passed**. Real Jetty/PostgreSQL smoke loaded 1,354 records,
  served `/status` and `/Login` with HTTP 200, and completed **244 operations**.
  Review caught and corrected the initial artifact-telemetry exclusion. The final
  mode retains collection and synchronously persists hits/bins during shutdown;
  independent PostgreSQL queries confirmed **2 artifact hits, 99 bins, and 2,814
  aggregate bin hits**, including 3 login-related bins. No extra approval was added.
- Python controller: **72 unit tests passed**. Includes exact operation matching,
  nested scopes, no-peer timeout, per-step comparison rejection, actual HTTP
  exchange, required engine logs, custom approval rules, worktree selection,
  external Rust target directory, and bounded read-only snapshot capture.

Detailed subagent reports are under `.runs/deterministic-agents/`.

## Boot-operation logging update

Operation observations are now instrumented in both isolated worktrees, below the
transaction barrier: entity/service stack activity, metadata, read caches, loader
files/records, and JDBC/PostgreSQL SQL including schema DDL. See
[observation semantics and remaining coverage](DETERMINISTIC.md#boot-operation-observations).

Validation:

- Python: **85 tests passed** (including interleaved trace validation).
- Java: **15 focused tests passed**, including actual H2 DDL, insert, failed SQL,
  and loader evidence. Real WAR/fresh PostgreSQL smoke passed with 244 completed
  operations, `/status` and `/Login` 200, and persisted statistics retained.
  Preserved log: `.runs/boot-operation-logging-java/deterministic.log` — **16,140
  observations**, including 164 successful table-creation calls and 1,319 loader
  record attempts. This is an engine-local smoke, not paired equivalence.
- Rust: **878 core tests passed, 1 ignored; 114 host unit tests passed**. Isolated
  protocol suite passed with an additional real embedded-PostgreSQL child that
  checks successful DDL/inserts, failed SQL, assigned timestamps and no logged
  bound parameter values.
- New paired run `.runs/7ca436ce95d74227aa2a586a95c32007/` still **fails event 2**.
  Both local logs now retain rejected coordinator attempts; Java also shows the
  attempted `DbViewEntity` entity operation and Rust its metadata loading.
  Neither engine was allowed to proceed past the mismatch.

These changes improve evidence; they do not complete semantic operation pairing
or resolve the startup topology blocker.

## PostgreSQL incremental verification implementation

`incremental.py` now replays PostgreSQL-origin old/new row events carried by logical
decoding. `diff_compare()` replaces per-write row snapshots; schema invalidation,
targeted DDL row readback, native sequence checks, durable cursor/batch evidence,
capture-integrity checks and final drain are wired into the controller.
The harness gates committed write transactions, not JDBC outcomes or operation
identity. Optional synchronous operation callbacks remain covered by focused tests.
Open-transaction writes are not transaction-visible uncommitted-state verification.

Validation includes the Python suite, focused Java/Rust engine-hook tests, and a
real two-container PostgreSQL test of row changes, TOAST, rollback, DDL/rename/CTAS,
truncation, sequence divergence, disabled capture and operation/write/final barriers.
See [test commands](DETERMINISTIC.md#verification-tests).

Actual rebuilt-engine evidence:
`.runs/2026-10-17_00-15-38.312085Z/`. The initial incremental baselines match.
That historical run enabled the optional operation gate and rejected **operation 1**:
Rust executed `SELECT 1` while Java called JDBC `getTables` for `DB_VIEW_ENTITY`.
It demonstrates rejection of different operation streams, **not a successful
Java/Rust parity run**. The current harness disables that operation gate; CDC-only
runs must not be interpreted as operation-order proof.

## JSON-driven exemption checkpoint

Paired rebuilt-engine evidence: `.runs/2026-10-17_02-31-23.001427Z/`.
The selected JSON's `transaction_exemptions` is interpreted by `approvals.py`;
PostgreSQL DDL events now identify affected tables and index owners. This fixes
approved search setup being incorrectly paired with Java's seed load. It does
not change the existing specialized snapshot normalization algorithms.

- **31 committed-write pairs passed**, with operation checks disabled.
- **3 Rust transactions were exempted** under the JSON rules.
- **Write 32 failed**: Java committed a `StatusItem/create` statistics bin (31
  hits); Rust committed a `SystemMessageRemote/create` statistics bin (1 hit).
  Schema equality passes; normalized committed data differs. No new statistics
  exception was added, and this is not a complete startup pass.
- Python suite: **115 tests run, 114 passed, 1 opt-in test skipped**.
- The real two-container PostgreSQL integration test separately **passed**,
  including approved DDL/index setup, mixed-transaction rejection, and existing
  row/sequence/capture-integrity checks.

For comparison, PR #22's fresh-connection-query change alone did not advance the
write gate: with-patch `.runs/2026-10-17_02-08-45.354269Z/` and without-patch
`.runs/2026-10-17_02-13-14.213419Z/` both passed two pairs and failed at write 3.
The checkpoint run uses the same isolated worktrees (including their existing
uncommitted instrumentation/startup changes) with that Rust patch applied.

## Remaining acceptance requirement

A successful full Java/Rust startup run under the current committed-write contract
**has not been demonstrated here**. Historical operation-order failures above are
not the current acceptance gate, but transaction boundaries still need to align.
Loader transaction boundaries have differed (Java per-file versus Rust per-record).
Changing timestamps cannot repair boundary or state differences; adding generic
timing exceptions would not establish equivalence.
