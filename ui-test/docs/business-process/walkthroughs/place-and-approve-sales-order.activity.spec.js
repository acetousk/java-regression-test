// Step 5 activity: "Place and Approve Sales Order" from walkthroughs/place-and-approve-sales-order.md.
// A CSR takes a phone order from demo customer Joe Q Public: one DEMO_1_1, paid by the card on file.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, choose, openDialog, sameId, selectId, signIn, submitTo, urlParam } = require('../../../process-helpers');

const orderDetail = /\/marble\/Order\/OrderDetail\?/;

registerActivity({
  source: 'walkthroughs/place-and-approve-sales-order.md',
  activity: 'Place and Approve Sales Order',
  steps: [
    ...signIn,
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
    {
      name: 'add one DEMO_1_1',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Add Product Item', 'AddProductItemContainer');
        await choose(page, await selectId(form, 'productId'), 'DEMO_1_1', 'DEMO_1_1');
        await form.locator('[name="quantity"]').fill('1');
        await submitTo(page, form.locator('[type="submit"]'), orderDetail);
        await expect(page.getByText('DEMO_1_1').filter({ visible: true }).first()).toBeVisible();
      },
    },
    {
      name: 'pay with the card on file',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Add Payment', 'AddPaymentInfo');
        await choose(page, await selectId(form, 'paymentMethodId'), '1111');
        await submitTo(page, form.locator('[type="submit"]'), orderDetail);
        await expect(page.getByText('1111').filter({ visible: true }).first()).toBeVisible();
      },
    },
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
    {
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
    },
    {
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
    },
  ],
});
