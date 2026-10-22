# Frontend-match restart handoff — 2026-10-22

This package preserves the visual-regression thread well enough to resume on a new Linux install without the old checkout, caches, or conversation. It is a recovery snapshot, not a claim that invoice parity or database comparison passes. Publication repository: `acetousk/java-regression-test`, branch `docs/frontend-match-handoff-2026-10-22`, directory `.saved-runs/frontend-match-handoff-2026-10-22/`.

## What the user wants

Compare Java and Rust screen behavior and visual fidelity in **apps and qapps**, using `moqui-framework/runtime` implementation and CSS as the reference. Stay on the current screen until closely matching. Make small source-supported fixes, validate them, and submit focused stacked PRs. **No vapps yet. Run Step 4.** Preserve unrelated work, report unresolved blockers, and put before/after screenshots in PR descriptions only; never commit screenshot images.

Later instructions override older ones: running Step 4 overrides the earlier skip instruction; continuing focused stacked PRs until parity overrides the original one-PR-then-stop instruction. Do not interpret an old note as permission to stop after one PR or skip final DB comparison.

The logical/activity regression is a separate thread and checkout (`match-screen-logic`), historically using ports **28080/28081**. Do not interfere with its processes, ports, worktree, build targets, or DBs. This thread uses `frontend-match` and an isolated Rust worktree.

User preferred primary-agent reasoning and review with bounded **Luna** implementation/execution tasks. Parent must independently inspect and validate delegated work. If resuming delegation, discover current provider/model IDs; historical IDs are not portable. Each review round needs a new delegated task. Use at most one one-minute active-task monitor and remove it when no tasks are active. At handoff, the last Luna task was completed and the scheduler had no tasks. No implementation task or monitor needs to be resumed.

User also requested output in `moquilabnotes www/AI Provider Value.md`; the actual old-machine file is `/home/user/LabNotes/www/AI Provider Value.md`.

## Exact stopping point

Current screen in both modes:

```text
marble/Accounting/Invoice/EditInvoice?invoiceId=UI_PARITY_INVOICE
/apps/marble/Accounting/Invoice/EditInvoice?invoiceId=UI_PARITY_INVOICE
/qapps/marble/Accounting/Invoice/EditInvoice?invoiceId=UI_PARITY_INVOICE
```

The latest form-metrics implementation is **committed and pushed**, but its PR creation was interrupted. It has no PR as verified on 2026-10-22. No code fix is needed before preparing that fourth PR; first recheck GitHub to avoid a duplicate.

