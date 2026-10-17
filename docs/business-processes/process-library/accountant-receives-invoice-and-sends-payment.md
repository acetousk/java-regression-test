# Accountant Receives Invoice and Sends Payment

Source: [Business Process Library/Accountant Receives Invoice and Sends Payment](https://moqui.org/docs/mantle/Business%20Process%20Library/Accountant%20Receives%20Invoice%20and%20Sends%20Payment)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

* [Shipment Receiver Receives Shipment](https://moqui.org/docs/mantle/Business%20Process%20Library/Shipment%20Receiver%20Receives%20Shipment)
  - visual test:
  - transition test:

## Story

Supplier sends invoice or other payment request to Accountant. If payment term is "pay on delivery" Accountant
sends the payment immediately. If payment term is "credit" Accountant sends payment within the payment
period agreed to.
- visual test:
- transition test:

If Accountant receives an invoice that does not match the PO, Accountant notifies Buyer who contacts Supplier to resolve the issue.
- visual test:
- transition test:
