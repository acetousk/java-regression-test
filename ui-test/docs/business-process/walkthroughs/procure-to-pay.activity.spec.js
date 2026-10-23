// Step 5 activity: "Add Supplier" from walkthroughs/procure-to-pay.md.
// A buyer adds an organization supplier, then gives it an email address for purchase orders.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');

const supplier = 'Regression Supplier';
const email = 'orders@regression-supplier.example.com';
const editSupplier = /\/marble\/Supplier\/EditSupplier\?/;

registerActivity({
  source: 'walkthroughs/procure-to-pay.md',
  activity: 'Add Supplier',
  steps: [
    ...signIn,
    {
      name: 'open Suppliers from the dashboard',
      run: async page => {
        await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
        await submitTo(page, page.getByRole('link', { name: 'Suppliers', exact: true }).first(),
          /\/marble\/Supplier(?:\/FindSupplier)?(?:[?#]|$)/);
      },
    },
    {
      name: 'create the organization supplier',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Organization Supplier', 'CreateOrganizationDialog');
        await form.locator('[name="organizationName"]').fill(supplier);
        await submitTo(page, form.locator('[type="submit"]'), editSupplier);
        await expect(page.getByText(supplier).first()).toBeVisible();
        await expect(page.getByText('Supplier', { exact: true }).first()).toBeVisible();
        return urlParam(page, 'partyId');
      },
      verify: sameId('supplier partyId'),
    },
    {
      name: 'add the supplier\'s order email',
      writes: true,
      run: async page => {
        // Email is an item of the Phone, Email, and Other box's Add New menu.
        await button(page, 'Add New').click();
        await button(page, 'Email').click();
        const form = page.locator('[id^="AddEmailInfo"] form').filter({ visible: true }).first();
        await expect(form.locator('[name="emailAddress"]')).toBeVisible();
        await form.locator('[name="emailAddress"]').fill(email);
        await submitTo(page, form.locator('[type="submit"]'), editSupplier);
        await expect(page.getByText(email).first()).toBeVisible();
      },
    },
  ],
});
