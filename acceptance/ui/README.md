# Exact UI acceptance (Phase 3)

1. Exact response, DOM and decoded RGBA comparison and browser capture.
2. Isolated boot-gated lifecycle runner, inventory and guard tests.
3. Evidence and usable-screen coverage reporting.

`run.py` inventories screens in the two current runtimes, copies runtimes into a
private run directory, starts fresh PostgreSQL containers and cached engines on
38080/38081, captures shared routable screens, and cleans up its own processes and
containers. It requires the phase-one boot gate and makes no builds. Run through
mise for the pinned Java toolchain.

Install dependencies here with `npm install` and `npx playwright install chromium`,
then run from the harness root:

```sh
mise exec -- python check_boot.py --evidence-dir .runs/boot-check
mise exec -- python acceptance/ui/run.py --boot-gate .runs/boot-check/gate.json
node --test acceptance/ui/compare.test.cjs
python -m unittest discover -s acceptance/ui -p 'test_*.py'
python acceptance/ui/summarize.py .runs/phase-three-ui/<run>
```

An existing compatible Playwright installation may instead be supplied through
`NODE_PATH`; it is only read. Evidence is in `.runs/phase-three-ui/<run>/` and
contains private response bodies, DOM, screenshots, runtime configs and logs.
Do not publish that directory. No application components are installed by this
runner. Current-only and Java-only screen inventories remain explicit.

This is an acceptance sweep, not a regression screen test. It performs GET
navigation and seeded login, not business transactions or fixture creation.
Detail parameters use the first sorted common value discovered in rendered links.
Screens lacking shared record parameters are recorded as uncovered; other screens may still fail or redirect; HTTP status, final URL
and capture errors must be reviewed before counting screen coverage. Email and
special-purpose screens need dedicated scenarios and are listed as uncovered.

Response body bytes (after browser transport decoding), live DOM serialization
UTF-8 bytes, and decoded PNG RGBA bytes are compared separately. PNG container
bytes are not used for pixel equality. There are no masks, tolerances, string
normalizations, approved differences, injected styles or frozen clocks. Session
tokens, timestamps, ports, fonts, asynchronous rendering and intentional design
changes can therefore cause raw mismatches. A matching error page is not screen
parity, and equal pixels do not establish equal HTML or DOM.

The runner exits nonzero for raw mismatch or incomplete coverage; this is expected
for intentionally evolved interfaces and must not be relabeled a parity pass.
`result.json` and text diffs summarize the independently retained raw artifacts.

The explicitly supplied boot gate must prove readiness and graceful shutdown, and
its cached artifact hashes must match. Validation remains active with `python -O`.
Capture errors, HTTP/client errors, missing required record parameters, unexpected
redirects, shutdown verification errors and forced kills all fail the run.
HTTP 200 responses containing rendering errors in the response or live DOM also
fail coverage. `result.json` reports usable pairs separately from raw comparisons,
and lists current-only screens without a Java counterpart. Source hashes in
`runner-provenance.json` identify the acceptance code used by new runs; engine
provenance includes working-diff and untracked-file hashes. Setup exceptions leave
an explicit failed `verdict.json` after cleanup.

For Qapps, fetched `.qvt` response bodies are also retained and compared byte for
byte, paired by path/query and request index; unmatched resources fail equality.
The initial document comparison remains separate from these screen fragments.
