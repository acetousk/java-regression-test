# PRs to merge for the business-process screen tests

These PRs make the business-process activities pass on Java and Rust in lockstep. Merge each stack bottom-up.

## mr-moqui (Rust): one stack, #95 → #129

| PR | Branch | What |
|----|--------|------|
| #95 | fix/apps-navbar-item-templates | Render apps navbar items as templates (base: fix/qapps-shell-layout, pushed without a PR) |
| #102 | fix/apps-select-open-on-click | Open apps drop-downs on click, not focus |
| #103 | fix/entity-auto-empty-string-null | entity-auto sets an empty-string parameter as null |
| #104 | fix/reset-sequence-banks-after-load | Drop sequence banks after the empty-DB load |
| #110 | fix/qapps-dense-button-spacing | Apply button spacing in Quasar 2 |
| #111 | fix/test-login-after-password-upgrade | Show Test Login after the password is re-hashed |
| #112 | fix/qapps-page-margin-collapse | Let page margins collapse as in Quasar 1 |
| #113 | fix/user-visit-id | Expose ec.user.visitId as Java does |
| #114 | fix/find-summary-java-order | Find-form header summary over every header field, in form order |
| #115 | fix/service-empty-typed-param-null | Pass an empty typed parameter as null (order item price) |
| #116 | fix/validation-error-shown-as-java | Show an empty required parameter as Java does |
| #117 | fix/service-call-web-send-json-response | service-call sends its result with web-send-json-response (store facility) |
| #118 | fix/decimal-scale-as-java | Read decimals without the column scale; keep BigDecimal's scale when an operand is zero |
| #119 | fix/dynamic-select-as-select2 | Drop-down opens on click and keeps the transition's option order |
| #120 | fix/seca-order-as-java | Run same-priority SECA rules in Java's HashMap order (sequence ids) |
| #121 | fix/link-transition-alias | Link to an alias transition's screen; find `//` paths by name; generate actions for a running script on their own thread |
| #122 | fix/view-entity-form-shape | Give a view entity's form shape its aliases and primary key |
| #123 | fix/section-in-form-keeps-owner | A section in a form-list cell keeps the row's form (Pack items) |
| #124 | fix/timestamp-param-user-zone | Read a text timestamp parameter in the user's zone |
| #125 | fix/date-time-minute-step | Start a date-time field on its minute step |
| #126 | fix/temporal-format-as-java | Show a timestamp from a `from` path, or formatted with no pattern, as Java does (Shipment Detail) |
| #128 | fix/string-masker | StringUtilities.masker for GL account codes (Edit Invoice GL Transactions) |
| #129 | fix/form-pass-through-skips-fields | A form's pass-through hidden inputs skip its own fields, as Java (Pack Item posted shipmentId twice) |

Earlier, separate: #68 (on fix/login-history), #51, #50, #29, #20.

## mr-mantle-usl (Rust's mantle)

| PR | Branch | What |
|----|--------|------|
| #1 | fix/order-item-total-decimal-scale | get#OrderItemTotal keeps the scale of Java's 0.0 and 1.0 literals |
| #2 | fix/shipment-item-source-status-default | create#ShipmentItem leaves the source status null as Java (stacked on #1) |

## MrSimpleScreens (Rust's SimpleScreens)

| PR | Branch | What |
|----|--------|------|
| #4 | fix/shipment-shipping-options-js | Iterate shipping options with for...of in getShippingOptions |

## moqui-framework (Java)

| PR | Branch | What |
|----|--------|------|
| #751 | fix/deterministic-visit-close-once | Close a deterministic visit only once |
| #752 | fix/deterministic-screen-test-lane | Run joined screen-test renders in the holder's lane |
| #753 | fix/deterministic-startup-index | Index empty DataFeeds inline in deterministic mode |

## java-regression-test (harness): one stack, #24 → #41

| PR | Branch | What |
|----|--------|------|
| #24 | fix/activity-barrier-timeouts | Wait out paired-write comparisons and page rendering |
| #25 | test/save-icon-fix-run | Save the icon-fix run of find-and-create-customer |
| #26 | perf/persistent-cdc-session | Read CDC through one psql session per database |
| #27 | test/business-process-library | Business-process library and the sales-order spec |
| #28 | feat/java-opensearch | `--java-opensearch` for Java's search facade |
| #29 | test/sales-order-create-parity | Type Tom Select searches reliably and pick Joe Q Public |
| #30 | fix/activity-loading-bar-settle | Functional parity; place and approve a sales order end to end |
| #31 | test/create-sales-account | Create a sales account and contact; close the focus tooltip before opening a dialog |
| #32 | test/ship-sales-order | Ship a sales order: create shipment, pack, ship; record open requests and DOM of a failed step |
| #33 | test/receive-customer-payment | Receive a check for a sales invoice (Send & Apply the promised payment) |
| #34 | fix/clear-java-sessions | Clear Java's stored Jetty sessions before startup (stale visit close) |
| #35 | test/add-supplier | Add a supplier and its order email; click a details-summary menu as a button |
| #36 | test/purchase-order-receive | Place and approve a purchase order; receive its shipment into the warehouse |
| #37 | test/pay-supplier-invoice | Approve the supplier invoice and record the payment sent |
| #38 | test/receive-inventory-direct | Receive inventory directly, without a purchase order |
| #39 | test/stock-move | Move part of an asset to another location; shared Receive Direct steps |
| #40 | test/physical-inventory | Record a physical inventory count with a variance reason |
| #41 | test/transfer-shipment | Transfer stock between facilities: schedule, pack from an asset, ship, receive, deliver |

## Business processes passing in lockstep

| Process | Steps | Paired writes | Run |
|---------|-------|---------------|-----|
| place-and-approve-sales-order | 10/10 | 17 | 2026-10-23_11-06-21.976725Z |
| create-sales-account, then find-and-create-customer, then place-and-approve-sales-order | 6/6, 5/5, 10/10 | 10, 15, 29 (cumulative, 0 unpaired) | 2026-10-23_11-43-49.456151Z |
| ship-sales-order (places and approves its own order first) | 16/16 | 30, 0 unpaired | 2026-10-23_16-03-15.654529Z (with #126); 2026-10-23_16-20-41.915010Z (shared order steps) |
| accountant-sends-invoice-and-receives-payment (order paid by check, shipped, check applied) | 18/18 | 16 (46 cumulative), 0 unpaired | 2026-10-23_16-20-41.915010Z |
| add-supplier (organization supplier, then its order email) | 5/5 | 6 (57 cumulative), 0 unpaired | 2026-10-23_16-20-41.915010Z |
| buyer-places-purchase-order (10 DEMO_1_1 from Ziddleman for Ziziwork Retail) | 8/8 | 7 (64 cumulative), 0 unpaired | 2026-10-23_16-20-41.915010Z |
| shipment-receiver-receives-shipment (its own purchase order, then create, schedule, receive the shipment) | 12/12 | 12 (76 cumulative), 0 unpaired | 2026-10-23_16-20-41.915010Z |
| accountant-receives-invoice-and-sends-payment (its own purchase order and receipt, then approve the invoice and record the payment sent) | 15/15 | 40 cumulative, 0 unpaired | 2026-10-23_17-14-21.830766Z (with #128) |
| receive-inventory-direct (5 DEMO_2_1 into Ziziwork Retail Warehouse at 7.50, no purchase order) | 5/5 | 44 cumulative, 0 unpaired | 2026-10-23_17-14-21.830766Z |
| inventory-mover-does-stock-move (receive 10 DEMO_2_1 at bulk 01010102, move 4 to pick 01010101) | 8/8 | 18 cumulative, 0 unpaired | 2026-10-23_17-41-28.777761Z |
| inventory-mover-checks-physical-inventory (receive 8 DEMO_2_1 at 01010202, count 2 less, Damaged) | 8/8 | 32 cumulative, 0 unpaired; same variance row on both DBs | 2026-10-23_17-41-28.777761Z |
| transfer-shipments (receive 6 DEMO_2_1, add the back room facility, transfer 4 there: schedule, pack and issue from the asset, pack, ship, receive, deliver) | 17/17 | 25, 0 unpaired | 2026-10-23_18-26-01.084676Z (with mr-mantle-usl #2, #129) |
