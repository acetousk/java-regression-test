// Step 5 activity: "Accountant Sends Invoice and Receives Payment" from
// process-library/accountant-sends-invoice-and-receives-payment.md, the Billing story. An order paid by personal
// check is shipped; packing it invoices the customer. The check arrives and the accountant records it against the
// invoice, which is then paid. (The CC Payment story is automatic: ship-sales-order's card order is paid when packed.)
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');
const { payByInstrument, placeAndApproveOrderPaidBy, shipOrder } = require('../../../sales-order-steps');

const editInvoice = /\/marble\/Accounting\/Invoice\/EditInvoice\?/;

registerActivity({
  source: 'process-library/accountant-sends-invoice-and-receives-payment.md',
  activity: 'Receive Payment for a Sales Invoice',
  steps: [
    ...signIn,
    ...placeAndApproveOrderPaidBy(payByInstrument('Personal Check')),
    ...shipOrder,
    {
      name: 'open the invoice from the shipment',
      run: async page => {
        await submitTo(page, page.getByRole('link', { name: /Invoice\s+\d+/ }).filter({ visible: true }).first(),
          editInvoice);
        return urlParam(page, 'invoiceId');
      },
      verify: sameId('invoiceId'),
    },
    {
      name: 'record the check against the promised payment: Send & Apply',
      writes: true,
      run: async page => {
        await expect(page.getByText('Finalized', { exact: true }).filter({ visible: true }).first()).toBeVisible();
        await page.locator('input[name="paymentRefNum"]').filter({ visible: true }).first().fill('1001');
        await submitTo(page, button(page, 'Send & Apply'), editInvoice);
        await expect(page.getByText('Payment Received', { exact: true }).filter({ visible: true }).first()).toBeVisible();
      },
    },
  ],
});
