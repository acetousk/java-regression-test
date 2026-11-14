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

Change 10 validates both current artifact hashes against the successful boot gate
before inventory, runtime copies, database creation or engine startup. Inventory-only
mode remains available without built artifacts or a gate. Per-launch hash checks
remain additional safeguards.

11. Explicit engine routes.

A private operation plan can provide `engineRoutes` for each screen, keyed by
engine and rendering mode. The frozen selection remains unchanged. The runner
records the resolved operation and actual request paths. It rejects external
routes and rendering-mode changes. `engineSelectors` can identify equivalent
controls without changing expected values. A route mapping does not approve any
response, text, state, or coverage difference.

Inventory parsing ignores XML comments while preserving CDATA. Raw source hashes
remain in evidence. Malformed elements still fail parsing.

12. Isolated authentication and extra fixtures.

An operation can select an anonymous browser session, or explicit test credentials
with an exact expected login path. These sessions close after the case and never
replace the administrator session. An expected final login page must be explicit.
Plans can include additional scalar `fixtureGroups`. These use the existing
owned-database checks, quoted identifiers, atomic inserts, and row verification.
They cannot replace built-in fixture groups. Fixture setup is not UI coverage.

13. Separate reviewed database comparison.

`--differences PATH` selects an optional rules file. The runner retains its exact
bytes, source path, and SHA-256 digest. The default remains the repository rules.
Each operation retains raw, unfiltered `pg_dump` bytes. A separate structured
comparison uses the same exported row snapshot for each engine. The exporting
transaction stays open until both captures finish. Sequence state must agree
between captures because sequence counters are not transactional. The structured
verdict remains incomplete when large objects exist.

The structured comparison excludes only harness observation infrastructure before
applying the recorded rules. It is not raw dump byte equality. A presentation
rule must explicitly request `database: "reviewedStructured"` to use this separate
verdict. Both before and after comparisons must pass with the same rules digest.
Raw verdicts remain unchanged. Neither capture establishes a transaction barrier
between the two engines.

14. Runtime source identity.

Before starting either engine, the copied runtime must match its checkout source
manifest. The runner retains this manifest and checks it again after cleanup.
Source changes during a run fail the verdict. Mutable directories are excluded
only at the runtime root; nested source assets with the same names remain intact.

Change 13 also stores structured evidence as gzip files at compression level 1.
The artifact manifest records original and compressed paths, sizes, and SHA-256
hashes. Compression must reproduce the original bytes before deleting that file.
`evidence_archive.load_json_artifact(directory, name)` verifies both hashes when
reading a saved JSON artifact. The comparator still writes its full report, but
skips the duplicate stdout copy. Raw SQL dumps remain uncompressed.

15. Observed transition coverage.

A case can declare `coveredTransitions` with transition names and optional HTTP
methods. Each declaration requires an actual successful response with retained
body bytes. A declaration alone does not establish execution. Explicit negative
control assertions can verify that an action is absent, but they do not count as
executing that action or covering its API endpoint.

Phase 3, Change 16 adds optional exact request-target pairs to a reviewed presentation rule.
Set `requestTargets` to objects with `java` and `rust` local paths, including their full query strings.
Each pair needs case-specific live evidence before approval.
Pairs apply only to captured request keys and functional click destinations.
No prefix matching, query removal, method change, or status change is allowed.
Other observation values and existing body checks remain strict.
Raw evidence stays unchanged. The separate verdict is marked `exception-adjusted`.
Keep private route pairs and their evidence in private plans and differences files.

Phase 3, Change 17 supports `--java-checkout` and `--rust-checkout` for disposable runtime profiles.
Every checkout needs a boot gate with its exact artifact hash and `runtime_source_sha256`.
This digest uses the source manifest from `runtime_identity.py`.
A matching binary alone cannot approve a profile with different runtime components.
Source inventory, copied-runtime checks, and engine provenance use the selected checkouts.
Default checkout paths remain unchanged.

Phase 3, Change 18 supports optional operation `fixtureControl` settings.
Provide a private `readyFile`, optional external `reset` state, and exact state `assertions`.
The ready file contains the owned fixture's loopback URL and capability token.
Only HTTP on `127.0.0.1` is accepted. Redirects are rejected.
Before each engine, the runner calls `/__fixture/reset`. Afterward, it calls `/__fixture/state`.
Each assertion uses a `path` array and an exact `value`.
The runner retains requests, responses, ready-file hashes, and assertion results without the token.
Any control or assertion error fails the case. Hook success does not prove operation parity.
No shell command or engine state mutation is available through this control interface.

Change 15 transition declarations require `name`, exact local `path`, and explicit `method`.
The path includes the full query string and resolves through the selected engine mapping.
A matching 2xx response must have captured body bytes.
A redirect also needs a captured 2xx terminal response linked by Playwright's same-origin redirect chain.
Unrelated paths, changed queries, changed methods, and redirects without completion never count.

Phase 3, Change 19 launches verified private copies of both executable artifacts.
Concurrent builds cannot replace the files used by the UI run.
Provenance retains original paths, launch paths, and their verified hashes.
Copy or hash failures stop the run before any engine starts.

Phase 3, Change 20 retains raw content bytes for observed operation requests.
Each request records its method, exact target, byte count, hash, body presence, and capture completeness.
Private request body files sit beside response body files.
The separate `requestBodies` verdict compares exact bytes and request identity.
Missing historical request bodies cannot pass this verdict.
Token differences and encoding differences remain raw differences.
Reviewed path pairs may map exact destinations, but cannot change request bytes.
No token-specific compatibility rule is enabled.
This evidence does not claim equality of network frames or headers.

Phase 3, Change 21 adds explicit `csrfProbe` steps for disposable records.
The probe first changes a field through the real submit button and verifies the persisted value.
It then submits the rendered form with an invalid token and another authenticated session's token.
Each refusal requires an explicit 401 or 403 status, expected message, and unchanged persisted value after reload.
Only exact request/response hashes from those successful refusal checks permit expected authentication errors.
Peer-session requests remain in the captured evidence.
This security proof does not normalize tokens or grant request-body compatibility.

Phase 3, Change 22 adds exact typed `search` terms to dynamic `choose` steps.
The driver uses the visible search input and waits for actual options.
It records the term, selected label, and submitted value as functional evidence.
Native options cannot claim server-search coverage.

Phase 3, Change 23 binds `submitValues` to an explicit local `path` and `method: "POST"`.
The request must match the page origin and complete path and query.
Raw observations retain the resolved target, method, and checked values.
`clickResponse` rejects duplicate query keys because its parameter contract uses an object.

24. Explicit per-engine action sequences.

A plan can provide `engineSteps.java` and `engineSteps.rust` with a named
`engineStepContract`. Both lists must contain actions. Shared postconditions remain
active. Each engine records its actual labels, confirmations, values, and requests.
Different actions or observations remain different in comparisons. This option does
not approve functional equivalence or change raw comparison rules.

25. Disposable authenticator inputs from real setup screens.

`totpFill` reads one displayed base32 secret into an engine-specific memory binding.
Later steps can use current, incorrect, expired, or cross-account codes. Codes use
wall time, as authenticator verification does. The helper rejects collisions with
the tested valid window. Setup bodies and submitted requests remain private raw
evidence. Observations retain time and hashes; independent secrets are never forced
to match. This helper does not approve authentication or database differences.

26. Code inputs from owned local delivery fixtures.

`fixtureValueFill` reads one six-digit code from a capability-protected loopback
fixture. It verifies the exact recipient and retained MIME hash. Stored bindings
remain engine-specific. Refusal probes can reuse an old code or enter an incorrect
code. Actual fixture responses and submitted requests remain private evidence.
This does not approve different delivery effects or account security state.

27. Bounded workload output checks and owned cleanup.

`capturedJson` checks already captured response bytes. It requires an exact method,
status, target, query, and named contract. Readiness conditions only control waiting;
ready responses must satisfy exact values. Complete object checks reject extra keys.
Array counts require actual arrays. Captured identifiers can bind subsequent exact
query targets. Response hashes, indices, and observations remain available.

Assertions do not reuse a response from an earlier successful assertion. Cleanup
checks require a fresh response after cleanup starts. All waits have a 30-second
monotonic deadline. No application requests or evaluated code are introduced.

An optional per-engine cleanup runs in `finally`. Its guard requires a configuration
proof and an exact start submission from this operation. It can click one owned
control and require captured stop proof. Cleanup results remain separate from success
observations. Missing ownership prevents action; cleanup failure fails the capture.
Original failures remain recorded. Engine lifecycle cleanup still runs afterward.

28. Exact HTML action mappings during qapps captures.

When a qapps operation declares an engine's HTML screen route, action targets
under that screen's `/apps/` path use the explicit HTML mapping. Queries and
methods remain exact. Unrelated paths and raw captured requests stay unchanged.

29. Retained browser redirect-body gaps.

Chromium may withhold a redirect response body. When the exact same-origin
redirect chain reaches a captured successful terminal response, retain the
unavailable body and browser error on the redirect metadata separately from
functional action errors. Missing terminal bodies and other body failures still
fail capture. This does not supply missing bytes or approve raw equality.
