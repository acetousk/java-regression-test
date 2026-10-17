# Placing Customer Places a Sales Order - Through EBay

Source: [Business Process Library/Placing Customer Places a Sales Order - Through EBay](https://moqui.org/docs/mantle/Business%20Process%20Library/Placing%20Customer%20Places%20a%20Sales%20Order%20-%20Through%20EBay)

Type: Business-process description; verify UI applicability.

NOTE: This story is historical. There is no eBay integration component in the current Moqui add-ons, and this process is not implemented as a Moqui add-on.
- visual test:
- transition test:

## Ideas to Incorporate

## Story

eBay Marketer selects products to add to eBay Store and automatically sends them to eBay. eBay Marketer allocates inventory to warehouse for eBay auctions. eBay Marketer creates eBay Auctions from listings in the eBay Store.
- visual test:
- transition test:

Placing Customer places an order through eBay Store, or places the highest bid in an eBay Auction.
- visual test:
- transition test:

eBay Marketer imports eBay orders (auctions and store orders) to get paid orders by specifying begin/end time, views orders placed in that time, and then selects orders to import. eBay Marketer reviews imported orders and manually approves them, mainly making sure orders match the orders in eBay. If Placing Customer orders multiple items they will come in as separate orders and eBay Marketer will combine the orders into a single order.
- visual test:
- transition test:

For credit card payment the order is placed on eBay and Placing Customer calls eBay Marketer and gives CC#. eBay Marketer either enters entire order including payment information manually, or finds the order already imported from eBay and adds payment information to the order, and then authorizes the payment.
- visual test:
- transition test:

If Customer sends money via PayPal and skips ordering on eBay, eBay Marketer manually creates an order. When order is complete eBay Marketer marks as shipped in PayPal.
- visual test:
- transition test:

Once items are shipped Company automatically sends message to eBay and sends standard ship notification email.
- visual test:
- transition test:

On returns order is returned as normal, and then eBay Marketer manually marks order as returned in eBay and if application refunds payment in PayPal, and if PayPal was not used manually refunds credit card or other payment.
- visual test:
- transition test:
