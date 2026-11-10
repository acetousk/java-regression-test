// Step 5 activity: "Create Individual Customer" from walkthroughs/find-and-create-customer.md.
// Performed like a user, on both engines in lockstep, under the transaction harness.
const { expect } = require('@playwright/test');
const { login, registerActivity } = require('../../../activity-harness');

const customer = { firstName: 'Regression', lastName: 'Customer', emailAddress: 'regression.customer@example.com' };

registerActivity({
  source: 'walkthroughs/find-and-create-customer.md',
  activity: 'Create Individual Customer',
  steps: [
    {
      name: 'open Login',
      writes: true,
      run: async page => {
        await page.goto('../Login', { waitUntil: 'domcontentloaded' });
        await expect(page.locator('#login_form')).toBeVisible();
      },
    },
    {
      name: 'log in',
      writes: true,
      run: async page => login(page),
    },
    {
      name: 'start on the Marble ERP dashboard and open Customers',
      run: async page => {
        await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
        await Promise.all([
          page.waitForURL(/\/marble\/Customer(?:\/FindCustomer)?(?:[?#]|$)/),
          page.getByRole('link', { name: 'Customers', exact: true }).first().click(),
        ]);
        await expect(page.getByRole('button', { name: 'New Person Customer' })).toBeVisible();
      },
    },
    {
      name: 'open the New Person Customer dialog',
      run: async page => {
        await page.getByRole('button', { name: 'New Person Customer' }).click();
        await expect(page.locator('#CreatePersonDialog [name="firstName"]')).toBeVisible();
      },
    },
    {
      name: 'enter the customer and click Create',
      writes: true,
      run: async page => {
        const form = page.locator('#CreatePersonDialog form');
        for (const [field, value] of Object.entries(customer)) {
          await form.locator(`[name="${field}"]`).fill(value);
        }
        await Promise.all([
          page.waitForURL(/\/marble\/Customer\/EditCustomer\?/),
          form.locator('[type="submit"]').click(),
        ]);
        await expect(page.getByText(`${customer.firstName} ${customer.lastName}`).first()).toBeVisible();
        return new URL(page.url()).searchParams.get('partyId');
      },
      verify: async partyIds => {
        expect(partyIds.java, 'created customer partyId').toBeTruthy();
        expect(partyIds.rust, 'both engines assign the same partyId').toBe(partyIds.java);
      },
    },
  ],
});
