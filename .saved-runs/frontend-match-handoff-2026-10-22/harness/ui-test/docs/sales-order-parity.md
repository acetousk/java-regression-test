# Create Sales Order: parity investigation

Scope: `walkthroughs/place-and-approve-sales-order.md`, activity-008.
Playwright navigated Login → authenticated landing → mode dashboard →
`marble/Order/FindOrder` → Create Sales Order dialog. No order was submitted.
Screenshots are recorded for each reached step, with login captures reused across modes.

## Evidence

Latest run: `.runs/2026-10-17_04-21-15.254700Z/`.
Start with `ui-test/sales-order-probe/summary.json`; step screenshot references are
in each engine's `captures[].steps`. Images retain original pixels, without masks.

Java's browser assets were built with Gradle 8.9 (the local moqui-fop build file
is incompatible with Gradle 9), and the Java WAR was rebuilt. This resolved the
previous Java baseline's missing assets/literal template output. Rust used the
existing binary from checkout b7823494, **not** the worktree's engine sources.
A private config loads the edited HTML macro module from the worktree instead of
the binary's embedded module. This validates the renderer patch through a real
browser, not a rebuilt engine. Full binary paths/checksums are in
`probe-provenance.json`. Do not publish the private configs, cookies or HTML.

| Mode | Java | Rust | Full-page differing pixels |
| --- | --- | --- | --- |
| apps | Dialog opened | Dialog opened, but navbar section rendering failed | 34.96% diagnostic only |
| vapps | Dialog opened | 404: screen absent | No valid screen comparison |
| qapps | Dialog opened | Dialog opened | 6.73% |

The apps probe originally classified server-side error text as captured; the
runner now detects `Error rendering section [` and marks it blocked. That run's
apps metrics must not be treated as a valid screen comparison. The mixed binary /
runtime is another reason not to claim engine parity.

Qapps differences visible in the screenshots: taller dropdown spacing/dialog,
different date input widths, missing active-filter summary and Saved Finds,
additional XLS control, different navbar layout and footer. Apps uses a different
HTML/CSS/widget implementation (semantic dialogs/Tom Select versus Bootstrap /
Select2), not merely a few changed pixels. Vapps has no corresponding Rust root
screen/template; substituting qapps would conceal, not fix, the missing mode.

The overall run failed: incomplete coverage and Java shutdown evidence missing
(post-SIGTERM artifact-bin/factory-destroy markers). Rust shut down cleanly;
both disposable database containers were removed. This is not a workflow pass.

## Narrow fixes

- MrSimpleScreens: `!orderType?.toLowerCase() === 'sales'` negates the string
  before comparison, so the role filter is never ignored. Change both sales /
  purchase tests to `!==`, preserving Java's case-insensitive filtering.
  Actual XML expression tests: 14 failures before, 20 passes after.
- mr-moqui HTML macro: Font Awesome's decorative glyph enters the accessible name
  (`\uf064 Create Sales Order`), defeating exact role/name lookup. Set the shared
  dialog trigger's escaped `aria-label` to its visible label. Two renderer tests
  pass. In the live probe, Rust's exact named trigger is found after the fix.
  Java's existing button has the same icon issue; its documented trigger ID is
  used for navigation without modifying the Java oracle.

These fixes do **not** establish visual or runtime-source parity.

## Byte-level source audit

Tracked files only, comparing raw bytes without whitespace normalization.
Generated/minified downloads and test outputs not tracked by Git are excluded.
Full changed/missing path inventories: `.runs/runtime-byte-audit.json`.

| Java runtime path → Rust counterpart | Identical | Changed | Java only | Rust only |
| --- | ---: | ---: | ---: | ---: |
| base-component/webroot → same | 11 | 23 | 43 | 61 |
| base-component/tools → same | 48 | 66 | 20 | 2 |
| component/SimpleScreens → component/MrSimpleScreens | 172 | 281 | 9 | 57 |
| component/MarbleERP → component/MrMarbleERP | 5 | 5 | 1 | 5 |
| conf → same | 3 | 1 | 0 | 0 |

Counts include tracked docs/tests/metadata. Some source differences are necessary
Groovy → JavaScript / FreeMarker → Fancy conversions; others change presentation
or remove features. The runtime directories are **not almost byte-identical**.
Restoring those features/layouts requires broader work than the two narrow fixes;
blindly copying Java templates would not be executable on the Rust engine.
