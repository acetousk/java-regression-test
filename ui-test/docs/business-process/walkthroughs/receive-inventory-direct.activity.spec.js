// Step 10 activity: "Receive or Record Inventory" from walkthroughs/initial-setup-and-basics.md. Without a purchase
// order or an incoming shipment, the inventory mover receives stock directly from the Inventory summary: product,
// quantity, facility, owner and acquire cost.
const { expect } = require('@playwright/test');
const { choose, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');

const { registerActivity } = require('../../../activity-harness');

const findSummary = /\/marble\/Asset\/Asset\/FindSummary\?.*assetTypeEnumId=AstTpInventory/;
const assetDetail = /\/marble\/Asset\/Asset\/AssetDetail\?/;

registerActivity({
  source: 'walkthroughs/initial-setup-and-basics.md',
  activity: 'Receive Inventory Direct',
  steps: [
    ...signIn,
    {
      name: 'open Inventory from the dashboard',
      run: async page => {
        await page.goto('marble/dashboard', { waitUntil: 'domcontentloaded' });
        await submitTo(page, page.getByRole('link', { name: /^\W*Inventory\s*$/ }).first(), findSummary);
      },
    },
    {
      name: 'open the Receive Direct dialog',
      run: async page => {
        const form = await openDialog(page, 'Receive Direct', 'ReceiveAssetDialog');
        // The dialog warns that receiving here is a shortcut past the purchase order and incoming shipment.
        await expect(page.getByText(/only receive inventory here if there is no Purchase Order/).filter({ visible: true })
          .first()).toBeVisible();
        await expect(form.locator('[type="submit"]')).toBeVisible();
      },
    },
    {
      name: 'receive 5 DEMO_2_1 into the warehouse at a cost of 7.50',
      writes: true,
      run: async page => {
        const form = page.locator('#ReceiveAssetDialog form');
        await choose(page, 'ReceiveAssetForm_productId', 'DEMO_2_1', 'DEMO_2_1');
        await form.locator('input[name="quantity"]').fill('5');
        await choose(page, 'ReceiveAssetForm_facilityId', 'Ziziwork Retail Warehouse', 'Ziziwork Retail');
        await choose(page, 'ReceiveAssetForm_ownerPartyId', 'Ziziwork Retail', 'Ziziwork Retail');
        await form.locator('input[name="acquireCost"]').fill('7.50');
        await submitTo(page, form.locator('[type="submit"]'), assetDetail);
        await expect(page.getByText('DEMO_2_1').filter({ visible: true }).first()).toBeVisible();
        return urlParam(page, 'assetId');
      },
      verify: sameId('assetId'),
    },
  ],
});
