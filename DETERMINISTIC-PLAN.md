# Plan: deterministic execution for parity and disconnected peers

Status: proposed future contract; not an implementation or a claim of parity.
Operation/result comparison below is a future goal, beyond the current
committed-write-only harness contract in [DETERMINISTIC.md](DETERMINISTIC.md).

## 1. One execution contract, two consumers

Deterministic execution is a framework capability, not just a regression-test mode:

1. **Cross-engine comparison:** moqui-framework and mr-moqui execute the same
   commands against equivalent initial databases. The harness compares operation
   order, service results, and committed database state.
2. **mr-moqui-only P2P execution/replay:** Rust peers execute the same accepted
   service command against the same replicated state, potentially days apart after
   reconnecting, without requiring another peer to be online during execution.
   moqui-framework does not need P2P transport, durable replay, or catch-up support.

The invariant is:

```text
execute(contract version, runtime manifest, prior replicated state, command envelope)
    -> same service result, replicated database state, and effect intents
```

Same service name and parameters alone are insufficient. The initial state,
command order, code, configuration, time, IDs, and external observations must also
be identical. Determinism does not supply consensus or merge divergent histories.

Share deterministic execution semantics between engines for parity, but implement
production journals, replay, P2P transport, and recovery only in mr-moqui. Java
needs only the deterministic providers and comparison hooks required by the
harness. Rust's live-comparison and journal-replay adapters use the same service
execution path; do not build a second P2P-only service implementation.

## 2. Existing foundation and gaps

See [current protocol](DETERMINISTIC.md) and
[integration evidence](DETERMINISTIC-RESULTS.md).

- The Python coordinator currently pairs Java/Rust committed writes in memory,
  supplies shared timestamps, and compares PostgreSQL-replayed state at barriers.
- Its wall-clock-derived base is recorded for a run, but P2P replay needs durable
  command inputs independent of the coordinator's process lifetime.
- Transaction observation logs are diagnostic, not a durable replay journal.
- Historical paired startup failed at event 2 under operation-identity checks;
  the current write-only contract still needs a demonstrated full startup pass.
  Loader transaction boundaries have also differed. Keep failures visible.
- Time assignment alone does not control randomness, sequences, query ordering,
  external I/O, background writers, or all language/library clock APIs.
- A snapshot after an inner transaction cannot prove equality of uncommitted
  parent state. Independent nested commits need an explicit replay policy.

Keep historical protocol-v1 evidence intact while adding the new contract.
The current coordinator reports version 2 with version-1 engine hook messages;
any replacement wire protocol must be explicitly versioned.

## 3. Scope and ordering: choose the simple safe baseline

Start with **one serial command history per replication group**. A group contains
all tables/rows and reference data its services may read or modify. No untracked
local writers may mutate that state. Cross-group services are unsupported initially.

Use an authorized ordering authority for the first implementation; a future
consensus-backed ordering implementation can replace it behind the same contract.
Record an authority epoch and ordered position, and fence stale authorities. This
is a deliberate availability trade-off, not a claim of leaderless P2P consensus.

During a partition:

- A peer may execute already accepted commands whose predecessors it possesses.
- New requests may be durably queued as proposals, not declared globally committed.
- An isolated peer cannot finalize conflicting writes independently and still
  promise identical state without an additional conflict/consensus design.
- Any speculative execution must use isolated disposable state and must not emit
  real external effects; omit speculation from the initial implementation.

On reconnect, proposals are authorized and ordered before becoming accepted
commands. Their execution time is assigned at acceptance; an original client
business timestamp, if needed, is a separate validated input.

## 4. Durable command envelope

Specify a canonical encoding and hash with shared Java/Rust test vectors. Include:

- Protocol/contract version, group/tenant, authority epoch, ordered position,
  previous journal hash, command ID, and request idempotency key.
- Service identity and canonical typed parameters, including null versus absent,
  decimal precision/scale, timestamps, binary data, and collection ordering.
- Pinned runtime manifest: execution contract, service/component code, entity
  schema/migrations, business configuration, locale/timezone rules, and required
  reference-data versions. P2P peers pin compatible Rust artifacts. Separately,
  the parity harness records a tested Java/Rust manifest pair; Java does not need
  to consume the production replay envelope.
- Validated execution identity and required business authorization context.
  Reconnect transport authentication is separate; do not replay expiring bearer
  tokens or bypass current transport access controls.
- Assigned logical epoch milliseconds and versioned deterministic ID/random
  algorithm inputs. Specify nested scope derivation and call ordering.
- Immutable external observation values or content hashes whose bytes remain
  available for the entire replay retention period.
- Expected predecessor state/checkpoint identity and integrity/authenticity proof.

Once accepted, these inputs cannot change on retry. A reused command ID with a
changed payload is rejected. Missing code, observations, or predecessor state
blocks replay; never substitute current values or the latest service version.

Persist the accepted envelope before execution. Store the execution receipt
(result, outcome, state digest, effect-intent digest) separately, bound to its
command hash. A receipt is evidence, not a substitute for executing the service.

## 5. Framework execution context

Implement matching scoped deterministic providers in Java and Rust for comparison.
Rust additionally obtains that context from durable P2P envelopes; Java obtains it
from the harness and needs no production replay adapter. Normal mode retains
existing behavior. Deterministic services fail closed on unsupported sources of
nondeterminism.

| Source | Required deterministic behavior |
| --- | --- |
| Business time | All service-visible clocks, defaults, audits, ECAs, and date calculations use assigned logical time; reconnect never uses today's date instead. |
| Deadlines | Real monotonic clocks remain operational only; a local timeout pauses/retries work, not a peer-specific committed business outcome. |
| IDs and randomness | Use specified command-scoped algorithms/namespaces, including nested calls. Do not rely on local sequence allocation or language-default PRNGs. Never use replayable randomness for authentication secrets or cryptographic nonces. |
| Queries and iteration | Require stable ordering, explicit tie-breakers, and defined null/collation semantics wherever order affects behavior. Control map/set iteration and aggregate ordering. |
| Arithmetic and text | Pin decimal rounding/overflow, timestamp precision, Unicode/case behavior, timezone and locale. Define permitted floating-point operations or reject unsafe ones. |
| Database behavior | Audit defaults, triggers, generated columns, stored functions, sequence state, isolation, and driver conversions; no hidden real-time/random values. |
| Environment | Pin business configuration; deny arbitrary environment, filesystem, hostname, and process-state reads. Immutable resources must be manifest-addressed. |
| External reads | Resolve before command acceptance and bind observations into the envelope; replay makes no live HTTP, DNS, file, or provider lookup. |
| Scheduling and caches | Execute one application lane per group. Timers/jobs become ordered commands; caches cannot change observable results. Test cold and warm caches. |

Cover nested services, entity operations, ECAs, validators, authorization business
rules, and supported Groovy/Java/JavaScript/native entry points. Inventory direct
clock/random/I/O calls and third-party escape paths. Initially expose an explicit
allowlist of audited deterministic services; uninstrumented arbitrary code is not
made deterministic merely by setting an environment variable.

## 6. Transactions, retries, and external effects

For the initial supported service subset, one accepted command has one atomic
replicated-state commit. Joined nested transactions share its context. Reject
independently committed nested transactions until a durable subcommand/checkpoint
protocol exists; do not hide partial commits behind a top-level retry.

Commit business writes, a unique applied-command record, the service receipt,
replication cursor, and outbox intents in the **same database transaction**.
A crash before commit retries the same envelope; a crash after commit returns the
stored receipt without applying the command twice. Business failures have defined
rollback/result semantics. Transient infrastructure errors retry and do not become
machine-dependent permanent business decisions.

Email, payments, webhooks, files, and messages are outbox intents, never direct
replay side effects. Each intent has a stable command-derived identity. Only the
authorized fenced dispatcher delivers it; replaying peers do not redeliver it.
Use provider idempotency/reconciliation where available: a database transaction
alone cannot guarantee exactly-once effects at an external provider. Provider
results become later ordered commands, not live inputs during replay.

Treat operational logs, connection times, and local health metrics as explicitly
local state, outside the replicated business schema. Business audit rows remain
replicated and deterministic. Do not silently exclude existing tables merely to
make parity pass; review classification and retain the harness's strict defaults.

## 7. Reconnect and catch-up

1. Authenticate peers and exchange group, manifest, journal position/hash, and
   checkpoint identities; detect an incompatible version or fork before applying.
2. Fetch and verify a contiguous accepted command suffix. Deduplicate duplicates,
   buffer out-of-order arrivals within bounds, and request gaps via protocol events.
3. Restore a verified compatible checkpoint if the predecessor history is no
   longer retained; then replay its suffix. A checkpoint is an explicit recovery
   mechanism, not the parity test copying one engine's DB to make it pass.
4. Execute commands locally, without live peer barriers, in accepted order using
   original envelope inputs and the exact historical runtime version.
5. Verify each resulting receipt/state digest against available trusted evidence.
   Stop the affected group at the first mismatch, retain evidence, and report the
   first divergent command. Never skip it or normalize away business differences.
6. Persist progress atomically and acknowledge only durable positions. Resume on
   reconnect, message arrival, and process/transaction completion events, not
   sleep-based polling.

Use canonical logical row/state digests, not physical database-file hashes. Define
coverage for schema, rows, deletes, and any sequence state that remains in scope.
Exclude only explicitly local operational state. Hashes detect divergence; they
do not establish trust in a malicious ordering authority or execution peer.

Retain journals, checkpoints, historical runtime bundles, and external observation
blobs together for a declared offline window exceeding the required days-long
absence. If that window is exceeded, require checkpoint recovery or explicit
resync. Encrypt/access-control journals and diagnostics: service parameters and
results can contain credentials or business data.

## 8. Delivery phases and gates

### Phase 1 — Freeze contract and resolve current parity blocker

- Specify envelope encoding, state scope, transaction semantics, authority/fencing,
  supported-service inventory, and runtime manifests with golden test vectors.
- Align actual startup/loader boundaries and fix the existing event-2 divergence;
  do not ignore extra transactions or widen reviewed differences automatically.
- Demonstrate real paired boot, readiness, shutdown, and snapshot parity under
  the existing strict gate. Bootstrap supplies a versioned initial checkpoint.

### Phase 2 — Shared context and durable Rust replay

- Implement context providers and comparison-relevant nondeterminism guards in
  both engines; add production replay enforcement in mr-moqui only.
- In mr-moqui only, add journal/envelope persistence, atomic applied-command
  receipts/cursors, outbox intents, recorded execution, and standalone replay.
- Prove repeat execution from the same initial state with no hook server, no live
  external I/O, a changed wall clock, and cold/warm caches.

### Phase 3 — Cross-engine deterministic service comparison

- Extend `deterministic.py` and the harness to supply matching service inputs and
  deterministic context while preserving protocol-v1 tests and diagnostics.
  The harness may translate Rust replay fixtures into Java comparison inputs;
  Java does not need a durable journal or production envelope implementation.
- Execute the same service cases on Java and Rust; compare canonical service
  results and committed database state. Test Rust effect intents separately where
  no Java equivalent exists; explicitly report that coverage boundary. Retain
  strict transaction/operation diagnostics rather than silently treating differing
  internal execution as equivalent.
- Add shared corpus cases for IDs, dates, decimals, ordering, errors, ECAs, nested
  calls, and database defaults. Publish tested compatible manifest pairs.

### Phase 4 — mr-moqui-only P2P catch-up and recovery

- In mr-moqui only, add authenticated journal exchange, ordered acceptance, authority fencing,
  checkpoint recovery, retention, gap detection, and event-driven resumption.
- Prove restart/deduplication and partition behavior before permitting external
  effect delivery. Integrate one fenced, idempotent outbox dispatcher.

### Phase 5 — Production eligibility

- Audit every path used by each eligible service, including libraries and DB
  extensions. Reject unsupported services rather than promise universal replay.
- Add compatibility checks and ordered migration commands; retain old runtime
  bundles or migrate via an agreed checkpoint. Never replay old commands with
  today's code by default.
- Publish supported manifests/services, offline retention, recovery procedures,
  security assumptions, and measured replay throughput/storage requirements.

## 9. Required acceptance scenarios

- **Live parity:** real Java/Rust engines reach readiness and match committed
  service state/results under existing reviewed rules; empty traces cannot pass.
- **Days-late Rust replay:** mr-moqui peer A executes at T; mr-moqui peer B
  reconnects at T + 7 days with a
  skewed clock, restarts, catches up, and produces identical replicated rows,
  IDs, business timestamps, audit records, service results, and effect intents.
  Advance test clocks; do not make tests sleep for days.
- **Fresh execution:** replay performs the service computation, rather than merely
  applying recorded write sets or copying the originating database.
- **Crash boundaries:** inject crashes before commit, after commit but before ack,
  and during catch-up; no double writes, lost cursors, or duplicate receipts.
- **Delivery faults:** duplicates, missing/reordered envelopes, journal tampering,
  authority changes, and history forks are detected and handled without guessing.
- **Conflicting offline proposals:** the authority orders them on reconnect; all
  peers produce the same accepted/rejected business outcomes. No claim that both
  disconnected writers independently finalized conflicting commands.
- **External world changed:** replay still uses bound observations and produces
  no second payment/email; provider failures use explicit reconciliation.
- **Fail closed:** incompatible code/schema, missing old resources, unauthorized
  envelopes, direct wall-clock/random/I/O access, and unsupported independent
  nested commits cannot silently execute.
- **Divergence:** a deliberately different input, row, arithmetic rule, or result
  stops the group at the first affected command with actionable private evidence.

Completion requires both Java/Rust live parity and independent mr-moqui delayed
replay. Java P2P/replay support is explicitly out of scope. Passing one gate is
not evidence that the other works.
