// Steps shared by the processes that follow a sales order. The CSR's steps from
// walkthroughs/place-and-approve-sales-order.md give an approved order of one DEMO_1_1 for demo customer Joe Q Public,
// paid by the card on file or by another instrument; the shipper's from walkthroughs/ship-sales-order.md ship it.
const { expect } = require('@playwright/test');
const { button, choose, openDialog, sameId, selectId, submitTo, urlParam } = require('./process-helpers');

const orderDetail = /\/marble\/Order\/OrderDetail\?/;

const shipmentDetail = /\/marble\/Shipment\/ShipmentDetail\?/;

const payByCard = {
  name: 'pay with the card on file',
  writes: true,
  run: async page => {
    const form = await openDialog(page, 'Add Payment', 'AddPaymentInfo');
    await choose(page, await selectId(form, 'paymentMethodId'), '1111');
    await submitTo(page, form.locator('[type="submit"]'), orderDetail);
    await expect(page.getByText('1111').filter({ visible: true }).first()).toBeVisible();
  },
};

/** A payment by an instrument with no payment method, such as `Personal Check`, which the customer sends later. */
function payByInstrument(instrument) {
  return {
    name: `pay by ${instrument}`,
    writes: true,
    run: async page => {
      const form = await openDialog(page, 'Add Payment', 'AddPaymentInfo');
      await choose(page, await selectId(form, 'paymentInstrumentEnumId'), instrument);
      await submitTo(page, form.locator('[type="submit"]'), orderDetail);
      await expect(page.getByText(instrument).filter({ visible: true }).first()).toBeVisible();
    },
  };
}

/** Add `quantity` of `productId` with the Order Detail's Add Product Item dialog. */
function addProduct(productId, quantity) {
  return {
    name: `add ${quantity === 1 ? 'one' : quantity} ${productId}`,
    writes: true,
    run: async page => {
      const form = await openDialog(page, 'Add Product Item', 'AddProductItemContainer');
      await choose(page, await selectId(form, 'productId'), productId, productId);
      await form.locator('[name="quantity"]').fill(String(quantity));
      await submitTo(page, form.locator('[type="submit"]'), orderDetail);
      await expect(page.getByText(productId).filter({ visible: true }).first()).toBeVisible();
    },
  };
}

const placeOrder = {
  name: 'place the order',
  writes: true,
  run: async page => {
    const warnings = button(page, 'Place Warnings');
    if (await warnings.isVisible()) {
      await warnings.click();
      await submitTo(page, button(page, 'Place Order Anyway'), orderDetail);
    } else {
      await submitTo(page, button(page, 'Place'), orderDetail);
    }
    await expect(page.getByText('Placed').filter({ visible: true }).first()).toBeVisible();
  },
};

const approveOrder = {
  name: 'approve the order',
  writes: true,
  run: async page => {
    const warnings = button(page, 'Approve Warnings');
    if (await warnings.isVisible()) {
      await warnings.click();
      await submitTo(page, button(page, 'Approve Order Anyway'), orderDetail);
    } else {
      await submitTo(page, button(page, 'Approve'), orderDetail);
    }
    await expect(page.getByText('Approved').filter({ visible: true }).first()).toBeVisible();
  },
};

/** Place and approve an order paid by the `payment` step. */
const placeAndApproveOrderPaidBy = payment => [
  {
    name: 'open Sales Orders from the dashboard',
    run: async page => {
      await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
      await submitTo(page, page.getByRole('link', { name: /Sales\s+Orders/ }).first(), /\/marble\/Order\/FindOrder/);
      await expect(button(page, 'Create Sales Order')).toBeVisible();
    },
  },
  {
    name: 'open the Create Sales Order dialog',
    run: async page => {
      await openDialog(page, 'Create Sales Order', 'CreateSalesOrderDialog');
    },
  },
  {
    name: 'choose the store and the customer and click Create',
    writes: true,
    run: async page => {
      const form = page.locator('#CreateSalesOrderDialog form');
      // The store fills in its vendor and warehouse; without a facility the order cannot be placed.
      await choose(page, 'CreateSalesOrder_productStoreId', 'POPC_DEFAULT: Ziziwork Retail Store');
      await expect(page.locator('#CreateSalesOrder_facilityId')).not.toHaveValue('', { timeout: 30000 });
      await choose(page, 'CreateSalesOrder_customerPartyId', 'CustJqp: Joe Public', 'Joe');
      await submitTo(page, form.locator('[type="submit"]'), orderDetail);
      await expect(page.getByText('Joe Public').filter({ visible: true }).first()).toBeVisible();
      return urlParam(page, 'orderId');
    },
    verify: sameId('orderId'),
  },
  addProduct('DEMO_1_1', 1),
  payment,
  {
    name: 'set the shipping address and method',
    writes: true,
    run: async page => {
      const form = page.locator('form#SetOrderInfoForm_0');
      await choose(page, 'SetOrderInfoForm_0_shippingPostalContactMechId_0', '1350 E. Flamingo');
      await choose(page, 'SetOrderInfoForm_0_carrierAndShipmentMethod_0', 'Ground');
      await submitTo(page, form.locator('[type="submit"]'), orderDetail);
      await expect(page.getByText('No shipping address selected').filter({ visible: true })).toHaveCount(0);
      await expect(page.getByText('No shipment method selected').filter({ visible: true })).toHaveCount(0);
    },
  },
  placeOrder,
  approveOrder,
];
const placeAndApproveOrder = placeAndApproveOrderPaidBy(payByCard);

/** The status shown in the Shipment Detail header form. */
async function expectShipmentStatus(page, status) {
  await expect(page.getByText(status, { exact: true }).filter({ visible: true }).first()).toBeVisible();
}

/** From an approved order's Order Detail: create its shipment, schedule it, issue and pack the item, pack, ship. */
const shipOrder = [
  {
    name: 'create a shipment for the order part',
    writes: true,
    run: async page => {
      await submitTo(page, button(page, 'Create Shipment'), orderDetail);
      await expect(page.getByRole('link', { name: /Shipment\s+\d+/ }).filter({ visible: true }).first()).toBeVisible();
    },
  },
  {
    name: 'open the shipment',
    run: async page => {
      await submitTo(page, page.getByRole('link', { name: /Shipment\s+\d+/ }).filter({ visible: true }).first(),
        shipmentDetail);
      await expect(button(page, 'Set Scheduled')).toBeVisible();
      return urlParam(page, 'shipmentId');
    },
    verify: sameId('shipmentId'),
  },
  {
    name: 'set the shipment scheduled',
    writes: true,
    run: async page => {
      await submitTo(page, button(page, 'Set Scheduled'), shipmentDetail);
      await expectShipmentStatus(page, 'Scheduled');
    },
  },
  {
    name: 'issue and pack the reserved item',
    writes: true,
    run: async page => {
      await submitTo(page, button(page, 'Issue & Pack'), shipmentDetail);
      await expect(button(page, 'Set Packed')).toBeVisible();
    },
  },
  {
    name: 'set the shipment packed',
    writes: true,
    run: async page => {
      const form = await openDialog(page, 'Set Packed', 'SetPackedDialog');
      await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
      await expectShipmentStatus(page, 'Packed');
    },
  },
  {
    name: 'set the shipment shipped',
    writes: true,
    run: async page => {
      const form = await openDialog(page, 'Set Shipped', 'SetShippedDialog');
      await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
      await expectShipmentStatus(page, 'Shipped');
      // The status history and actual start are dates as Java shows them, not epoch millis.
      await expect(page.locator('body')).not.toContainText(/\b\d{13}\b/);
    },
  },
];

module.exports = {
  addProduct, approveOrder, expectShipmentStatus, orderDetail, placeOrder, payByInstrument, placeAndApproveOrder, placeAndApproveOrderPaidBy, shipmentDetail, shipOrder,
};
