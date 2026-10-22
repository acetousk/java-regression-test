# Buyer Places Purchase Order

Source: [Business Process Library/Buyer Places Purchase Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Buyer%20Places%20Purchase%20Order)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

* [Product Marketer Maintains Product Information](https://moqui.org/docs/mantle/Business%20Process%20Library/Product%20Marketer%20Maintains%20Product%20Information)
  - visual test:
  - transition test:

## Story

If this is the first time a product has been ordered from a supplier: Buyer makes arrangement with Manufacturer or Distributor (acting as Supplier) to supply the product. Buyer agrees with Supplier on payment terms (pay in advance, pay on delivery (COD), or credit (billing account) with net payment period). Buyer records initial supplier information for product with at least minimum and increment quantities and latest supplier cost (for a given quantity). Buyer may also record more detailed agreement information.
- visual test:
- transition test:

Buyer creates Purchase Order for a single Supplier based on existing re-order Requirements or on manual/external planning. Buyer specifies ship before date (aka "cancel if not shipped by" date) and "cancel all back orders after" date. Buyer may specify a PO#, otherwise it is generated automatically. Buyer approves purchase order. When recording PO, Company automatically sets price as "last price" on Supplier-Product record.
- visual test:
- transition test:

Buyer places an order with the given Supplier by sending Supplier order as a printed document, email, OAGIS or UBL XML message, or by phone. Supplier tells Buyer one or more estimated ship dates and Buyer records those dates.
- visual test:
- transition test:

If the payment term is pay in advance Buyer notifies Accountant who immediately sends payment to Supplier.
- visual test:
- transition test:
