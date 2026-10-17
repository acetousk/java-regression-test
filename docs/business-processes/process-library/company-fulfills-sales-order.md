# Company Fulfills Sales Order

Source: [Business Process Library/Company Fulfills Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Fulfills%20Sales%20Order)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

* [Company Approves Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Approves%20Sales%20Order)
  - visual test:
  - transition test:

## Story

### Pick

Once inventory is available (for part or all of the order, depending on preference) Fulfillment Manager creates a picklist and prints it (for up to X orders at a time, depending on batch pick size; only orders where inventory is available for part or all of the order, depending on preference). Picker walks the pick floor and at each location listed on the pick sheet Picker picks the amount specified for the location and places items in the cart bin(s) specified on the pick sheet, and verifies each is the correct location by looking at the pack sheet for the order in that bin. Once all items on the pick sheet are picked Picker records status update for the picklist.
- visual test:
- transition test:

If Picker notices that there is insufficient quantity in the pick location for a given picklist item Picker will ask an Inventory Mover to find inventory in a bulk location. If Inventory Mover finds needed inventory in a bulk location they will do a quick Stock Move for that inventory from the bulk to the pick location. If Inventory Mover does not find bulk inventory Picker puts anything picked back in the appropriate location(s). Inventory Mover records the physical inventory adjustment.
- visual test:
- transition test:

### Pack

Packer selects a pick bin and removes the packing sheet and scans the Order ID bar code (which contains order and ship group info). Packer selects the appropriate packaging (boxes). Packer scans the Product ID on each item and places the items within the packaging. Packer weighs each package as it is filled (including all packing materials) and records the weight. Packer marks the shipment as packed.
- visual test:
- transition test:

Packer fills out any applicable customs forms based on the information returned, and attaches to package(s). Packer prints a shipping label and attaches it to each package. Packer prints personalized inserts and places inside the package. Packer seals the package and places into the appropriate outgoing carrier container.
- visual test:
- transition test:

Company automatically creates Parcels Shipped Report. Divided by: shipping method, packer. Purpose: used for packer incentives, capacity planning.
- visual test:
- transition test:

Carrier picks up packages in outgoing container and delivers them to Ship-To Customer.
- visual test:
- transition test:

If Placing Customer wants to pick up an order at the warehouse, then Customer Service picks and packs the order and uses the Quick Ship functionality so the system recognizes that the order is fulfilled.
- visual test:
- transition test:
