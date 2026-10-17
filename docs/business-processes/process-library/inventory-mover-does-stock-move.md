# Inventory Mover does Stock Move

Source: [Business Process Library/Inventory Mover does Stock Move](https://moqui.org/docs/mantle/Business%20Process%20Library/Inventory%20Mover%20does%20Stock%20Move)

Type: Business-process description; verify UI applicability.

Trigger: Based on touch frequency or other report showing a non-optimal location, move inventory to match frequency or other criteria (Optimize Locations)
- visual test:
- transition test:

## Ideas to Incorporate

## Dependencies

## Story

*(Bulk-to-Pick)* Inventory Mover gets a list of inventory items by Product ID and facility location (generated according to pick location where quantity drops below configured threshold). Inventory Mover moves inventory from bulk location to pick location according to list. Inventory Mover records actions to represent actual inventory moves (not listed ones). If Inventory Mover finds that inventory in the bulk location is short of system record during a stock move, Inventory Mover records moves of available quantity and records a physical inventory adjustment with difference between requested move amount and actual move amount.
- visual test:
- transition test:

*(Optimize Locations)* TODO
- visual test:
- transition test:
