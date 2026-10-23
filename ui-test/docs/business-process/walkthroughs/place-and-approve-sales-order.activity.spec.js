// Step 5 activity: "Place and Approve Sales Order" from walkthroughs/place-and-approve-sales-order.md.
// A CSR takes a phone order from demo customer Joe Q Public: one DEMO_1_1, paid by the card on file.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, choose, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');

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
      name: 'choose the customer and click Create',
      writes: true,
      run: async page => {
        const form = page.locator('#CreateSalesOrderDialog form');
        await choose(page, 'CreateSalesOrder_customerPartyId', 'Joe', 'Joe');
        await submitTo(page, form.locator('[type="submit"]'), orderDetail);
        await expect(page.getByText('Joe Q Public').first()).toBeVisible();
        return urlParam(page, 'orderId');
      },
      verify: sameId('orderId'),
    },
    {
      name: 'add one DEMO_1_1',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Add Product Item', 'AddProductItemContainer');
        await choose(page, 'AddProductItemForm_productId', 'DEMO_1_1', 'DEMO_1_1');
        await form.locator('[name="quantity"]').fill('1');
        await submitTo(page, form.locator('[type="submit"]'), orderDetail);
        await expect(page.getByText('DEMO_1_1').first()).toBeVisible();
      },
    },
    {
      name: 'pay with the card on file',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Add Payment', 'AddPaymentInfo');
        await choose(page, 'AddPaymentForm_paymentMethodId', '1111');
        await submitTo(page, form.locator('[type="submit"]'), orderDetail);
        await expect(page.getByText('1111').first()).toBeVisible();
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
        await expect(page.getByText('Placed').first()).toBeVisible();
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
        await expect(page.getByText('Approved').first()).toBeVisible();
      },
    },
  ],
});
