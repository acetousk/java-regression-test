# Inventory Mover Puts Away Inventory

Source: [Business Process Library/Inventory Mover Puts Away Inventory](https://moqui.org/docs/mantle/Business%20Process%20Library/Inventory%20Mover%20Puts%20Away%20Inventory)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Dependencies

* [Shipment Receiver Receives Shipment](https://moqui.org/docs/mantle/Business%20Process%20Library/Shipment%20Receiver%20Receives%20Shipment)
  - visual test:
  - transition test:

## Story

Inventory Mover receives the product from Shipment Receiver.
- visual test:
- transition test:

Inventory Mover prints and applies label containing Product ID (bar code and text). Inventory Mover optionally prints and applies label with Inventory Item ID, noting that if items are split system will have different Inventory Item IDs for some items later on.
- visual test:
- transition test:

Inventory Mover then determines location for items. If the product does not have a primary location, the Inventory Mover finds an appropriate empty location to use and assigns that as the primary location for the product. Inventory Mover fills the primary location and puts any excess product in a bulk location.
- visual test:
- transition test:

Inventory Mover assigns location where items were placed to the inventory item previously received. If items were placed in multiple locations Inventory Mover does quick stock moves to record where inventory was actually placed, and checks to make sure the quantity that remains in the original location is the quantity actually placed there. If inventory is received into both bulk and pick/primary locations then original location should be the bulk location and the stock move should be done to the pick/primary location.
- visual test:
- transition test:
