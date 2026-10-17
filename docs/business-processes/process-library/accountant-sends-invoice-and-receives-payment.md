# Accountant Sends Invoice and Receives Payment

Source: [Business Process Library/Accountant Sends Invoice and Receives Payment](https://moqui.org/docs/mantle/Business%20Process%20Library/Accountant%20Sends%20Invoice%20and%20Receives%20Payment)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

## Story

**(CC Payment)** When shipment is marked as Packed: for all orders associated with the shipment that were paid by credit card and the payments have not been captured, Accounting captures payment (automated).
- visual test:
- transition test:

**(Billing)** When shipment is marked as Packed: Accountant creates an invoice and sends it to Bill-To Customer for the relevant order(s). When payment is received from Bill-To Customer, Accountant associates it with relevant invoice(s) and marks invoices with full payment as paid.
- visual test:
- transition test:
