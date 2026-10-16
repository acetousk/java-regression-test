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

## Remaining acceptance requirement

The requested full result—identical operation order and database state after
every step, except reviewed differences—**has not been achieved**. Startup
transaction topology/metadata must be aligned or explicitly redesigned. Loader
transaction boundaries also differ (Java per-file versus Rust per-record).
Changing timestamps cannot repair these differences. The gate must stay failed
until the actual behavior is aligned; adding generic timing exceptions would not
establish equivalence.
