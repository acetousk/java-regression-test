# Phase-two database validation

Change 1 runs isolated checks against the currently built Java and Rust artifacts.
It copies both runtimes, starts disposable PostgreSQL containers and uses HTTP
ports 28080 and 28081. It never edits the shared build manifest or checkouts.

```sh
mise exec -- python tools/phase_two_db.py --output .runs/phase-two-db/paired-new
```

Use a new output directory each time. Java 21+ is required; `--java-home` can
select it explicitly. The runner exits nonzero if whole-database identity fails,
even when selected business scenarios pass. Evidence contains database values
and session credentials and must remain private.

The runner inventories current source services/specs (excluding disabled component
templates), performs enumeration and unit/conversion scenarios through authenticated
Tools service calls, and checks persisted state and selected business deltas.
Raw selected-row verdicts compare the ordered SQL JSON output as actual UTF-8
bytes, retaining before/after files and hashes. Separate semantic business
projections explicitly omit `last_updated_stamp` and preserve decimal precision. Full schema, typed JSON
row multisets and native sequences are compared after graceful shutdown with the
existing harness. Raw and existing-approval verdicts remain separate.

Change 2 reproduces all 45 selected Rust specs (44 regression specs plus the explicitly
requested ETL acceptance scenario) without rebuilding:

```sh
python tools/phase_two_rust.py --output .runs/phase-two-db \
  --runtime .runs/phase-two-db/paired-new/engines/rust/runtime
```

The tracked runner includes every selector, runs three independent scratch
PostgreSQL databases sequentially, retains JUnit/logs and records exact commands,
exit codes and the binary hash in `rust-commands.json`. It refuses to overwrite
existing Rust results. The feature assertion count is recorded in the report and depends on the pinned
current source; later source changes can change that count. Call-count coverage is
plain text in `rust-service-coverage.txt`; counts include refusals and nested calls,
not per-service success proof. Rust suites are not Java parity tests.

```sh
python tools/phase_two_report.py --run .runs/phase-two-db --paired paired-new
```

Change 3 combines JUnit evidence and paired results, retaining budget warnings,
unrun source coverage and noncomparable services. Historical ERP business specs
are inapplicable when their components are absent; this runner installs none.

When Rust rerun evidence is retained in a separate directory, select it explicitly:

```sh
python tools/phase_two_report.py --run .runs/phase-two-db --paired paired-05 \
  --rust-results .runs/phase-two-db/reproduced
```
