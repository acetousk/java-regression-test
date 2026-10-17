# Company Approves Sales Order

Source: [Business Process Library/Company Approves Sales Order](https://moqui.org/docs/mantle/Business%20Process%20Library/Company%20Approves%20Sales%20Order)

Type: Business-process description; verify UI applicability.

## Ideas to Incorporate

* Special case statuses and manual approval
  - visual test:
  - transition test:

## Story

Sales Orders are approved automatically when paid by credit card and CC authorization is successful.
- visual test:
- transition test:

Sales Orders are placed in Pending approval status after checkout then auto-approve once a third-party payment processor (PayPal, etc.) sends notification.
- visual test:
- transition test:

Sales Orders are placed in Rejected status when authorization fails.
- visual test:
- transition test:

Once order is approved Company reserves inventory for approved order, reducing Available To Promise (ATP) quantity. If inventory is not available negative inventory reservations are created and the order is placed on back-order.
- visual test:
- transition test:

Company sends confirmation email to the Placing Customer.
- visual test:
- transition test:
