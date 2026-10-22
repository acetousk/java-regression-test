# Find Transfer Shipments: navbar parity

Random selection from unique mapped walkthrough routes (no dialogs):
`marble/Shipment/FindShipment?shipmentTypeEnumId=ShpTpTransfer`.
Only `apps` and `qapps` were attempted. No business records were submitted.

## Before

Evidence: `.runs/2026-10-17_04-34-08.248361Z/`.
Reports and unmodified screenshots: `ui-test/transfer-shipment/`.

- Java: both screens captured without browser/resource errors.
- Rust apps: blocked by `Error rendering section [TopNavSection]`:
  `cannot read property 'notificationCount' of null`. Its 19.01% differing pixels
  are diagnostic only, not a valid screen comparison.
- Qapps: both captured; 24,308 / 1,440,000 differing pixels (1.6881%).
  Rust lacks Saved Finds and the active Type: Transfer filter summary. Sort icons,
  spacing, navbar and footer also differ. This is not negligible parity.

## Narrow runtime fix

PR: https://github.com/moqui/mr-moqui/pull/27

Java `webroot/screen/includes/navbar.html.ftl` interprets each
`STRT_HEADER_NAVBAR_ITEM` as a template (`?interpret`), including directives.
Rust's `navbar.html.fancy` used `ec.resource.expand`, which expands expressions
but does not execute the item's `<#assign>` / `<#if>` directives. SimpleScreens'
navbar item assigns `noticeCounts` from `get#UserNoticeCounts`, so interpolating
its properties without executing the assignment fails.

Use `sri.renderInlineText(navbarItem)`, the existing trusted Fancy template
rendering path also used for footer items. This executes the actual service and
conditional, rather than substituting zero counts or removing the navbar item.

## After and limitations

Evidence: `.runs/2026-10-17_04-35-45.588383Z/`.
Rust apps and qapps both captured without browser/resource/section errors.
Assertions against the captured apps DOM verify:

- no `TopNavSection` rendering error;
- the seeded user's notification counter renders as `0`;
- all four notification/message/calendar/task links are present;
- the assignment directive is not emitted as escaped text.

The first three assertions fail against the before DOM and pass after the fix.
This is runtime browser validation, not a new automated unit test or full parity.

The after run's Java oracle was invalid: raw FreeMarker directives/interpolations
appeared in output, with literal-template resource 404s and JavaScript errors.
Its comparison percentages are diagnostic only; no before/after pixel improvement
is claimed. Investigate/stabilize that oracle before further visual claims.

Both runs used fresh isolated databases and verified graceful shutdown/cleanup.
The prebuilt Rust executable `/home/user/moqui/mr-moqui/target/debug/moqui` was
used with this worktree's runtime and explicit HTML/QVT macro overrides; the
engine was not rebuilt. Private `probe-provenance.json` records executable hashes
and checkout identities. No current-engine-source parity is claimed. Private
configs, HTML, cookies and full logs must not be published.
