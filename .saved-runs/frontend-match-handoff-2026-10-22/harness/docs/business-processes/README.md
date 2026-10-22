# Business process test checklists

One file per documented process or walkthrough. Original activity order and source wording are retained; prose activities remain grouped as in the source.

Under each activity, fill in:

- visual test: Screens/states to compare, including dialogs, validation messages, layout and styling.
- transition test: Action, inputs, expected navigation/state change and success/error outcome.

Blank fields are planning placeholders, not test results. Use equivalent starting data on both implementations. Some processes require external systems or manual actions; mark browser-only tests N/A where appropriate.

The walkthroughs are UI-oriented. The process library contains higher-level scenarios, including storefront, external/manual and OAGIS integration activities; these do not guarantee corresponding Marble ERP buttons. Some upstream pages are only short sketches.

## Executable visual tests

See [the visual-test runner](../../ui-test/README.md). All 42 documents and their
visual placeholders are inventoried in a best-effort evidence sweep, not complete
executable workflows. Blocked/partial activities are explicitly reported and do not
pass the workflow gate. Specs stay under `ui-test/docs/business-process/`; screenshots,
diffs and comparison reports go under `.runs/<run-id>/ui-test/`, grouped by process
library activity and then render mode (`apps/`, `vapps/`, `qapps/`). Temporary `--skip-step-4` mode loads all demo data and skips the
database comparison, not visual assertions.

## Marble ERP UI walkthroughs

- [Initial Setup and Basics](walkthroughs/initial-setup-and-basics.md)
- [Company Setup](walkthroughs/company-setup.md)
- [Pricing and Promotions](walkthroughs/pricing-and-promotions.md)
- [Find and Create Customer](walkthroughs/find-and-create-customer.md)
- [Place and Approve Sales Order](walkthroughs/place-and-approve-sales-order.md)
- [Ship Sales Order](walkthroughs/ship-sales-order.md)
- [Shipping Management with Picklists](walkthroughs/shipping-management-with-picklists.md)
- [Procure to Pay](walkthroughs/procure-to-pay.md)
- [Transfer Shipments](walkthroughs/transfer-shipments.md)
- [Bank Accounts](walkthroughs/bank-accounts.md)
- [Period Closing](walkthroughs/period-closing.md)

## Mantle business-process library

- [Accountant Receives Invoice and Sends Payment](process-library/accountant-receives-invoice-and-sends-payment.md)
- [Accountant Reconciles Bank Account](process-library/accountant-reconciles-bank-account.md)
- [Accountant Sends Invoice and Receives Payment](process-library/accountant-sends-invoice-and-receives-payment.md)
- [Buyer Places Purchase Order](process-library/buyer-places-purchase-order.md)
- [Carrier Does Not Deliver Shipment to Customer](process-library/carrier-does-not-deliver-shipment-to-customer.md)
- [Carrier Returns Undeliverable Shipment to Company](process-library/carrier-returns-undeliverable-shipment-to-company.md)
- [Company Approves Sales Order](process-library/company-approves-sales-order.md)
- [Company Fulfills Sales Order](process-library/company-fulfills-sales-order.md)
- [Company Processes Return Received](process-library/company-processes-return-received.md)
- [Customer Cancels Order](process-library/customer-cancels-order.md)
- [Customer Creates and Edits Account](process-library/customer-creates-and-edits-account.md)
- [Customer Finds Product](process-library/customer-finds-product.md)
- [Customer Returns Product](process-library/customer-returns-product.md)
- [Customer Reviews Order History and Status](process-library/customer-reviews-order-history-and-status.md)
- [Inventory Mover Checks Physical Inventory](process-library/inventory-mover-checks-physical-inventory.md)
- [Inventory Mover does Stock Move](process-library/inventory-mover-does-stock-move.md)
- [Inventory Mover Puts Away Inventory](process-library/inventory-mover-puts-away-inventory.md)
- [Marketer Maintains General Site Content](process-library/marketer-maintains-general-site-content.md)
- [OAGIS Order to Cash](process-library/oagis-order-to-cash.md)
- [OAGIS Procure to Pay](process-library/oagis-procure-to-pay.md)
- [OAGIS Work Plan to Cash](process-library/oagis-work-plan-to-cash.md)
- [Placing Customer Adds Product to Cart](process-library/placing-customer-adds-product-to-cart.md)
- [Placing Customer Places a Sales Order - Online Checkout](process-library/placing-customer-places-a-sales-order-online-checkout.md)
- [Placing Customer Places a Sales Order - Through CSR](process-library/placing-customer-places-a-sales-order-through-csr.md)
- [Placing Customer Places a Sales Order - Through EBay](process-library/placing-customer-places-a-sales-order-through-ebay.md)
- [Product Marketer Maintains Product Information](process-library/product-marketer-maintains-product-information.md)
- [Sales Representative Leads Prospects from RFQ to Sales Order](process-library/sales-representative-leads-prospects-from-rfq-to-sales-order.md)
- [Sales Representative Seeks Prospects and Opportunities](process-library/sales-representative-seeks-prospects-and-opportunities.md)
- [Shipment Receiver Receives Shipment](process-library/shipment-receiver-receives-shipment.md)
- [Story of Online Retail Company](process-library/story-of-online-retail-company.md)
- [B2B Sales Process](process-library/b2b-sales-process.md)

## Supporting references (not activity checklists)

- [Marble ERP application outline](https://moqui.org/docs/apps/Marble+ERP+User+Guide/Application+Outline)
- [Statuses and types](https://moqui.org/docs/apps/Marble+ERP+User+Guide/Statuses+and+Types)
- [Actor definitions](https://moqui.org/docs/mantle/Business+Process+Library/Actor+Definitions)
- [Business-process library index](https://moqui.org/docs/mantle/Business+Process+Library)
- [SimpleScreens reference documents](https://github.com/moqui/SimpleScreens/tree/master/document)
