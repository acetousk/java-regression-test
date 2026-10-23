// Steps shared by the inventory processes. Without a purchase order, the inventory mover receives stock directly from
// the Inventory summary ("Receive or Record Inventory" in walkthroughs/initial-setup-and-basics.md).
const { expect } = require('@playwright/test');
const { choose, openDialog, sameId, submitTo, urlParam } = require('./process-helpers');

const findSummary = /\/marble\/Asset\/Asset\/FindSummary\?.*assetTypeEnumId=AstTpInventory/;
const assetDetail = /\/marble\/Asset\/Asset\/AssetDetail\?/;

/** Open Inventory and receive quantity of productId into the Ziziwork Retail warehouse, at location if given. */
function receiveDirect({ productId, quantity, acquireCost, location }) {
  return [
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
      name: `receive ${quantity} ${productId} into the warehouse${location ? ` at ${location}` : ''} at a cost of ${acquireCost}`,
      writes: true,
      run: async page => {
        const form = page.locator('#ReceiveAssetDialog form');
        await choose(page, 'ReceiveAssetForm_productId', productId, productId);
        await form.locator('input[name="quantity"]').fill(String(quantity));
        await choose(page, 'ReceiveAssetForm_facilityId', 'Ziziwork Retail Warehouse', 'Ziziwork Retail');
        if (location) await choose(page, 'ReceiveAssetForm_locationSeqId', location, location);
        await choose(page, 'ReceiveAssetForm_ownerPartyId', 'Ziziwork Retail', 'Ziziwork Retail');
        await form.locator('input[name="acquireCost"]').fill(acquireCost);
        await submitTo(page, form.locator('[type="submit"]'), assetDetail);
        await expect(page.getByText(productId).filter({ visible: true }).first()).toBeVisible();
        return urlParam(page, 'assetId');
      },
      verify: sameId('assetId'),
    },
  ];
}

module.exports = { assetDetail, receiveDirect };
