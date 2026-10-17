# OAGIS Order to Cash

Source: [Business Process Library/OAGIS Order to Cash](https://moqui.org/docs/mantle/Business%20Process%20Library/OAGIS%20Order%20to%20Cash)

Type: Business-process description; verify UI applicability.

NOTE: These pages describe OAGIS document-exchange scenarios. The `mantle-oagis` component is listed in addons.xml with no releases and is not required to run Moqui, Mantle USL, or Marble ERP.
- visual test:
- transition test:

## Introduction

This process covers Customer and Supplier processes from Order through Cash plus Quotes and GL.
- visual test:
- transition test:

## OAGIS Scenarios

### Incorporated Scenarios

* 1 - General Ledger to Sub Ledgers
  - visual test:
  - transition test:
* 5 - Order Management to Accounts Receivable and General Ledger
  - visual test:
  - transition test:
* 7 - Purchasing to Accounts Payable to General Ledger
  - visual test:
  - transition test:
* 8 - Purchasing to Accounts Payable to General Ledger Posting from Purchasing
  - visual test:
  - transition test:
* 12 - Basic Purchase Order Process
  - visual test:
  - transition test:
* 25 - Invoice Matching, Matching in Accounts Payable
  - visual test:
  - transition test:
* 27 - Sales Force Automation to Order Management, Updating Orders
  - visual test:
  - transition test:
* 28 - Sales Force Automation to Order Management, Inquiry of Orders
  - visual test:
  - transition test:
* 29 - Sales Force Automation to Order Management and Shipping
  - visual test:
  - transition test:
* 30 - Supply Chain Integration
  - visual test:
  - transition test:
* 37 - Catalog and Price List Exchange
  - visual test:
  - transition test:
* 39 - Request for Quote and Quote Exchange
  - visual test:
  - transition test:
* 47 - Full Cycle Purchasing
  - visual test:
  - transition test:
* 53 - Inventory Visibility
  - visual test:
  - transition test:
* 54 - Mid Market Order to Cash Procure to Pay
  - visual test:
  - transition test:
* 55 - High Tech Procure to Pay
  - visual test:
  - transition test:
* 56 - High Tech Invoicing
  - visual test:
  - transition test:
* 58 - Metals Industry Order to Cash Procure to Pay
  - visual test:
  - transition test:
* 59 - High Tech Logistics - Direct Ship Model
  - visual test:
  - transition test:
* 60 - High Tech Logistics - Standard VMI With Outsourced - Customer Agent
  - visual test:
  - transition test:
* 61 - High Tech Logistics - Customer Operated Hub
  - visual test:
  - transition test:

### Related Scenarios

* 3 - Order Management to Accounts Receivable
  - visual test:
  - transition test:
* 4 - Order Management to Credit Management to Accounts Receivable
  - visual test:
  - transition test:
* 14 - Plant Data Collection / Warehouse Management / Issues
  - visual test:
  - transition test:
* 15 - Plant Data Collection / Warehouse Management / Transfers
  - visual test:
  - transition test:
* 19 - Plant Data Collection / Warehouse Management / Shipping
  - visual test:
  - transition test:
* 21 - Manufacturing to Purchasing (Requisitions, Purchasing, Inspection, Receiving, MRP)
  - visual test:
  - transition test:
* 22 - Manufacturing with Available to Promise to Order Management
  - visual test:
  - transition test:
* 23 - Manufacturing to Order Management Financials with Manufacturing for Engineer to Order and Configure to Order (Engineering - BOM, Inventory - Finished Goods, Order Management, Manufacturing, Inventory - Work In Progress, GL, Costing, AR)
  - visual test:
  - transition test:
* 31 - Customer Service Integration, Field Service, No Returns
  - visual test:
  - transition test:
* 48 - Sales Lead
  - visual test:
  - transition test:
* 49 - Sales Opportunity
  - visual test:
  - transition test:

## Actors

* Customer - purchase product from Supplier
  - visual test:
  - transition test:
* Supplier - sells product to Customer
  - visual test:
  - transition test:
* Carrier - transports product from Supplier to Customer
  - visual test:
  - transition test:
* Organization - general organization, may be Customer or Supplier or other
  - visual test:
  - transition test:

## Process Story

### Catalog

Supplier Catalog Management sends SyncCatalog to Supplier Order Management and Purchasing, and each sends ConfirmBOD to Catalog.
Catalog sends SyncPriceList to OM and Purchasing, and each sends ConfirmBOD to Catalog.
Inventory sends SyncItemMaster to OM, Catalog, and Purchasing and each sends ConfirmBOD to Inventory.
- visual test:
- transition test:

Customer sends GetCatalog to Supplier and Supplier sends ShowCatalog to Customer (alternatively Supplier Sync and Customer Confirm).
Customer sends GetPriceList to Supplier and Supplier sends ShowPriceList to Customer (alternatively Supplier Sync and Customer Confirm).
- visual test:
- transition test:

Customer sends GetInventoryBalance to Supplier and Supplier sends ShowInventoryBalance to Customer.
Alternatively, Supplier sends SyncInventoryBalance to Customer and Customer sends ConfirmBOD to Supplier (and optionally vice-versa).
- visual test:
- transition test:

### Quote

Customer sends ProcessRFQ to Supplier and Supplier sends AcknowledgeRFQ to Customer.
To change a RFQ, Customer sends ChangeRFQ to Supplier and Supplier sends RespondRFQ to Customer.
To get RFQ details, Supplier sends GetRFQ to Customer and Customer sends ShowRFQ to Supplier.
To cancel an RFQ, Customer sends CancelRFQ to Supplier and Supplier sends ConfirmBOD to Customer.
- visual test:
- transition test:

Supplier sends ProcessQuote to Customer and Customer sends AcknowledgeQuote to Supplier.
To change a quote, Supplier sends ChangeQuote to Customer and Customer sends RespondQuote to Supplier.
To get quote details, Customer sends GetQuote to Supplier and Supplier sends ShowQuote to Customer.
To cancel a quote, Supplier sends CancelQuote to Customer and Customer sends ConfirmBOD to Supplier.
- visual test:
- transition test:

### Order

Customer sends ProcessPurchaseOrder to Supplier (supplier internally creates SalesOrder) and Supplier sends AcknowledgePurchaseOrder to Customer.
To change a purchase order Customer sends ChangePurchaseOrder to Supplier and Supplier sends RespondPurchaseOrder to Customer.
To cancel a purchase order Customer sends CancelPurchaseOrder to Supplier and Supplier sends ConfirmBOD to Customer.
To get purchase order info Supplier sends GetPurchaseOrder to Customer and Customer sends ShowPurchaseOrder to Supplier.
- visual test:
- transition test:

Supplier Sales sends SyncPurchaseOrder to Supplier Order Management.
Supplier Order Management sends SyncPurchaseOrder to Manufacturing, Shipping, and/or Billing and each sends ConfirmBOD to OM.
- visual test:
- transition test:

For separate internal Sales/SFA within Supplier:
Sales (SFA) sends ProcessSalesOrder to Order Management and OM sends AcknowledgeSalesOrder to Sales.
To change a sales order Sales sends ChangeSalesOrder to OM and OM sends RespondSalesOrder to Sales.
To cancel a sales order Sales sends CancelSalesOrder to OM and OM sends ConfirmBOD to Sales.
To get sales order info OM sends GetSalesOrder to Sales and Sales sends ShowSalesOrder to OM.
If Supplier has separate Manufacturing, Shipping, or Billing (or Dispatch, Weight Bridge) Supplier OM sends SyncSalesOrder to each and each sends ConfirmBOD to OM.
- visual test:
- transition test:

### Shipping

Customer sends ProcessPlanningSchedule to Supplier and Supplier sends AcknowledgePlanningSchedule to Customer.
- visual test:
- transition test:

(pick/pack) Supplier Manufacturing sends UpdatePickList to Supplier Shipping and Supplier Shipping sends RespondPickList to Supplier Manufacturing.
Supplier Shipping sends PostJournalEntry to Supplier GL and GL sends PostAcknowledgeJournalEntry to Shipping.
- visual test:
- transition test:

(carrier) Supplier sends ProcessShipment to Carrier and Carrier sends AcknowledgeShipment to Supplier.
Supplier sends ProcessCommercialInvoice, NotifyShippersLetterOfInstruction, NotifyExportDeclaration, and NotifyHazardousMaterialShipmentDocument to Carrier (as needed) and Carrier sends ConfirmBOD to Supplier.
- visual test:
- transition test:

Carrier picks up shipment from Supplier.
- visual test:
- transition test:

Supplier sends NotifyShipment to Customer and Customer sends ConfirmBOD to Supplier.
Supplier sends NotifyShipment to Carrier and Carrier sends ConfirmBOD to Supplier.
- visual test:
- transition test:

Carrier delivers shipment to Customer.
- visual test:
- transition test:

Carrier sends NotifyShipmentUnit to Supplier and Customer, and each send ConfirmBOD to Carrier.
Carrier sends ProcessInvoice (for freight) to Supplier and/or Customer, and Supplier and/or Customer send AcknowledgeInvoice to Carrier.
Carrier sends NotifyReceiveDelivery to Supplier and Supplier sends ConfirmBOD to Carrier.
- visual test:
- transition test:

Customer sends NotifyReceiveDelivery to Supplier and Supplier sends ConfirmBOD to Customer.
- visual test:
- transition test:

### Supplier AR

Supplier AR sends ProcessInvoice to Customer AP and Customer AP sends AcknowledgeInvoice to Supplier.
- visual test:
- transition test:

Supplier Billing sends PostJournalEntry to Supplier General Ledger and GL sends PostAcknowledgeJournalEntry to Billing.
Alternatively, Supplier Billing sends LoadReceivable to Supplier AR and AR sends ConfirmBOD to Billing, then Supplier AR sends PostJournalEntry to Supplier GL and GL sends PostAcknowledgeJournalEntry to AR.
Alternatively, Supplier Order Management sends LoadReceivable to Supplier AR and AR sends ConfirmBOD to OM, then AR sends PostJournalEntry to GL and GL sends PostAcknowledgeJournalEntry to AR.
- visual test:
- transition test:

### Customer AP

Customer Purchasing sends SyncPartyMaster to AP and AP sends ConfirmBOD to Purchasing (and vice-versa to keep in sync).
- visual test:
- transition test:

Customer Purchasing sends LoadPayable to AP and AP sends ConfirmBOD to Purchasing. AP or Purchasing sends PostJournalEntry to GL and GL sends ConfirmBOD back.
- visual test:
- transition test:

Customer sends NotifyRemittanceAdvice to Supplier and Supplier sends ConfirmBOD to Customer.
- visual test:
- transition test:

### Sub-Ledger

If Organization has separate General Ledger and Sub-Ledger(s), Organization GL sends SyncChartOfAccounts to Sub-Ledger and SL sends
ConfirmBOD to GL. SL sends PostJournalEntry to GL and GL sends PostAcknowledgeJournalEntry to SL.
- visual test:
- transition test:

## Simple Order to Cash Scenario

Customer sends ProcessPurchaseOrder to Supplier (supplier internally creates SalesOrder) and Supplier sends AcknowledgePurchaseOrder to Customer.
- visual test:
- transition test:

Supplier sends NotifyShipment to Customer and Customer sends ConfirmBOD to Supplier. TODO: NotifyBOM?
- visual test:
- transition test:

Customer optionally sends NotifyReceiveDelivery to Supplier and Supplier sends ConfirmBOD to Customer.
- visual test:
- transition test:

Supplier sends ProcessInvoice to Customer and Customer sends AcknowledgeInvoice to Supplier.
- visual test:
- transition test:

Customer sends NotifyRemittanceAdvice to Supplier and Supplier sends ConfirmBOD to Customer.
- visual test:
- transition test:

## OAGIS Documents Used

### Party
* SyncPartyMaster - ConfirmBOD
  - visual test:
  - transition test:

### Catalog and Inventory
* SyncCatalog - ConfirmBOD
  - visual test:
  - transition test:
* SyncPriceList - ConfirmBOD
  - visual test:
  - transition test:
* SyncItemMaster - ConfirmBOD
  - visual test:
  - transition test:
* GetCatalog - ShowCatalog
  - visual test:
  - transition test:
* SyncInventoryBalance - ConfirmBOD
  - visual test:
  - transition test:

### RFQ and Quote
* ProcessRFQ - AcknowledgeRFQ
  - visual test:
  - transition test:
* ChangeRFQ - RespondRFQ
  - visual test:
  - transition test:
* GetRFQ - ShowRFQ
  - visual test:
  - transition test:
* CancelRFQ - ConfirmBOD
  - visual test:
  - transition test:
* ProcessQuote - AcknowledgeQuote
  - visual test:
  - transition test:
* ChangeQuote - RespondQuote
  - visual test:
  - transition test:
* GetQuote - ShowQuote
  - visual test:
  - transition test:
* CancelQuote - ConfirmBOD
  - visual test:
  - transition test:

### Purchase Order
* ProcessPurchaseOrder - AcknowledgePurchaseOrder
  - visual test:
  - transition test:
* ChangePurchaseOrder - RespondPurchaseOrder
  - visual test:
  - transition test:
* CancelPurchaseOrder - ConfirmBOD
  - visual test:
  - transition test:
* GetPurchaseOrder - ShowPurchaseOrder
  - visual test:
  - transition test:
* SyncPurchaseOrder - ConfirmBOD
  - visual test:
  - transition test:

### Sales Order
* ProcessSalesOrder - AcknowledgeSalesOrder
  - visual test:
  - transition test:
* ChangeSalesOrder - RespondSalesOrder
  - visual test:
  - transition test:
* CancelSalesOrder - ConfirmBOD
  - visual test:
  - transition test:
* GetSalesOrder - ShowSalesOrder
  - visual test:
  - transition test:
* SyncSalesOrder - ConfirmBOD
  - visual test:
  - transition test:

### Shipping
* ProcessPlanningSchedule - AcknowledgePlanningSchedule
  - visual test:
  - transition test:
* UpdatePickList - RespondPickList
  - visual test:
  - transition test:
* ProcessShipment - AcknowledgeShipment
  - visual test:
  - transition test:
* ProcessCommercialInvoice, NotifyShippersLetterOfInstruction, NotifyExportDeclaration, NotifyHazardousMaterialShipmentDocument - ConfirmBOD
  - visual test:
  - transition test:
* NotifyShipment - ConfirmBOD
  - visual test:
  - transition test:
* NotifyShipmentUnit - ConfirmBOD
  - visual test:
  - transition test:
* NotifyReceiveDelivery (aka NotifyDeliveryReceipt?) - ConfirmBOD
  - visual test:
  - transition test:

### AR, Invoice, AP, Payment
* LoadReceivable - ConfirmBOD
  - visual test:
  - transition test:
* ProcessInvoice - AcknowledgeInvoice
  - visual test:
  - transition test:
* LoadPayable - ConfirmBOD
  - visual test:
  - transition test:
* NotifyRemittanceAdvice - ConfirmBOD
  - visual test:
  - transition test:

### Ledger
* PostJournalEntry - PostAcknowledgeJournalEntry
  - visual test:
  - transition test:
* SyncChartOfAccounts - ConfirmBOD
  - visual test:
  - transition test:

## Initial Documents to Support

* ProcessPurchaseOrder - AcknowledgePurchaseOrder
  - visual test:
  - transition test:
* NotifyShipment - ConfirmBOD
  - visual test:
  - transition test:
* ProcessInvoice - AcknowledgeInvoice
  - visual test:
  - transition test:
* NotifyRemittanceAdvice - ConfirmBOD
  - visual test:
  - transition test:
