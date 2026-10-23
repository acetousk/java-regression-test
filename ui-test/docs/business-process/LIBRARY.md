# Business process library: functional screen tests

Each process here is something a Marble ERP user does, written as a test that does it through the screens.
Tests run in Step 5 under the transaction harness: every step runs on Java and Rust in lockstep, and the
step passes only when both engines show the same page and commit the same writes.

Sources:
- the Marble ERP user-guide walkthroughs (`docs/business-processes/walkthroughs/`)
- the Mantle business-process library (`docs/business-processes/process-library/`)
- the Mantle flow tests the process steps are checked against (`mantle-usl/src/test/groovy/*Flow.groovy`)

## Starting data

Both engines load the same seed and demo data. Tests build on this demo data, not on each other's records:
- store `POPC_DEFAULT` "Ziziwork Retail Store", vendor org `ORG_ZIZI_RETAIL`
- warehouse `ZIRET_WH`
- products `DEMO_1_1`, `DEMO_2_1`, `DEMO_3_1` and others
- user `john.doe` / `moqui`

Each activity logs in with its own browser session. It creates the records it works on, with fixed names
so that both engines assign the same IDs. Activities can run in any order. An activity that needs stock
receives its own first.

## Processes

Status: **spec** means an executable spec exists. **planned** means a screen test is still to be written.
**n/a** means the process has no Marble ERP screens to drive, such as a storefront, an EDI/OAGIS
integration or a carrier event.

| # | Process | Actor | Screens | Spec | Status |
|---|---------|-------|---------|------|--------|
| 1 | Create individual customer | CSR | Customer/FindCustomer → EditCustomer | `walkthroughs/find-and-create-customer` | spec |
| 2 | Create sales account and sales contact | CSR | Customer/FindCustomer → EditCustomer | `walkthroughs/create-sales-account` | spec |
| 3 | Place and approve sales order | CSR | Order/FindOrder → OrderDetail | `walkthroughs/place-and-approve-sales-order` | spec |
| 4 | Ship sales order (simple: create shipment, issue and pack, pack, ship) | Shipper | OrderDetail → Shipment/ShipmentDetail | `walkthroughs/ship-sales-order` | spec |
| 5 | Receive customer payment for the sales invoice | Accountant | Accounting/Invoice/EditInvoice → Payment | `process-library/accountant-sends-invoice-and-receives-payment` | spec |
| 6 | Add supplier | Buyer | Supplier/FindSupplier → EditSupplier | `walkthroughs/procure-to-pay` | spec |
| 7 | Place purchase order | Buyer | Order/FindOrder → OrderDetail | `process-library/buyer-places-purchase-order` | spec |
| 8 | Receive purchase shipment into inventory | Receiver | Shipment/ShipmentDetail (Receive) | `process-library/shipment-receiver-receives-shipment` | spec |
| 9 | Pay supplier invoice | Accountant | Accounting/Invoice → Payment | `process-library/accountant-receives-invoice-and-sends-payment` | planned |
| 10 | Receive inventory directly | Inventory mover | Asset/Asset/FindSummary (Receive Direct) | `walkthroughs/initial-setup-and-basics` | planned |
| 11 | Move stock between locations | Inventory mover | Asset/AssetDetail (Move) | `process-library/inventory-mover-does-stock-move` | planned |
| 12 | Record physical inventory count | Inventory mover | Asset/PhysicalInventory | `process-library/inventory-mover-checks-physical-inventory` | planned |
| 13 | Transfer shipment between facilities | Shipper | Shipment/FindShipment (New Transfer Shipment) | `walkthroughs/transfer-shipments` | planned |
| 14 | Picklist pick and pack | Warehouse | Shipping/Picklist, PackShipment | `walkthroughs/shipping-management-with-picklists` | planned |
| 15 | Cancel sales order | CSR | OrderDetail (Close Order / Cancel) | `process-library/customer-cancels-order` | planned |
| 16 | Customer return: return, receive, refund or credit | CSR | OrderDetail → Return/EditReturn | `process-library/customer-returns-product` | planned |
| 17 | Create product and price | Product marketer | Catalog/Product/FindProduct → EditProduct, Prices | `process-library/product-marketer-maintains-product-information` | planned |
| 18 | Create promotion | Product marketer | ProductStore/Promotion | `walkthroughs/pricing-and-promotions` | planned |
| 19 | Create internal organization with contact info | Admin | Party/FindParty → EditParty | `walkthroughs/initial-setup-and-basics` | planned |
| 20 | Work plan to cash: project, task, time entry, client invoice | Project manager | Project, Task, HumanRes/EditRateAmounts | `process-library/oagis-work-plan-to-cash` | planned |
| 21 | Sales rep: request (RFQ) to sales order | Sales rep | Request/FindRequest → EditRequest | `process-library/sales-representative-leads-prospects-from-rfq-to-sales-order` | planned |
| 22 | Manual journal entry, then post | Accountant | Accounting/Transaction | `walkthroughs/period-closing` | planned |
| 23 | Bank account setup and reconciliation | Accountant | Accounting/FinancialAccount | `walkthroughs/bank-accounts` | planned |
| 24 | Close fiscal period | Accountant | Accounting/TimePeriod | `walkthroughs/period-closing` | planned |
| 25 | Review accounting reports (income statement, balance sheet) | Accountant | Accounting/Reports | `walkthroughs/initial-setup-and-basics` | planned |
| - | Online checkout, cart, finding products, account self-service | Storefront customer | PopCommerce (not installed) | - | n/a |
| - | eBay order, OAGIS order-to-cash and procure-to-pay messages | Integration | none | - | n/a |
| - | Carrier fails to deliver or returns an undeliverable shipment | Carrier | external event | - | n/a |
| - | Marketer maintains general site content | Marketer | PopCommerce wiki (not installed) | - | n/a |

Rows 4, 5, 8 and 9 continue the order a test created in an earlier step of the same spec. They are written
as later steps of one activity, so the spec for a whole flow (order to cash, procure to pay) contains them.

## Writing a spec

- Write one `*.activity.spec.js` per walkthrough or process, with one `registerActivity` per activity.
  Start each activity at Login, so it runs on its own.
- Keep each step to what a user does: click a dashboard link, open a dialog, fill fields, submit. Mark
  steps that submit with `writes: true`.
- Get dialog IDs, button labels and field names from the screen XML. A `container-dialog` renders its
  `button-text` as a button and its `id` on the dialog. A form field renders as `[name=<field>]`, and a
  drop-down's input has the id `<form name>_<field name>`. Use the helpers in `process-helpers.js`.
- Each step ends by asserting the result a user would see, such as the new record's page or the status it
  moved to. Where the step returns an ID, add a `verify` that the two engines agree.
