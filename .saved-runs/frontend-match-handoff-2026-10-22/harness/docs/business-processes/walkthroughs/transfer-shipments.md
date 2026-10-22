# Transfer Shipments

Source: [Marble ERP User Guide/Warehouse/Transfer Shipments](https://moqui.org/docs/apps/Marble%20ERP%20User%20Guide/Warehouse/Transfer%20Shipments)

Type: UI walkthrough.

Transfer shipments are used to transfer inventory from one facility to another. They use pack and inventory issuance from the origin facility just like outgoing shipments as well as inventory receipt just like incoming shipments.
- visual test:
- transition test:

## Create, Pack and Ship a Transfer Shipment

- start on Find Shipment screen
  - visual test:
  - transition test:
- use the **New Transfer Shipment** dialog, specify from and to facilities
  - visual test:
  - transition test:
- while still in Input status add items (Product, Quantity) to transfer
  - visual test:
  - transition test:
- once all items added use *Set Scheduled* button to update status to allow pack/issue of inventory
  - visual test:
  - transition test:
- this shipment is not based on an order so there are no inventory reservations to pack against
  - visual test:
  - transition test:
- use the *Pack/Issue Item* dialog to select inventory to use and to pack and issue to the shipment
  - visual test:
  - transition test:
- once all items desired are packed use the *Set Packed* button to change status to Packed
  - visual test:
  - transition test:
- if a shipping label is needed
    - visual test:
    - transition test:
    - note that both origin and destination facilities must have an address set to create labels
      - visual test:
      - transition test:
    - assign quantities to packages as needed
      - visual test:
      - transition test:
    - use the *Update Package* dialog to set box type and weight
      - visual test:
      - transition test:
    - back at the top of the screen select the *Ship By* (carrier and service) to use and click on 'Update Shipment'
      - visual test:
      - transition test:
    - use **Get Labels** near the top of the screen or the **Get Label** button for each package to get labels
      - visual test:
      - transition test:
    - check label data per package to make sure it is what was expected
      - visual test:
      - transition test:
    - print labels with the *Print Labels* dialog for configured printers or use the *Download Label* button for each package to get a PDF to print locally
      - visual test:
      - transition test:
- once finished with all inventory packing and issuing use the 'Set Shipped' button to update status
  - visual test:
  - transition test:
- note that once in the Shipped status the Transfer Shipment goes into a mode where it is ready to Receive
  - visual test:
  - transition test:

## Receive a Transfer Shipment

- when the Shipment physically arrives at the destination Facility look up the Shipment by ID or other
  - visual test:
  - transition test:
- the Shipment should be in the Shipped status
  - visual test:
  - transition test:
- use **Receive Product** to receive into inventory in the destination Facility
  - visual test:
  - transition test:
- once all receipt is complete use the 'Set Delivered' button to update Shipment status
  - visual test:
  - transition test:
- note that once a Shipment is in the Delivered status no additional items may be received but existing receipts may be updated
  - visual test:
  - transition test:
