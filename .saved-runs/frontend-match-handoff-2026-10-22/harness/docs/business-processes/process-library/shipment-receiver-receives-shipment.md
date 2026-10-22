# Shipment Receiver Receives Shipment

Source: [Business Process Library/Shipment Receiver Receives Shipment](https://moqui.org/docs/mantle/Business%20Process%20Library/Shipment%20Receiver%20Receives%20Shipment)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

* [Buyer Places Purchase Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Buyer%20Places%20Purchase%20Order)
  - visual test:
  - transition test:

## Story

Supplier ships items ordered via Carrier.
- visual test:
- transition test:

When Carrier delivers shipment, Shipment Receiver briefly reviews incoming shipment and signs for receipt of the product from Carrier. If the quantity is not the quantity ordered or it is clearly a different product Shipment Receiver will contact Supplier and resolve issue before signing for receipt. If no resolution is reached Shipment Receiver will not sign for receipt and the shipment will be returned to Supplier.
- visual test:
- transition test:

If shipment received is clearly a return (has RMA# or Return ID), Shipment Receiver gives items to CSR for handling. If shipment received does not correspond to a known PO or Return, Shipment Receiver gives items to Buyer for handling.
- visual test:
- transition test:

If shipment received is clearly for a purchase order (has PO#) Shipment Receiver processes incoming inventory. Shipment Receiver finds the PO corresponding to the items received and records PO receipt (inventory) information for it including quantity and cost, but no location yet.  If Shipment Receiver records a higher quantity received than was ordered, system automatically adjusts the PO being received against.
- visual test:
- transition test:

Shipment Receiver reviews incoming items. Shipment Receiver determines the Product ID. Shipment Receiver checks the item to make sure all features match what is currently in the system performs quality checks according to a checklist specific to that product (if one exists).
- visual test:
- transition test:

If the product is a different color than what is in the system Shipment Receiver creates a new Product ID and records it.
- visual test:
- transition test:

If product that arrives is not the product on the PO and has already been received (and not just a different color) then Shipment Receiver sends it to Buyer for handling.
- visual test:
- transition test:

Shipment Receiver sets the inventory aside for Inventory Mover to put away.
- visual test:
- transition test:

If part of the PO is not yet received Buyer contacts Supplier and resolves any issues (not yet received inventory, wrong inventory, etc.).
- visual test:
- transition test:
