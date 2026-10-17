# Saved regression runs

`2026-10-17_18-58-47.909101Z/` contains the successful deterministic empty-database
startup/shutdown run: all 116 paired writes, readiness, graceful shutdown, final
incremental comparison and final snapshot comparison passed under the approved
differences copied into the run. See `verification.json` and
[`docs/startup-parity-pass.md`](../docs/startup-parity-pass.md).

The disposable database password and field-encryption key were redacted from
`java-demo.xml` and `rust-demo.xml` before publication. All other evidence files
are unchanged. This is saved evidence, not a resumable database or deployment
configuration. Logs include local paths and fixture data.
