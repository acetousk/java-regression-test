# Find and Create Customer

Source: [Marble ERP User Guide/Order to Cash/Find and Create Customer](https://moqui.org/docs/apps/Marble%20ERP%20User%20Guide/Order%20to%20Cash/Find%20and%20Create%20Customer)

Type: UI walkthrough.

## Introduction and Definitions

A customer is a **Party** (*Person or Organization*) with the **Customer** role. While a customer Party may also be in other roles it must have the **Customer** role to show up in searches on the Find Customer screen and the Customer drop-down in the Create Sales Order form.
- visual test:
- transition test:

Sales Account and Sales Contact are special types of customer to handle customers who are organizations with individuals who do purchasing, billing, and other activities on behalf of that organization. A Sales Account is a Party with the **Customer** and **Sales Account** roles. A Sales Contact does not need the **Customer** role if they won't be the direct customer on a sales order, but they will have the **Sales Contact** role. A Sales Contact is associated with a Sales Account with a 'Contact' type relationship record that can be used to specify a role for the Contact such as Buyer, Accountant, Inventory Manager, etc. A Sales Account may have a parent Sales Account to manage larger organizations with different divisions or departments that purchase directly.
- visual test:
- transition test:

The first step for a Sales Order is generally to find or create a Customer record. This can be as simple as typing in customer information in the drop-down in the Create Sales Order dialog if you know the customer is already in the system and you have some identifying information. A more flexible flow is to start on the Find Customer screen, find or create a customer record, and then from the Edit Customer screen use the Sales Orders link to go to the Find Orders screen where the Customer field will now be populated in the Create Sales Order dialog.
- visual test:
- transition test:

Note that while a customer record must exist before a customer can be set on a Sales Order you don't have to add payment or shipping address information in advance, those can be added on the Order Detail screen.
- visual test:
- transition test:

## Find Customer

TODO
- visual test:
- transition test:

## Create Individual Customer

TODO
- visual test:
- transition test:

## Create Sales Account

TODO
- visual test:
- transition test:

## Create Sales Contact

TODO
- visual test:
- transition test:

## Convert Existing Customer to Sales Account or Contact

TODO
- visual test:
- transition test:
