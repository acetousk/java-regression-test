# Recovery package checks — 2026-10-22

- All 13 effective repository revisions matched the old-machine checkouts.
- All packaged Python files compiled without executing their workflows.
- The eight changed/new capture, comparison, wait and process-runner JavaScript files passed `node --check`.
- All packaged JSON parsed successfully.
- All three preserved patches passed `git apply --cached --check` against the corresponding original repository indexes, without modifying those indexes.
- The inventory contains text files only; no image files, database files, build artifacts, browser sessions, or Git metadata were included.
- The harness snapshot retains the working files byte for byte. Preserved source documents contain existing trailing spaces, and patch context lines also trigger generic whitespace checks. Those archival bytes were kept intentionally. New handoff documentation/helper files passed whitespace checks separately.
- `SHA256SUMS` covers the complete package except itself.

The restore helper was syntax checked and inspected; a complete fresh-install build/capture was not executed during this summary task. Historical engine/test/capture results are documented separately in the README and evidence JSON. They are not new test runs.
