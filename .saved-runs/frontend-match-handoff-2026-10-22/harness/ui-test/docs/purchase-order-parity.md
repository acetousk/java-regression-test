# Purchase Orders: header-only filter summary

Random mapped route: `marble/Order/FindOrder?orderType=Purchase`.
Only apps and qapps attempted; no business records submitted.

PR: https://github.com/moqui/mr-moqui/pull/32

## Runtime fix

Java's HTML macro considers all form fields for its active-filter summary.
Rust considered only visible table columns, omitting `Order Type: Purchase`.
Header-only fields are also excluded from column-selection metadata by design.

Generate separate summary descriptors for all fields, reuse existing summary
callbacks/context/escaping, and skip explicitly hidden fields. Leave column
selection and table layout unchanged. The final browser capture includes
`Order Type: Purchase`, as Java does. Declaration order is also restored.

## Evidence

Before: `.runs/2026-10-17_05-23-23.551241Z/`.
Final: `.runs/2026-10-17_05-29-01.018522Z/`.
Screenshots/reports: `ui-test/screen-probe/` under each run.

Apps differing pixels: before 4.5485%, after 4.5658%. This narrow functional fix
does not improve the aggregate pixel score or establish visual parity.
Date-period descriptions, navbar/footer, CSS, spacing and other differences remain.

Initial qapps screenshots captured stale dashboard content while navigation had
already updated the URL. Their metrics are invalid destination comparisons.
Qapps needs a navigation-completion/capture investigation before further claims.
Vapps was not tested or changed.

Both engines passed graceful-shutdown verification in the before and final runs;
disposable databases were cleaned up. Intermediate runs `05-26-25.978809Z` and
`05-27-32.244242Z` tested incomplete patches and lacked Java post-SIGTERM shutdown
markers. They are not final validation.

Rust browser execution used a prebuilt executable with worktree runtime macro
overrides, not a rebuilt engine. Private provenance records identities/hashes;
private configs, HTML, cookies and logs must not be published.

## Tests

Exact PR worktree: `node --test runtime/base-component/framework/template/screen/*.test.js`:
13 passed. New tests cover generated header-only descriptors, off-column filters,
ordering, escaping, duplicate prevention, hidden/empty/non-filter fields and
inline/skipped headers. The original visible-column implementation fails the
new off-column summary assertion.

Full parity remains failing. Await review of PR #32 before the next fix.
