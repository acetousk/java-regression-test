// Step 9 activity: "Accountant Receives Invoice and Sends Payment" from
// process-library/accountant-receives-invoice-and-sends-payment.md. Receiving the purchase shipment invoices the
// organization for it; the accountant approves the supplier's invoice and records the payment sent for it.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, choose, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');
const { placeAndApprovePurchaseOrder, receivePurchaseOrder } = require('../../../purchase-order-steps');

const editInvoice = /\/marble\/Accounting\/Invoice\/EditInvoice\?/;

/** The invoice's status, shown as text; a status button can carry the same words (Payment Sent). */
function invoiceStatus(page, status) {
  return expect(page.getByText(status, { exact: true }).and(page.locator(':not(button)'))
    .filter({ visible: true }).first()).toBeVisible();
}

/** Type a date and time: Java's date-time field is a text box, Rust's a datetime-local input. */
async function fillDateTime(input, date, time) {
  await input.fill(await input.getAttribute('type') === 'datetime-local' ? `${date}T${time}` : `${date} ${time}`);
}

registerActivity({
  source: 'process-library/accountant-receives-invoice-and-sends-payment.md',
  activity: 'Pay a Supplier Invoice',
  steps: [
    ...signIn,
    ...placeAndApprovePurchaseOrder,
    ...receivePurchaseOrder,
    {
      name: 'open the supplier invoice from the shipment',
      run: async page => {
        await submitTo(page, page.getByRole('link', { name: /Invoice\s+\d+/ }).filter({ visible: true }).first(),
          editInvoice);
        await expect(page.getByText(/Payable Invoice/).filter({ visible: true }).first()).toBeVisible();
        return urlParam(page, 'invoiceId');
      },
      verify: sameId('invoiceId'),
    },
    {
      name: 'approve the invoice',
      writes: true,
      run: async page => {
        // The status button asks "Change status to Approved?"; the accountant confirms.
        page.once('dialog', dialog => dialog.accept());
        await submitTo(page, button(page, 'Approve (Approved)'), editInvoice);
        await invoiceStatus(page, 'Approved');
      },
    },
    {
      name: 'record the payment sent for the invoice',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Payment for Invoice', 'RecordPaymentContainer');
        await choose(page, 'RecordPaymentForm_statusId', 'Delivered');
        await fillDateTime(form.locator('input[name="effectiveDate"]'), '2026-10-23', '12:00');
        await form.locator('input[name="paymentRefNum"]').fill('2001');
        await submitTo(page, form.locator('[type="submit"]'), editInvoice);
        await invoiceStatus(page, 'Payment Sent');
        await expect(page.getByText(/Unpaid \$0\.00/).filter({ visible: true }).first()).toBeVisible();
        // GL Transactions sums the invoice and payment postings by account, the codes shown in the account code mask.
        // Whether the payment posts to checking or to unapplied payments depends on the clock against its effective
        // date, so check only the accounts the invoice always posts to.
        for (const account of ['149-300-000: Finished Good Unreceived/Unbilled', '212-000-000: Accounts Payable - Operating'])
          await expect(page.getByText(account, { exact: true }).filter({ visible: true }).first()).toBeVisible();
      },
    },
  ],
});
