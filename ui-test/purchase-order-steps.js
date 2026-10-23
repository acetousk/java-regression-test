// Steps shared by the processes that follow a purchase order. The buyer's steps from
// process-library/buyer-places-purchase-order.md give an approved order of 10 DEMO_1_1 from demo supplier
// Ziddleman & Sons for the Ziziwork Retail warehouse; the receiver's from shipment-receiver-receives-shipment.md
// receive it.
const { expect } = require('@playwright/test');
const { button, choose, openDialog, sameId, submitTo, urlParam } = require('./process-helpers');
const { addProduct, approveOrder, expectShipmentStatus, orderDetail, placeOrder, shipOrder, shipmentDetail } =
  require('./sales-order-steps');

const placeAndApprovePurchaseOrder = [
  {
    name: 'open Purchase Orders from the dashboard',
    run: async page => {
      await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
      await submitTo(page, page.getByRole('link', { name: /Purchase\s+Orders/ }).first(),
        /\/marble\/Order\/FindOrder\?.*orderType=Purchase/);
      await expect(button(page, 'Create Purchase Order')).toBeVisible();
    },
  },
  {
    name: 'open the Create Purchase Order dialog',
    run: async page => {
      await openDialog(page, 'Create Purchase Order', 'CreatePurchaseOrderDialog');
    },
  },
  {
    name: 'choose the supplier, the organization and the warehouse and click Create',
    writes: true,
    run: async page => {
      const form = page.locator('#CreatePurchaseOrderDialog form');
      await choose(page, 'CreatePurchaseOrder_vendorPartyId', 'Ziddleman', 'Ziddleman');
      await choose(page, 'CreatePurchaseOrder_customerPartyId', 'Ziziwork Retail');
      await choose(page, 'CreatePurchaseOrder_facilityId', 'Ziziwork Retail Warehouse', 'Ziziwork Retail');
      await submitTo(page, form.locator('[type="submit"]'), orderDetail);
      await expect(page.getByText('Ziddleman').filter({ visible: true }).first()).toBeVisible();
      return urlParam(page, 'orderId');
    },
    verify: sameId('orderId'),
  },
  addProduct('DEMO_1_1', 10),
  placeOrder,
  approveOrder,
];

/** From an approved purchase order's Order Detail: create the incoming shipment, schedule it, receive it all. */
const receivePurchaseOrder = [
  ...shipOrder.slice(0, 3),
  {
    name: 'receive the entire shipment',
    writes: true,
    run: async page => {
      await submitTo(page, button(page, 'Receive Entire Shipment'), shipmentDetail);
      await expectShipmentStatus(page, 'Delivered');
    },
  },
];

module.exports = { placeAndApprovePurchaseOrder, receivePurchaseOrder };
