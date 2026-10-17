# Business-process visual evidence sweep

Status: **FAILED / INCOMPLETE**, with evidence retained. No full workflow passes.

- 42 source documents, 744 visual placeholders.
- 3 render modes: apps, vapps, qapps.
- 2,232 activity/mode reports, all blocked as paired workflows.
- 462 unique browser captures; 17 dialogs opened successfully (Rust qapps).
  This is NOT the application's dialog count or complete dialog coverage. Only
  recognized labels on mapped screens were attempted; many other dialogs were
  blocked or not mapped by this sweep.
- 3,336 activity screenshot references plus 5 anonymous-login screenshots.
  Repeated screen/dialog probes reuse explicitly identified captures via hard links.
- 1,668 diagnostic-only image comparisons. These include error/incomplete pages;
  their image equality is NOT evidence that the activity was executed correctly.
- Both isolated servers shut down gracefully; disposable databases were removed.
- Step 4 database comparison was intentionally skipped.

## Browse evidence

Start with `summary.json`, then:

```text
process-library/<story>/activity-NNN/<apps|vapps|qapps>/comparison.json
walkthroughs/<process>/activity-NNN/<apps|vapps|qapps>/comparison.json
```

Each activity includes original source text/line, mapping classification and
limitations. When obtainable, sibling files include Java/Rust PNGs, diff PNG,
rendered HTML and visible text. Capture metadata includes failed requests, HTTP
errors, JS errors, authentication status, requested/final URLs and dialog result.
Unmapped external/manual/storefront steps have reports but no invented screenshots.

## Observed blockers

- Java reported widespread missing UI globals (`$`, `moqui`, `Vue`); screenshots
  show incomplete/un-styled UI. Some navigation/dialog interactions timed out.
- Rust vapps probes returned HTTP 404 for most routes.
- Rust apps/qapps produced some screens; 17 qapps dialogs opened. Other probes
  had route/resource failures, missing controls or unmet business prerequisites.
- Entry-screen captures do not execute prose stories. Business forms were not
  filled/submitted, prerequisite records were not created, and external/manual
  steps were not performed. Authentication used the seeded john.doe login form.

## Runtime provenance

- Java: this worktree's `moqui-framework`, revision
  `23eb356556d3bc025f49bacfb8e2201851c236a0`; WAR built locally with Gradle `war`.
- Java's missing moqui-fop dependency was copied from the existing local
  `/home/user/moqui/master/runtime/component/moqui-fop`, revision
  `1684dad02bb4b97cb4d7dbce5271937e7b28273e`.
- Rust: existing active `/home/user/moqui/mr-moqui` checkout, revision
  `b7823494acd4d027a4edf16bf40e617a78c7953c`, using its existing debug binary.
  This is NOT the Rust submodule revision in the frontend-match worktree.
- Each engine used its own runtime and a fresh PostgreSQL database with all data
  loading enabled. Runtime component sets were not certified equivalent.
- Java/Rust test HTTP ports: 18091 / 18092. Browser: system Chromium, viewport
  1440x1000, en-US, UTC. Both seeds authenticated successfully.

See the parent run's `verification.json`, `shutdown.json`, boot logs and private
configs for lifecycle evidence. This published copy excludes `_sessions/` and
redacts credentials, cookies and embedded session-token values from text artifacts.
Original private evidence remains under `.runs/`.
