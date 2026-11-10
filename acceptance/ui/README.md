# Exact UI acceptance (Phase 3)

1. Exact response, DOM and decoded RGBA comparison and browser capture.
2. Isolated boot-gated lifecycle runner, inventory and guard tests.
3. Evidence and usable-screen coverage reporting.
4. Updated engine revision pin.
5. Verified isolated document fixtures and shared service-definition selection.

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
navigation and seeded login after creating one `UiAcceptanceDocument` record through
each engine’s existing entity service in its disposable database. The two-request
session/CSRF flow and a database read verify fixture creation; evidence is retained.
Detail parameters use verified fixture IDs or the first sorted common value discovered
in rendered links. Service names come from actual shared XML service definitions,
never directory links. Screens that explicitly exclude HTML are reported as uncovered
for that mode; Qapps is still captured separately.
Screens lacking shared record parameters are recorded as uncovered; other screens may still fail or redirect; HTTP status, final URL
and capture errors must be reviewed before counting screen coverage. Email and
special-purpose screens need dedicated scenarios and are listed as uncovered.

Response body bytes (after browser transport decoding), live DOM serialization
UTF-8 bytes, and decoded PNG RGBA bytes are compared separately. PNG container
bytes are not used for pixel equality. Raw comparisons use no masks, tolerances, string normalizations or injected
styles. Operation mode supplies data time and reports reviewed presentation
differences separately, as described below. Session tokens, ports, fonts,
asynchronous rendering and intentional design changes can still cause raw mismatches. A matching error page is not screen
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

6. Reproducible 25-screen sampling and operation evidence.

```sh
NODE_PATH=/path/to/existing/node_modules mise exec -- python acceptance/ui/run.py \
  --boot-gate .runs/boot-check/gate.json \
  --selection acceptance/ui/sample25.json \
  --operation-plan acceptance/ui/operation_plan.json
node --test acceptance/ui/operations*.test.cjs
```

The frozen sample uses SHA-256(seed + NUL + screen key), taking the first 25
ranked keys from 44 distinct previously reachable shared screen definitions.
Default-navigation aliases were removed before freezing the selection; equality
was not an eligibility criterion. The manifest retains the seed, population,
excluded aliases and both rendering modes. This does not sample every installed
screen or establish coverage of previously unreachable screens.

The operation plan inventories controls, transitions, embedded dialogs and
list features. Executable cases use representative inputs. Arbitrary service
dispatch, data-dependent navigation and input domains are not exhaustively
covered by a finite plan. Explicit unresolved cases fail coverage. An input edit
is labeled as such; it does not count as submitting the form or persisting data.
Fixture SQL establishes disposable records and is never counted as exercising
application behavior. Fixture proofs must pass on both engines before dependent
cases run. No actual external printer or delivery provider is configured.

Each attempted operation retains decoded HTTP response bodies, DOM, decoded
RGBA, QVT and download evidence, plus full database snapshots before and after.
Interaction cases require explicit success postconditions. Missing evidence,
errors, missing controls, missing prerequisites and unexercised cases fail.
The complete expected-case list is recorded before execution, so interruption
cannot turn a partial run into a pass. Optional same-session reload diagnostics
are reported separately and cannot waive cross-engine differences.

Database snapshots compare the literal bytes of unfiltered plain `pg_dump`
exports, including every application schema, row, sequence and large object.
PostgreSQL system catalogs are outside the export scope. Each engine has a
consistent snapshot, but the pair has no synchronized transaction barrier;
background writes, row order and schema differences can cause mismatches.
Earlier exploratory runs used the controller snapshot format, which excludes
fixed harness tracking infrastructure; their provenance retains that distinction. HTTP evidence covers
browser-decoded document/XHR/fetch bodies, not raw wire frames or all headers.
No claim of exact operation parity is made unless every required comparison and
coverage check passes. Private evidence remains under `.runs/`.

Automatic scheduled jobs are disabled in both disposable operation runtimes with
`scheduled_job_check_time=0`. An earlier complete run demonstrated Java retention
cleanup deleting the historical fixtures mid-run. This prevents that unrelated
background mutation; it does not establish coverage of scheduled execution.
Manual service/job worker behavior is not disabled. The generated configuration
and `operation-environment.json` retain this choice explicitly.

7. Reviewed differences and supplied data time.

`approved-differences.json` at the repository root records the explicitly reviewed
schema, seed and presentation differences. Database comparison retains its raw
verdict and applies only named rules to a comparison copy. Newly reviewed seed
rows require exact non-generated values and absence on the other engine. Added
column rules remain restricted to nullable, default-free columns containing only
nulls; populated values are still reported. Shared `last_updated_stamp` values
are not exempted.

Operation runs now supply both engines with `MOQUI_TEST_DATA_CLOCK_FILE`. The
engines must include the corresponding opt-in clock implementation. Before UI
fixtures, real service create and update calls prove that each database's stored
stamp equals the supplied time at two successive instants. Failure stops the
run. This controls data timestamps, not elapsed deadlines, randomness, asynchronous
ordering, or transaction pairing. Consumers of user-now, including some security
expiry and cooldown rules, follow explicit effective time or supplied test time. Automatic schedules
remain disabled in these disposable runs. The clock proof's DataDocument entity
does not declare optimistic locking, so it does not prove stale-update rejection.

`approved_functional_plan.json` contains focused cases for the three reviewed
screen/mode combinations. Merge them into a plan containing the frozen sample's
25 keys to run through the existing lifecycle. Each applicable result includes
an `approvedPresentation` verdict alongside the unchanged raw verdict. A scoped
approval permits markup and pixels to differ only after functional observations
complete and agree. Content text assertions are exact; control-label checks
compare semantic words with presentation whitespace collapsed and retain raw
visible labels separately. Request targets, statuses, submitted values and
downloads remain strict. Database and coverage failures still fail the overall
result. Resource's separately approved implementation difference is recorded
without claiming function equivalence or successful coverage.
