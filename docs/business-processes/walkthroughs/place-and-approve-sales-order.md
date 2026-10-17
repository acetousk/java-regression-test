# Place and Approve Sales Order

Source: [Marble ERP User Guide/Order to Cash/Place and Approve Sales Order](https://moqui.org/docs/apps/Marble%20ERP%20User%20Guide/Order%20to%20Cash/Place%20and%20Approve%20Sales%20Order)

Type: UI walkthrough.

## Find or Create a Customer

- from the [Marble ERP dashboard](https://demo.moqui.org/qapps/marble/dashboard)
  - visual test:
  - transition test:
- the links for sales are in the **Customers** column on the left; the three columns are arranged by Party role (Customers, Internal, Suppliers)
  - visual test:
  - transition test:
- click on the **Customers** link; like many others this link goes to a find screen with dialogs to create
  - visual test:
  - transition test:
- search for or select a customer, or use the **New Person Customer** dialog to create a new one
  - visual test:
  - transition test:
- for new organization/company customers use the **New Sales Account (Organization Customer)** dialog and then use the **New Sales Contact** dialog for the individuals who are contacts at the company; the terms Sales Account and Sales Contact are from common Sales Force Automation (SFA) terminology
  - visual test:
  - transition test:

## Create a Sales Order

- from the *Find Customer* screen use the **Sales Orders** button, or from the *Edit Customer* screen use the **Orders** button; this takes you to the *Find Orders* screen showing orders for just that customer, and selects the Customer in the **Create Sales Order** dialog
  - visual test:
  - transition test:
- alternatively from the dashboard click on **Sales Orders & Quotes** to go to the *Find Orders* screen (and only show sales orders)
  - visual test:
  - transition test:
- click on **Create Sales Order** and in the dialog:
    - visual test:
    - transition test:
    - select the desired *Store* which will populate the *Vendor* and *Facility* fields based on Store settings, or alternatively just specify a *Vendor* Party and *Facility* to ship from
      - visual test:
      - transition test:
    - select a *Customer* or leave as is if one pre-selected from a parameter to the screen
      - visual test:
      - transition test:
    - specify other values as needed and submit the form to go to the *Order Detail* screen
      - visual test:
      - transition test:
- the *Order Detail* screen has a section at the top for the Order Header, and for each Order Part there is a part header section with a grey background and a part items section in a table below it
  - visual test:
  - transition test:

## Add Product and Other Items to the Order

- use the **Add Product Item** dialog or **Quick Add Items** screen to add products to the order
  - visual test:
  - transition test:
- use the **Add Other Item** dialog to add non-product items for discounts, taxes, shipping and other charges, etc
  - visual test:
  - transition test:
- note that if a Store has active promotions and shipping rate calculation, adjustment items will be added automatically for those based on calculated amounts
  - visual test:
  - transition test:

## Set Shipping, Payment, and Other options

- on the *Order Detail* screen in the *Part Header* section select an address and shipment method then click on **Set Shipping Address and Info**
  - visual test:
  - transition test:
- change any other Order Part settings in the **Edit Part {seq}** dialog
  - visual test:
  - transition test:
- use the **Add Party** dialog to add other parties in other roles to the order part
    - visual test:
    - transition test:
    - to send Invoice(s) to a different Party use the *Customer - Bill To* role
      - visual test:
      - transition test:
    - to ship to a different Party use the *Customer - Ship To* role, this will allow you to select a shipping address from this Party
      - visual test:
      - transition test:
    - other roles may be used such as *Affiliate*, *Sales Rep*, etc that are configured as roles applicable to orders
      - visual test:
      - transition test:
- use the **Add Payment** dialog to record info about how the order will be paid
    - visual test:
    - transition test:
    - select either a *Payment Method*, *Customer Account*, OR *Instrument* (generally just one of the three)
      - visual test:
      - transition test:
- note that if there is a single Payment its amount will be updated automatically as the order changes; if there are multiple Payments (split payment) then as the order total changes from product, charges, etc. items they will need to be updated manually
  - visual test:
  - transition test:

## Place and Approve the Order

- place the order with the **Place** button; there are validations that run automatically on the order and if any of these fail there will be a **Place Warnings** button that opens a dialog showing the warnings and a button to **Place Order Anyway**
  - visual test:
  - transition test:
- when an order is placed there are *Order Pre-Approve* validations automatically run and if all of these pass the order will be approved automatically (including authorized payments which means that if a payment method or instrument is chosen that can't be authorized you will always get a Pre-Approve warning)
  - visual test:
  - transition test:
- if any fail there will be a **Approve Warnings** button that shows a dialog with the warnings and a button to **Approve Order Anyway**
  - visual test:
  - transition test:
- once an order is Approved a button will appear in each *Order Part* section to **Create Shipment** for that Order Part; for a simple flow (not using Shipping screens for pick, pack, etc.) this is the first step to fulfill an order
  - visual test:
  - transition test:
