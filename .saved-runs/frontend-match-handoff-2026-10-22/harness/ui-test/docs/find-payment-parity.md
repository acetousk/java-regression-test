# Find Payment: separate Saved Finds dialog

Random mapped walkthrough route: `marble/Accounting/Payment/FindPayment`.
Only `apps` and `qapps`; read-only navigation and dialog opening, no business or
saved-find submissions.

## Evidence

Before: `.runs/2026-10-17_04-39-05.800988Z/`.
After: `.runs/2026-10-17_04-47-17.810770Z/`.
Screenshots/reports: `ui-test/find-payment/` in each run.
Both Java and Rust captures have no browser/resource/section errors in these runs.
The Java raw-template failure from the previous investigation did not recur;
its cause is not established and it should not be called fixed.

| Capture | Before differing pixels | After differing pixels |
| --- | ---: | ---: |
| apps | 3.7641% | 3.7641% |
| qapps | 1.4619% | 1.4842% |
| qapps Saved Finds open | Missing Rust trigger | 1.4540% |
| qapps Find Options open | Not measured | 7.9190% |

These are full-page original-pixel comparisons, not masked/cropped metrics.
Restoring the button does not establish visual parity or reduce the total pixel
rate while unrelated layout differences remain. In particular, Rust still lacks
the active-filter summary; navbar/footer, spacing, sort indicators and extra XLS
control also differ. The open Find Options dialog has substantial differences.

## Runtime change

PR: https://github.com/moqui/mr-moqui/pull/28

Java's `DefaultScreenMacros.qvt.ftl` places separate `_hdialog` (Find Options)
and `_sfdialog` (Saved Finds) dialogs in the form-list navigation. Rust combined
them under Find Options. Split the existing saved-find body into its own dialog,
with Java's ID suffix, title, icon and ordering (after Columns, before CSV).
Apply the same split to both merged and server-static QVT macros. Keep the
existing find/save/update/default/delete logic; this is not a complete port of
Java's saved-find interface, dropdown, scheduling or persistence semantics.

Five new Node runtime-renderer tests cover dialog separation, saved finds without
a header dialog, disabled/unauthorized/hidden navigation, existing saved-find
actions, and server-static output. Three merged-renderer assertions failed before
the patch; the static separation assertion also failed before its matching fix.
The targeted renderer/client Node suite passes 40 tests; harness tests pass 7.
The exact PR worktree's five new tests also pass. Rust build/test suite not run.

## Capture correctness

Intermediate after runs `04-44-47.873424Z` and `04-46-08.463670Z` have invalid
Saved Finds screenshots taken during its entrance transition: DOM text showed
the dialog but the image did not. Do not use their dialog pixel percentages.
The harness now requires an actual visible dialog role (not the component's
always-visible trigger wrapper), waits for Vue's animation frames, then awaits
animation completion events before capture. No sleep or timed polling was added.
The final screenshots were visually inspected and show both dialogs open.

## Limitations

Both engines used fresh isolated databases and verified graceful shutdown with
container cleanup. Rust used the existing prebuilt executable, with the edited
worktree runtime and explicit HTML/QVT macro overrides. The live probe validates
the merged QVT runtime patch, not a rebuild of current engine sources. Static QVT
is covered by the Node renderer test, not live-browser execution. Private
`probe-provenance.json` records artifact hashes/checkouts. Private configs,
HTML, cookies and logs must not be published. The harness deliberately fails the
parity gate despite collecting diagnostic evidence successfully.
