// Step 5 activity: "Create Sales Account" and "Create Sales Contact" from walkthroughs/find-and-create-customer.md.
// A CSR adds an organization customer as a Sales Account, then adds its buyer as a Sales Contact of that account.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { choose, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');

const account = 'Regression Sales Account';
const contact = { firstName: 'Regression', lastName: 'Buyer' };
const editCustomer = /\/marble\/Customer\/EditCustomer\?/;

/** Open Customers from the dashboard, as the user does before each New dialog. */
async function openCustomers(page) {
  await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
  await submitTo(page, page.getByRole('link', { name: 'Customers', exact: true }).first(),
    /\/marble\/Customer(?:\/FindCustomer)?(?:[?#]|$)/);
}

registerActivity({
  source: 'walkthroughs/find-and-create-customer.md',
  activity: 'Create Sales Account and Sales Contact',
  steps: [
    ...signIn,
    {
      name: 'open Customers from the dashboard',
      run: openCustomers,
    },
    {
      name: 'create the Sales Account',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Sales Account (Organization Customer)', 'CreateAccountDialog');
        await form.locator('[name="organizationName"]').fill(account);
        await submitTo(page, form.locator('[type="submit"]'), editCustomer);
        await expect(page.getByText(account).first()).toBeVisible();
        return urlParam(page, 'partyId');
      },
      verify: sameId('account partyId'),
    },
    {
      name: 'return to Customers',
      run: openCustomers,
    },
    {
      name: 'create the buyer as a Sales Contact of the account',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Sales Contact', 'CreateContactDialog');
        await choose(page, 'CreateContactForm_accountPartyId', account, 'Regression Sales');
        for (const [field, value] of Object.entries(contact)) {
          await form.locator(`[name="${field}"]`).fill(value);
        }
        await choose(page, 'CreateContactForm_fromRoleTypeId', 'Buyer');
        await submitTo(page, form.locator('[type="submit"]'), editCustomer);
        await expect(page.getByText(`${contact.firstName} ${contact.lastName}`).first()).toBeVisible();
        await expect(page.getByText(account).first()).toBeVisible();
        return urlParam(page, 'partyId');
      },
      verify: sameId('contact partyId'),
    },
  ],
});
