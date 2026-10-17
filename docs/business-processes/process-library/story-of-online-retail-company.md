# Story of Online Retail Company

Source: [Business Process Library/Story of Online Retail Company](https://moqui.org/docs/mantle/Business%20Process%20Library/Story%20of%20Online%20Retail%20Company)

Type: Business-process description; verify UI applicability.

Someone decides to sell a product. [Product Marketer Maintains Product Information](https://moqui.org/docs/mantle/Business%20Process%20Library/Product%20Marketer%20Maintains%20Product%20Information). 
[Buyer Places Purchase Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Buyer%20Places%20Purchase%20Order). [Marketer Maintains General Site Content](https://moqui.org/docs/mantle/Business%20Process%20Library/Marketer%20Maintains%20General%20Site%20Content).
- visual test:
- transition test:

When new inventory is needed [Buyer Places Purchase Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Buyer%20Places%20Purchase%20Order). 
When shipments arrive [Shipment Receiver Receives Shipment](https://moqui.org/docs/mantle/Business%20Process%20Library/Shipment%20Receiver%20Receives%20Shipment), then [Inventory Mover Puts Away Inventory](https://moqui.org/docs/mantle/Business%20Process%20Library/Inventory%20Mover%20Puts%20Away%20Inventory).
- visual test:
- transition test:

[Customer Finds Product](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Finds%20Product). [Placing Customer Adds Product to Cart](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Adds%20Product%20to%20Cart) 
and [Placing Customer Places a Sales Order - Online Checkout](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Places%20a%20Sales%20Order%20-%20Online%20Checkout). 
Alternatively [Placing Customer Places a Sales Order - Through CSR](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Places%20a%20Sales%20Order%20-%20Through%20CSR) 
or [Placing Customer Places a Sales Order - Through eBay](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Places%20a%20Sales%20Order%20-%20Through%20EBay).
If Customer decides to, [Customer Cancels Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Cancels%20Order).
- visual test:
- transition test:

If desired during checkout or for other reasons, [Customer Creates and Edits Account](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Creates%20and%20Edits%20Account). 
As desired [Customer Reviews Order History and Status](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Reviews%20Order%20History%20and%20Status).
- visual test:
- transition test:

Once order is ready [Company Approves Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Approves%20Sales%20Order).
- visual test:
- transition test:

When inventory is not sufficient in a pick location [Inventory Mover does Stock Move](https://moqui.org/docs/mantle/Business%20Process%20Library/Inventory%20Mover%20does%20Stock%20Move). 
[Company Fulfills Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Fulfills%20Sales%20Order). [Accountant Sends Invoice and Receives Payment](https://moqui.org/docs/mantle/Business%20Process%20Library/Accountant%20Sends%20Invoice%20and%20Receives%20Payment). 
Sometimes special cases come up, like [Carrier Does Not Deliver Shipment to Customer](https://moqui.org/docs/mantle/Business%20Process%20Library/Carrier%20Does%20Not%20Deliver%20Shipment%20to%20Customer) 
and [Carrier Returns Undeliverable Shipment to Company](https://moqui.org/docs/mantle/Business%20Process%20Library/Carrier%20Returns%20Undeliverable%20Shipment%20to%20Company).
- visual test:
- transition test:

[Customer Returns Product](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Returns%20Product). [Company Processes Return Received](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Processes%20Return%20Received).
- visual test:
- transition test:
