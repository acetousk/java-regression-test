# Business-process visual evidence

Specs cover the inventory of all 42 documents in `docs/business-processes/`:
744 visual-test placeholders, each evaluated for `apps`, `vapps` and `qapps`.
`generate-process-specs.js` generates one spec per document; `process-plan.js`
reads the source text and line numbers at execution time.

**This is a best-effort, read-only evidence sweep, not 744 implemented workflows.**
It visits candidate/documented screens and opens recognized named dialogs when
possible. It does not create prerequisite business records, fill/submit business
forms, execute external integrations or perform manual activities. Each activity
is reported as `partial` or `blocked`, never a completed story. Unmapped activities
receive an explicit report, not a fabricated Marble workflow. Story entry-screen
candidates are listed in `process-plan.js` and distinguished from documented URLs
and recognized dialog labels in the reports.

```sh
cd ui-test
npm ci
npx playwright install chromium
npm run generate:processes
cd ..
mise exec -- python java-regression-test.py --skip-step-4
```

`--skip-step-4` loads all demo data in fresh isolated databases (the existing
startup default), collects evidence while both servers are alive, then shuts
them down and cleans up, including after visual failures. It skips database
snapshots/comparison, not browser diagnostics. It cannot be combined with
`--deterministic`. Without this flag the existing database regression workflow
is unchanged. Both runtimes need application dependencies, including Java's
`moqui-fop`. `--visual-spec` limits execution; the default runs all specs.

For already-running **isolated test servers** (no data loading/reset):

```sh
cd ui-test
JAVA_BASE_URL=http://127.0.0.1:8080 RUST_BASE_URL=http://127.0.0.1:8081 npm run test:processes
```

Authentication uses the seeded `john.doe` / `moqui` login form. Override with
`VISUAL_USERNAME` / `VISUAL_PASSWORD`. No business mutations are submitted;
normal login, statistics and scheduler writes may still happen. Optionally set
`CHROMIUM_PATH=/usr/bin/chromium` to use system Chromium.

## Compare one screen (no script edits)

Fresh disposable databases and automatic available HTTP ports, using existing
build artifacts and this checkout's Rust runtime HTML/QVT macros:

```sh
CHROMIUM_PATH=/usr/bin/chromium mise exec -- python ui-test/compare-screen.py \
  --route 'marble/Shipment/FindShipment?shipmentTypeEnumId=ShpTpTransfer'
```

If the Rust executable is elsewhere, supply `--rust-binary /absolute/path/to/moqui`.
Use `--random` instead of `--route` to select from unique mapped walkthrough
routes; the selection pool is recorded. Defaults to `apps,qapps` (no `vapps`).
Optional `--modes qapps`, `--dialog-id ShipmentList_hdialog --dialog-label 'Find Options'`,
`--java-port`, `--rust-port`, `--java-checkout` and `--rust-checkout` select the
probe without changing files. Use explicit routes with dialog options. To
compare another state, invoke again; every invocation gets a fresh run directory.

For already-running **isolated test servers**, with the same environment variables
as above and a new absolute evidence directory:

```sh
CHROMIUM_PATH=/usr/bin/chromium node ui-test/compare-screen.js \
  --route 'marble/Accounting/Payment/FindPayment' --modes qapps \
  --run-dir /absolute/path/to/new-run
```

Evidence goes to `.runs/<run-id>/ui-test/screen-probe/` under the startup wrapper
(or the supplied directory). Differences/blocked captures exit nonzero after
collecting both engines/modes; startup cleanup still runs. This is a read-only
screen comparison, not workflow completion. Artifacts are not rebuilt: provenance
records executable hashes, checkout revisions and dirty-file inventories, without
claiming current-engine-source parity. Keep private configs, cookies, HTML and
logs private. The wrapper overrides configuration only in its private run config.

## Evidence layout

```text
.runs/<run-id>/
  ui-test/
    summary.json
    process-library/             # walkthroughs/ uses the same layout
      <process-story>/
        apps.summary.json
        vapps.summary.json
        qapps.summary.json
        activity-001/
          apps/
            screen.java.visual.png
            screen.rust.visual.png
            screen.diff.visual.png
            screen.java.html
            screen.rust.html
            screen.java.txt
            screen.rust.txt
            comparison.json
          vapps/                 # same artifacts when obtainable
          qapps/
    _steps/                      # deduplicated screenshots of each navigation step
    _captures/                   # shared immutable captures and diagnostics
    _sessions/                   # private authentication cookies; never commit
    test-results/                # Playwright diagnostics
```

Each activity report includes source text, headings, source line, mapping type,
limitations, requested/final URLs, navigation method, HTTP failures, JS errors,
login status and dialog-open result. Both engines are attempted independently.
Error-page screenshots are retained but labeled `diagnostic-only`; missing routes
and prerequisites are failures, not equivalent screens. Identical route/dialog
probes reuse the same capture **within one run**, explicitly marked `reused`.
Each capture's `steps` list references screenshots for login, the authenticated
landing page, dashboard, destination screen, and the open dialog when applicable.
Step screenshots are deduplicated within the run by server, engine/mode (for
application screens), route, dialog and actual URL; references mark `reused`.
Reusing a step screenshot does not skip navigation needed to reach later steps.
Hard links avoid duplicating image/HTML storage for repeated activities. Reused
entry screens are not independent executions of a story.

The original first-screen spec remains `open-marble-login.visual.spec.js`. Its
artifacts use `process-library/open-marble-login/<mode>/` without an activity
subdirectory. Anonymous mode entry may redirect to the shared Login screen;
those comparisons do not test authenticated mode-specific shells.

The controller passes its run directory through `MOQUI_RUN_DIR`. Standalone tests
create a timestamped directory; an absolute `MOQUI_RUN_DIR` selects one explicitly.
All generated output stays in `.runs/`, never beside specs. Each mode compares
Java against Rust, never against another mode.

Captures use the same browser, viewport, locale and timezone. Original screenshots
are retained without masking/resizing. Pixelmatch uses a 0.1 color threshold and
default antialias handling. Reports contain dimensions, pixel counts and difference
percentages. The final gate deliberately fails for blocked/partial workflows or
visual mismatches, **after collecting the remaining activities**.
