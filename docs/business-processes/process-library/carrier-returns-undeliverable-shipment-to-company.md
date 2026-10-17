# Carrier Returns Undeliverable Shipment to Company

Source: [Business Process Library/Carrier Returns Undeliverable Shipment to Company](https://moqui.org/docs/mantle/Business%20Process%20Library/Carrier%20Returns%20Undeliverable%20Shipment%20to%20Company)

Type: Business-process description; verify UI applicability.

## Dependencies

[Company Fulfills Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Fulfills%20Sales%20Order)
- visual test:
- transition test:

## Story

Carrier Returns Undeliverable Shipment to Company. Shipment Receiver sets the package aside and notifies CSR. CSR contacts Customer to check and correct address and see if Customer still wants the item(s). CSR creates a new label (through any Carrier, preferably the original carrier), places a new label on the package(s), records the new tracking number (edit the same shipment), and ships them out again. CSR may choose to charge Customer for shipping after clearing it with Customer (create order for shipping only).
- visual test:
- transition test:

If Customer does not want the item(s) CSR creates a return and sets the response type on the return to either store credit, refund, or replacement (may be partial payment, etc.; CSR sets other return fields) and sets return status to approved and complete (original package received).
- visual test:
- transition test:

Carrier sends notice that they could not deliver package or Customer refuses to pay the customs and specifies approximate number of days to resolve the issue. CSR contacts Customer to notify them and request they go pick it up. If Customer does not pick up package from Carrier or contact Carrier for delivery within the number of days specified by Carrier, Carrier may destroy the package right away. Carrier may also contact Company (via Carrier Contact) and ask what to do with the package. Carrier Contact will review the value of the item(s) and instruct Carrier to either return the package (and incur a charge) or fax a "please destroy" form so that Carrier can destroy the package.
- visual test:
- transition test:
