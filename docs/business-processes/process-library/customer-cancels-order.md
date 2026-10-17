# Customer Cancels Order

Source: [Business Process Library/Customer Cancels Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Customer%20Cancels%20Order)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

## Story

Customer sends email to request cancellation of an order. CSR reviews email, finds the order, and if it has not shipped (shipment packed) then records the order as cancelled. If payment has been received for the order Company automatically refunds the payment. If the order has shipped CSR replies to customer by email to notify that the item has been shipped and they are liable to pay.
- visual test:
- transition test:

Customer reviews order online and if any of it has not been shipped a cancel button will be available for the entire order and each item that has not shipped. Customer cancels entire order or individual item. Company automatically changes status, cancels inventory reservation(s), and if payment has been received then refunds payment.
- visual test:
- transition test:
