# Placing Customer Places a Sales Order - Online Checkout

Source: [Business Process Library/Placing Customer Places a Sales Order - Online Checkout](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Places%20a%20Sales%20Order%20-%20Online%20Checkout)

Type: Business-process description; verify UI applicability.

This story starts once Placing Customer has added products to a list in order to place a sales order. The interactions could take place through various mediums to send the information to the company, including internet, phone, fax, mail, or in-person.
- visual test:
- transition test:

Placing Customer (PLC for this story) reviews list of items to order and decides to place a sales order with that set of items.
PLC specifies general profile information including:
- visual test:
- transition test:

* first and last name (optionally middle initial or middle name, title, prefix, suffix)
  - visual test:
  - transition test:
* primary contact phone number (home, work, or mobile)
  - visual test:
  - transition test:
* primary contact email address
  - visual test:
  - transition test:
* shipping address (optionally multiple shipping addresses)
  - visual test:
  - transition test:
* preferred payment method, with billing address where applicable (optionally multiple payment method; includes credit cards, EFT accounts, etc)
  - visual test:
  - transition test:
* general preferences
  - visual test:
  - transition test:

If PLC wants to create an account to access order status and other information later on in an automated way, PLC selects a username and password that will be used for future authentication.
- visual test:
- transition test:

If PLC wants to split the order into multiple ship-groups for shipping to different destinations and/or shipping by different carriers or shipment methods, then PLC specifies ship groups desired and which quantity units of each item is associated with which ship-group.
- visual test:
- transition test:

PLC specifies order-specific information including:
- visual test:
- transition test:

* which shipping address to use for each ship-group (if more than one is on file)
  - visual test:
  - transition test:
* the shipment method and carrier (if PLC allowed to select the carrier) to use for each ship-group
  - visual test:
  - transition test:
* whether to ship the order all at once or as inventory is available
  - visual test:
  - transition test:
* the payment preference(s) for how to pay for the order, including payment methods associated with the PLC, financial accounts, or other payment method options not set up in advance (COD, offline pre-payment, etc.)
  - visual test:
  - transition test:
* if PLC has a billing account set up they can use whatever is left on the credit limit of that billing account to defer payment until the order is fulfilled (more specifically until each package related to the order is packed)
  - visual test:
  - transition test:

Company calculates additional adjustments such as a shipping cost estimate to be charged to Customer and the applicable taxes based on the items in the order and the shipping destination for each.
- visual test:
- transition test:

Company will communicate to Customer all order information including what PLC specified and what Company calculated based on that. If everything looks correct and according to what PLC wants and/or needs, PLC will finalize the order, officially placing it with Company.
- visual test:
- transition test:
