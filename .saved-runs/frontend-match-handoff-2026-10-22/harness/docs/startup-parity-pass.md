# Deterministic startup/shutdown pass

Run `2026-10-17_18-58-47.909101Z`, harness `6bad7ed` (after PRs #14 and #15).
Local evidence: `/home/user/moqui/java-regression-remove-restart/.runs/2026-10-17_18-58-47.909101Z/`.

`verification.json` records:

- `passed`, `servers_started`, `shutdown_verified`, `final_databases_equal`: true.
- 116 paired writes and 116 database comparisons; no error or unpaired writes.
- `per_transaction_databases_equal` and `final_incremental_equal`: true.
- 12 approved Rust-exempt writes; no Java-exempt writes.
- Approved differences SHA-256: `eae7e91a595e85f17ce618714ac216b915323469353c35caebbbdf5edd380d1e`.

Both HTTP servers reached readiness on ports 18080/18081. Both shut down gracefully
and flushed artifact bins. Java's boot log confirms Elastic client/index startup
was enabled. Autonomous background writers remain disabled in deterministic mode.

Existing binaries were reused without rebuilding:

| Artifact | SHA-256 |
| --- | --- |
| `/home/user/moqui/moqui-framework-deterministic/moqui.war` | `6329493b9af85b155259dc2ca9075800d11c329aad982c82c07bf09a341ea796` |
| `/home/user/moqui/mr-moqui-deterministic-target/debug/moqui` | `b10ac379a50f741bc602edd7090a6c02d8bf343f2cd2e7b94d35ccd403a75b2c` |

Runtime checkouts were `/home/user/moqui/moqui-framework-deterministic` and
`/home/user/moqui/mr-moqui-deterministic`. Each engine used a fresh disposable
PostgreSQL container, removed after evidence capture.

This establishes startup/shutdown committed database parity under the reviewed
exceptions for these instrumented artifacts. It does not establish arbitrary
service equivalence, internal operation ordering, or uncommitted-state equality.
Raw snapshots and traces remain local because they contain application data.
