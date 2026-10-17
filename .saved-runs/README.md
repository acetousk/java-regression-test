# Saved regression evidence

- [2026-10-17_03-22-50.677356Z visual sweep](2026-10-17_03-22-50.677356Z/ui-test/RESULTS.md)
  — 42 documents, 744 activities in apps/vapps/qapps; failed/incomplete.

These are archived evidence, not passing baselines. The visual sweep captured
462 unique browser states and successfully opened 17 dialogs; it did **not**
inventory or cover every application dialog, or execute complete business stories.
See each run's `ui-test/summary.json` and per-activity `comparison.json`.

Private authentication state (`ui-test/_sessions/`) is excluded. Database and
encryption credentials, session cookies and embedded session-token values are
redacted from published text artifacts. Screenshots and seed/demo business data
are retained. Original private runs remain under ignored `.runs/`.

Repeated activity captures have identical contents. Git stores identical blobs
once; do not interpret the number of screenshot paths as independent executions.
