// Step 11 activity: "Inventory Mover does Stock Move" (bulk-to-pick) from
// process-library/inventory-mover-does-stock-move.md. Stock received into a bulk location is moved in part to a pick
// location; the rest stays in bulk.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { assetDetail, receiveDirect } = require('../../../inventory-steps');
const { choose, signIn, submitTo, urlParam } = require('../../../process-helpers');

const moveAsset = /\/marble\/Asset\/Asset\/MoveAsset\?/;
/** The received asset's id on each engine, to come back to it after the move. */
const bulkAssetId = {};

registerActivity({
  source: 'process-library/inventory-mover-does-stock-move.md',
  activity: 'Move Stock from Bulk to Pick',
  steps: [
    ...signIn,
    ...receiveDirect({ productId: 'DEMO_2_1', quantity: 10, acquireCost: '7.50', location: '01010102' }),
    {
      name: 'open the asset\'s Move tab',
      run: async page => {
        await submitTo(page, page.getByRole('link', { name: /^\s*Move\s*$/ }).filter({ visible: true }).first(), moveAsset);
        await expect(page.getByText(/Move Asset \d+/).filter({ visible: true }).first()).toBeVisible();
        // The asset is on hand in its bulk location.
        await expect(page.getByText(/01010102\s+\[01:01:01:02: \]\s+Bulk/).filter({ visible: true }).first()).toBeVisible();
      },
    },
    {
      name: 'move 4 of the 10 to pick location 01010101',
      writes: true,
      run: async (page, engine) => {
        bulkAssetId[engine] = urlParam(page, 'assetId');
        const form = page.locator('form#EnterMoveAssetForm');
        // The move stays in the asset's facility, which the form starts on.
        await expect(page.locator('#EnterMoveAssetForm_facilityId')).toHaveValue('ZIRET_WH');
        await choose(page, 'EnterMoveAssetForm_locationSeqId', '01010101', '01010101');
        await form.locator('input[name="quantity"]').fill('4');
        await submitTo(page, form.locator('[type="submit"]'), /\/marble\/Asset\/Asset\/SelectAsset\?/);
      },
    },
    {
      name: 'open the asset left in bulk',
      run: async (page, engine) => {
        await page.goto(`marble/Asset/Asset/AssetDetail?assetId=${bulkAssetId[engine]}`, { waitUntil: 'domcontentloaded' });
        await expect(page).toHaveURL(assetDetail);
        // Six remain at the bulk location, on hand and available; the history shows the 4 moved to a new asset.
        await expect(page.getByText(/01010102\s+\[01:01:01:02: \]\s+Bulk/).filter({ visible: true }).first()).toBeVisible();
        await expect(page.getByText(/^\s*6 \(each\)\s*$/).filter({ visible: true })).toHaveCount(2);
        const moved = page.locator('tr').filter({ hasText: /Move, other asset: \d+/ }).filter({ visible: true });
        await expect(moved).toHaveCount(1);
        await expect(moved.getByText(/^\s*-4\s*$/)).toHaveCount(2);
      },
    },
  ],
});
