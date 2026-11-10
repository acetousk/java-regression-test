# Conditional presentation checks

Change 7 keeps raw byte comparisons and functional observations separate. A reviewed rule must match the selected screen key, render mode, exact route path and functional suite ID. No rule extends to another route or changes `result.passed`. The separate `approvedPresentation` result still requires the comparator's request, non-markup response, download and database checks.

`approved_functional_plan.json` defines representative operations for the reviewed Print Job HTML widgets and Data Document Fields HTML/Qapps controls. Its explicit unresolved cases block a claim that the entire suite is qualified. Other screens and Resource implementation differences are outside these suites. Input domains are not exhaustively enumerated.

The driver stores:

- `functionalObservations`: completed action identities, selected/submitted values, target paths and assertion outcomes, compared without dropping entries.
- `functionalRawObservations`: verbatim visible label text, option text and target metadata.
- `functionalComplete`: all scenario steps produced observations; errors, missing response bodies and raw differences remain recorded independently.
- `functionalSuiteId`: matched against the rule's exact screen/mode/path scope.

`exactLabel` checks semantic control labels after removing explicitly decorative nodes and collapsing presentation whitespace. It preserves raw visible text separately and does **not** establish byte equality. `exactText` compares visible text without whitespace normalization. Every changed label word fails. Native and Select2/Quasar choices are operated through their visible controls; hidden inputs are read only to verify submitted selection values. `submitValues` checks the actual POST payload. Reload/value and row-count assertions establish persisted visible outcomes separately from the full database comparison.

`confirmClick` accepts only the specified confirmation message and records the chosen button label. It never installs blanket auto-approval. Native confirmations use the browser's standard English OK/Cancel labels; custom confirmations record their visible labels, so an OK/Confirm difference remains a difference.

Run `node --test acceptance/ui/functional_actions.test.cjs acceptance/ui/operations.test.cjs acceptance/ui/approved_presentation.test.cjs` for the focused harness checks. Live execution requires a matching boot gate and newly owned disposable runtimes. Never reuse another acceptance run's databases.