| Layer | PR / branch | Commit | Base | State at handoff |
|---|---|---|---|---|
| Qapps labelled display | [#47](https://github.com/moqui/mr-moqui/pull/47), `fix/invoice-visual-parity` | `44a78fca427f0141106b36e05aaa3cad2778d180` | `master` | Open, linked to T3 |
| Qapps form margins | [#48](https://github.com/moqui/mr-moqui/pull/48), `fix/qvt-invoice-form-spacing` | `d2491b24e6a894610b05ad7f4a5ce281b3e6c64a` | `fix/invoice-visual-parity` | Open, linked to T3 |
| Apps status CSS | [#49](https://github.com/moqui/mr-moqui/pull/49), `fix/html-invoice-status-layout` | `30aa9133b4517466819c0f968421e9831f73b837` | `fix/qvt-invoice-form-spacing` | Open, linked to T3 |
| Apps form metrics | `fix/html-invoice-form-metrics` | `8c8f2c86d8fbb7d5b64296ddb9ccc5a99aa2a99c` | `fix/html-invoice-status-layout` | Pushed; **PR not created** |

The isolated Rust checkout `.runs/pr-invoice-current` is clean at the fourth commit. The stack began from then-current master `2269100`, deliberately avoiding unrelated original Rust edits. Requery PR states before continuing; these states are observations, not permanent assumptions.

Layer details and review decisions:

1. **#47:** Java-style outlined, read-only, autogrowing `m-display` for labelled qapps values; preserve inline text. Zero/multiline cases tested; Quasar `:for` supplies native input ID. Component, generated renderer, browser test only. Delegated 22 tests passed; parent focused browser and strict generated-render checks passed.
2. **#48:** Normal fields change `q-pa-xs` to `q-ma-sm`; form wrapper changes `q-mb-md` to `q-my-md`, in merged and static renderers. Parent rejected a fixture alteration that removed a dialog form scope and restored it. Parent passed 21 merged-render tests and static fixture compilation; delegated two generated goldens and 12 Node tests passed.
3. **#49:** Restore Java `float-plain` / `shaded-area` CSS so the invoice status widget is horizontal and shaded. Parent corrected shadow geometry to Java's one-pixel spread and fixed browser fixture nesting. CSS and geometry test only; parent test passed.
4. **Pushed fourth layer:** Java Bootstrap metrics: controls 34px high with 6px/12px padding; field bottom margin 15px; label top padding 7px; static values and links 34px high with 7px vertical padding. Preserve compact list controls and big-row child margin overrides. Only `moqui-html.css` and `moqui-html.test.js`, 49 insertions / 6 deletions. Parent independently passed the Chromium geometry test plus eight JS tests (nine total), inspected the diff, and validated the completed capture. `git diff --check` passed.

Fourth PR body is saved in [`support/invoice-form-metrics-pr.md`](support/invoice-form-metrics-pr.md). It contains externally hosted before/after screenshot URLs. Image files are not in this package. When resuming the original development task:

```bash
gh pr list --repo moqui/mr-moqui --state all --head fix/html-invoice-form-metrics
# Only if no existing PR:
gh pr create --repo moqui/mr-moqui \
  --base fix/html-invoice-status-layout \
  --head fix/html-invoice-form-metrics \
  --title 'fix(html): match Java form metrics' \
  --body-file .saved-runs/frontend-match-handoff-2026-10-22/support/invoice-form-metrics-pr.md
```

If using T3, immediately register every PR created or worked on with `link_pull_request(full URL)` and reconcile `list_thread_pull_requests` before finishing. Merely using `gh` does not register a PR. Do not create a fourth PR as part of simply reading this summary.

## Latest evidence and its limits

Every percentage is differing full-page pixels, not a workflow pass rate. Lower percentage is useful evidence but is not the sole acceptance criterion: source-supported semantics/layout can improve while whole-screen counts rise. No numeric acceptance threshold for complete parity was agreed.

| Local evidence run under `.runs/` | Context | Apps % | Qapps % | Shutdown verified | Final DB equal |
|---|---|---:|---:|---|---|
| `2026-10-19_23-43-05.295892Z` | Old patched worktree; different base | 20.0379 | 3.7938 | true | false |
| `2026-10-20_00-00-03.661898Z` | Current-master baseline | 20.0381 | 12.4843 | true | false |
| `2026-10-20_00-07-00.585196Z` | #47 after | 20.0381 | 12.5370 | false: Java markers missing | null / blocked |
| `2026-10-20_01-28-56.825836Z` | #48 after | 20.0381 | 13.4415 | true | false |
| `2026-10-20_01-51-08.055105Z` | #49 after; fourth-layer before | 19.5448 | 13.4415 | true | false |
| `2026-10-20_01-55-59.979813Z` | Fourth-layer after, parent validated | **7.6713** | **13.4415** | **true** | **false** |

Latest exact verification:

```json
{
  "deterministic_requested": false,
  "servers_started": true,
  "shutdown_verified": true,
  "final_databases_equal": false,
  "passed": false,
  "approved_differences_sha256": "eae7e91a595e85f17ce618714ac216b915323469353c35caebbbdf5edd380d1e"
}
```

All four latest Java/Rust apps/qapps captures authenticated, returned HTTP 200, and had empty screen-error, failed-request, HTTP-error, and console-error lists. Apps Java image was 1440×1091, Rust 1440×1085: 120519 differing / 1571040 compared pixels. Qapps Java was 1440×1000, Rust 1440×1034: 200139 / 1488960 pixels. Screenshot dimensions still differ. Latest shutdown had Java exit 143, Rust 0, neither forced, no shutdown errors or missing markers.

**Step 4 really ran and failed** in the latest run. The wrapper initially logs that it is skipped during the visual phase, then enables final comparison before shutdown. Read `verification.json`, `shutdown.json`, and comparison outputs, not the initial skip message. The #47 after-run is the exception: missing Java shutdown markers blocked comparison. No approvals were changed to manufacture a pass.

Invoice runs used final DB snapshots, not deterministic per-transaction / CDC verification. Broader DB differences remain in schema, Rust-only relations, seeded rows, timestamps, and statistics; these have not been solved or conclusively attributed to the invoice fixture. Do not conflate this with the separately running logical regression.

Latest provenance records pre-existing Java/Rust binaries, not a rebuild for each CSS iteration. Runtime macro overrides load worktree `ScreenHtml.js` and `ScreenQvt.js`. This supports the specific visual comparison, not an engine-source equivalence claim. Rust artifact SHA256: `40b2a6f072f367cc57d06e8af7a183199fe0649c17190825958c3c73d323754a`; Java war: `ce3c8094a97d63f0b8c1070fdb21fd0f5d6f8921c2f9dc1feff79b34b54f0d56`. A fresh install rebuilds once; artifact hashes may then differ.

Compact original JSON reports are in [`evidence/`](evidence/). Old absolute paths inside them describe the old machine; their screenshot targets are intentionally not included. Later repeated captures existed but are unnecessary; the validated `01-55-59` run is the reference here.

## Data that must survive migration

| Included location | Purpose |
|---|---|
| `harness/` | Snapshot of original controller/docs/tests plus current uncommitted `ui-test` files; a normal clone would miss those files |
| `support/compare-invoice.py` | Exact invoice fixture + final-Step-4 wrapper; required to reproduce the populated probe |
| `support/invoice-form-metrics-pr.md` | Ready fourth PR description, including screenshot URLs |
| `preserved-original/harness-tracked.patch` | Record of original tracked harness diff |
| `preserved-original/mr-moqui.patch` | Unrelated original Rust working diff, including component gitlink change |
| `preserved-original/mr-moqui-untracked/` | Original three untracked frontend test files |
| `preserved-original/invoice-masker.patch` | Older interrupted masker helper/test work; preservation only |
| `manifest.json` | Full Git pins, URLs, original statuses, toolchains, source inventory |
| `support/restore-checkouts.py` | Fresh-install repository reconstruction helper, using the manifest |
| `evidence/` | Compact capture reports, artifact provenance, shutdown and final verification JSON |
| `SHA256SUMS` | Integrity list for all packaged files except itself |

No old database volume is required for this probe. Fresh demo DBs originally contained no invoices, so the wrapper inserts one identical minimal invoice into two newly created disposable PostgreSQL DBs. That is a rendering fixture only: no invoice items, payments, business form submissions, or complete workflow coverage. Browser authentication/statistics/scheduler activity still writes data.

Do not copy build targets, node_modules, container volumes, browser cookie/storage files, raw private configs, DB snapshots/dumps, screenshot files, or raw `.git` files from old worktrees. The package does not contain them. Screenshots remain accessible through PR descriptions while their external image hosting survives; take new captures if unavailable.

## Recreate on a fresh Linux install

Prerequisites: Git; mise; Java/Python/Rust versions from `mise.toml`; Node/npm (observed 26.12.0 / 12.2.1); a working Docker-compatible CLI (old machine used Podman compatibility); Chromium; native compiler/linker/clang/cmake/pkg-config; normal Java and Cargo build prerequisites. GitHub authentication is needed for pushes/PR creation, not for public clones. Package manager setup is distribution-specific.

```bash
git clone --branch docs/frontend-match-handoff-2026-10-22 \
  https://github.com/acetousk/java-regression-test.git frontend-match
cd frontend-match
HANDOFF="$PWD/.saved-runs/frontend-match-handoff-2026-10-22"
(cd "$HANDOFF" && sha256sum -c SHA256SUMS)

# Restore the exact controller/UI harness snapshot, including uncommitted files.
# This intentionally overlays the newly cloned root source, preserving the package.
cp -a "$HANDOFF/harness/." .
mkdir -p .runs
cp "$HANDOFF/support/compare-invoice.py" .runs/compare-invoice.py
mise trust
mise install
mise exec -- python "$HANDOFF/support/restore-checkouts.py" "$PWD"

cd ui-test
npm ci
# Either install Chromium at /usr/bin/chromium and use CHROMIUM_PATH,
# or install Playwright's browser and set CHROMIUM_PATH to that executable.
npx playwright install chromium
cd ..
```

The helper clones pinned Java framework/runtime/components and the original clean Rust base, then creates the clean active Rust worktree at the fourth stack commit. It refuses existing dirty repositories or mismatched nonempty directories. It does **not** apply preserved original edits. `.runs/pr-invoice-current` has no tracked component submodules at this upstream revision, so its four component repositories must be cloned separately; the helper does so. Old copied component `.git` files contained absolute worktree pointers and are not portable.

The manifest is authoritative for full hashes. Effective pins:

| Path | Revision |
|---|---|
| Original harness HEAD (`screens`) | `c7640eb5e438a0b301dec7cedf1d78aa29d75428` |
| Publication base, remote `screens` | `73680d7be2d845972ed5f509a714f90952b6bfd5` |
| `moqui-framework` | `23eb356556d3bc025f49bacfb8e2201851c236a0` |
| Java `runtime` | `47ceed9c001c3c7598c3e178b9eafa6397001eb2` |
| Java `MarbleERP` | `fedf3f42f26c6e23a996354baf717aad4732a66e` |
| Java `SimpleScreens` | `5aed7ffba7231babdccfb0bd46cb6db66195487c` |
| Java `mantle-udm` | `f53aba96a14fc97c6b42918300ee880fa0eb03a1` |
| Java `mantle-usl` | `3fa07c672809910b1fe59caa050e5e4a8c20ea63` |
| Java `moqui-fop` (additional component) | `1684dad02bb4b97cb4d7dbce5271937e7b28273e` |
| Original Rust `mr-moqui` | `38196ec6071b1a0c77e2de2be4c60a6c2e129fb2` |
| Active Rust `.runs/pr-invoice-current` | `8c8f2c86d8fbb7d5b64296ddb9ccc5a99aa2a99c` |
| Active Rust `MrMarbleERP` | `89b263cadf80fcf97e24b6ac6b883b8491168d7b` |
| Active Rust `MrSimpleScreens` | `2a36dc166ea3fe848770617c19f10819ef223301` |
| Active Rust `mantle-udm` | `50be8e3acba2b844f31286aa60a7e9d8da9a2a79` |
| Active Rust `mantle-usl` | `14d327b1f00e345fc2c16e189684171dfb748152` |

Before Rust builds, read `mr-moqui/AGENTS.md` and `.agents/skills/building/SKILL.md` in the active checkout. Use a consistent compiler, incremental development builds, and a dedicated target directory. Avoid cache cleaning or rebuilding both engines on every CSS/runtime-template change.

Build once on a new install:

```bash
(cd moqui-framework && mise exec -- ./gradlew --no-daemon build)
(cd .runs/pr-invoice-current && \
  CARGO_TARGET_DIR="$HOME/.cache/mr-moqui-invoice-current-target" \
  mise exec -- cargo build --locked -p moqui --no-default-features --features enterprise)
```

The explicit enterprise build supports the external PostgreSQL test setup. Do not substitute the default maximal build without reading its embedded-Postgres payload prerequisites. The old successful command used exactly the enterprise flags above. Generic `mise run build` invokes the whole controller and its default build workflow; it is not the command used for repeated screen probes.

The controller provisions two empty ephemeral PostgreSQL containers, seeds/boots the engines, captures the requested route, stops servers, and compares final DB snapshots when enabled. The pinned image is `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`; Java JDBC driver 42.7.7 is downloaded by the controller if absent. Network access is needed for dependencies/container image on first setup.

Run the populated screen probe from the repository root (adjust Chromium path to your install):

```bash
CHROMIUM_PATH=/usr/bin/chromium mise exec -- python .runs/compare-invoice.py \
  --route 'marble/Accounting/Invoice/EditInvoice?invoiceId=UI_PARITY_INVOICE' \
  --modes apps,qapps \
  --rust-checkout "$PWD/.runs/pr-invoice-current" \
  --rust-binary "$HOME/.cache/mr-moqui-invoice-current-target/debug/moqui" \
  > .runs/invoice-resume.log 2>&1
```

Use a fresh log name for each run. A nonzero exit is expected while visual/DB differences remain; inspect the new evidence directory and verification JSON. Automatic free-port selection avoids hardcoded logical-thread ports. Do not run duplicate captures concurrently.

**Important wrapper behavior:** plain `ui-test/compare-screen.py` forces `skip_step_4=True` and disables deterministic mode. The saved invoice wrapper imports that probe, injects identical SQL through `docker exec ... psql -v ON_ERROR_STOP=1` into both fresh DBs, and sets `skip_step_4=False` after visual tests, including when the visual probe reports a mismatch. Keep `.runs/compare-invoice.py` exactly there because its root calculation uses `parent.parent`. Running the plain probe or Node comparison alone does not satisfy the Step 4 requirement.

Capture settings: seeded demo login `john.doe` / `moqui` (override `VISUAL_USERNAME` / `VISUAL_PASSWORD` for another disposable demo); viewport 1440×1000; device scale 1; locale en-US; timezone UTC; light theme; reduced motion. Full-page screenshots, no image masks/resizing; pixelmatch threshold 0.1. Dimension mismatch means unequal. Step captures deduplicate only within a run, not across runs. Standalone `compare-screen.js` needs already-running servers via `JAVA_BASE_URL` / `RUST_BASE_URL`; use a new absolute `--run-dir`. Dialog probes require both `--dialog-id` and `--dialog-label`.

## Focused checks when changing code again

Historical passing commands from the active Rust worktree:

```bash
CHROMIUM_PATH=/usr/bin/chromium node --test \
  runtime/base-component/webroot/screen/webroot/css/moqui-html.test.js \
  runtime/base-component/webroot/screen/webroot/js/moqui-html.test.js

CHROMIUM_PATH=/usr/bin/chromium node --test \
  runtime/base-component/webroot/screen/webroot/js/WebrootVue.qvt.display.test.js

CARGO_TARGET_DIR="$HOME/.cache/mr-moqui-invoice-current-target" mise exec -- \
  cargo test --locked -p moqui-core --lib client_components_are_precompiled
CARGO_TARGET_DIR="$HOME/.cache/mr-moqui-invoice-current-target" mise exec -- \
  cargo test --locked -p moqui-core --lib screen::tests::qvt::
CARGO_TARGET_DIR="$HOME/.cache/mr-moqui-invoice-current-target" mise exec -- \
  cargo test --locked -p moqui-core --lib screen::tests::statics::the_qvt_fixture_screens_become_templates_that_compile
```

Only regenerate generated/golden files when their source changed; inspect regeneration diffs, then rerun the strict check without `UPDATE_GOLDEN=1`. Root harness unit tests: `mise run test`; UI harness: `(cd ui-test && npm run test:unit)` and focused additional Node tests as relevant. Do not repeat all builds/captures simply because a new agent starts; existing validated results are recorded. A new install will need its first builds and smoke check.

## Preserve original edits without mixing them into the stack

The original root was branch `screens` at `c7640eb`, dirty in `ui-test/README.md`, `package.json`, `process-runner.js`, plus untracked capture/probe/wait scripts, tests, inspection script, and four screen parity notes. Those working contents are in `harness/`; original statuses are recorded in `manifest.json`.

The original Rust `mr-moqui` checkout was branch `screens` at `38196ec`, with unrelated edits to `entity/find.rs`, `ScreenHtml.js`, `ScreenQvt.js`, `ScreenQvtStatic.js`, navbar template, QVT CSS, HTML CSS, a `MrSimpleScreens` gitlink, and three untracked tests. Preserve them; **do not apply them to the new invoice stack**. If reconstruction is needed, use a separate disposable checkout at that base, `git apply --check` then `git apply` the saved patch, and copy `mr-moqui-untracked/`. A gitlink patch records a component SHA; it does not restore that component checkout automatically. Check out the SHA from the patch in the separately initialized component if needed.

Old `.runs/pr-invoice-screen`, branch `fix/invoice-screen-parity`, base `03f546018b0104d95c7fa13e3c9744c8876751ce`, retained a `StringUtilities.masker` helper/test patch in `ec_extra.rs`. An interrupted build initially failed on a raw-string delimiter; that was corrected, the build succeeded, and five helper tests passed. Current upstream already provides masker in `tools_host.rs`; **do not resubmit this duplicate implementation**. The patch is saved only to avoid losing old work.

## Prior work and outstanding blockers

Earlier work produced 42 business-process documents and 744 visual-test placeholders across stories/walkthroughs. The read-only evidence sweep was best effort, with partial/blocked cases; these are not 744 implemented end-to-end workflows. Local screen notes for sales order, purchase order, find payment and transfer shipment are in `harness/ui-test/docs/`.

Merged Rust visual fixes included PRs #26, #27, #28, #30–#34, #36–#41, and #43–#46: accessible dialog names, navbar themes, Saved Finds dialog separation, active summaries, theme variables, header-only summaries, period descriptions, empty titles, missing-filter distinctions, big-row width, block labels, sort-arrow/link spacing, header find filters, empty display lines, Java CSS defaults/buttons, list headers and footer columns. [#46](https://github.com/moqui/mr-moqui/pull/46) was confirmed merged. Do not redo or resubmit merged work.

Remaining blockers:

- Full EditInvoice visual parity is unmet: apps 7.6713%, qapps 13.4415%, differing page heights and remaining shared/header/panel styling differences.
- Java has an Assist control that Rust lacks. It affects the header offset. Do not insert fake cosmetic spacing, branding, or a pretend Assist implementation to conceal that functional gap.
- Final DB equality remains false; no approval changes were made. Source and seed sets differ, and the logical thread owns separate deeper regression work.
- Latest fixture proves populated rendering only, not invoice creation/items/payments or transaction semantics.
- Fourth stack branch is pushed but its PR remains to be created and linked after checking current GitHub state.

Next development sequence: check current PR/branch states; submit/link the validated fourth PR if still absent; review remaining differences against Java source; choose one bounded fix on the same EditInvoice screen; delegate only if following the user's Luna preference; independently validate focused tests/diff and one capture; run real Step 4; submit a focused next layer with honest evidence. Keep unrelated edits separate and do not move to vapps.

## Where the old context lives

Old workspace: `/home/user/.herdr/worktrees/java-regression-test/frontend-match`.

Original Pi history directory: `/home/user/.pi/agent/sessions/--home-user-.herdr-worktrees-java-regression-test-frontend-match--/`; latest original file `2026-10-17T19-18-46-115Z_01a14b4d-6663-763b-a98f-172134168238.jsonl`. Those transcripts are not required by this recovery package and were not published.

T3 thread: `mcp:3cb1ed71-3ddc-4a7e-9469-91ca5d109877`, title “Resume visual regression: frontend-match”. Read messages/activity using `t3_thread_read` with pagination if available. Historical last Luna task ID: `node:delegated-task:command%3Amcp%3A4b50d81d-719c-4436-b87d-d01fac64ab59%3Adelegate-task%3Ainvoice-html-form-metrics-layer-1`; confirmed completed. It is historical provenance, not a task to restart.

This summary/preservation task did not rerun engine builds or screen captures. It packages their existing evidence and validates the recovery files separately.
