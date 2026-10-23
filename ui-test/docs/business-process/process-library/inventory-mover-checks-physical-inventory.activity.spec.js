// Step 12 activity: "Inventory Mover Checks Physical Inventory" from
// process-library/inventory-mover-checks-physical-inventory.md. The inventory mover counts the stock at a location and
// records the physical quantity from the Inventory summary; a count below what is on hand adjusts the assets down,
// with the variance reason.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { receiveDirect } = require('../../../inventory-steps');
const { choose, selectId, signIn, submitTo } = require('../../../process-helpers');

const findSummary = /\/marble\/Asset\/Asset\/FindSummary\?/;

/**
 * The Inventory summary row for DEMO_2_1 at bulk location 01010202: it names the product and has the PhI Qty button,
 * where the find summary above names the product only and the total row below has the button only.
 */
function summaryRow(page) {
  return page.locator('tr').filter({ hasText: /01010202/ }).filter({ hasText: /Demo Product Two-One/ })
    .filter({ has: page.getByText(/PhI Qty/) }).filter({ visible: true });
}

/** The row's on-hand quantity, shown under Available just before the PhI Qty button. */
async function onHand(page) {
  const match = (await summaryRow(page).innerText()).match(/([\d.]+)\s+([\d.]+)\s+\W*PhI Qty/);
  expect(match, 'Available and On Hand in the summary row').toBeTruthy();
  return Number(match[2]);
}

// The quantity on hand at 01010202 before the count, per engine: a rerun receives another 8 there.
const counted = {};

registerActivity({
  source: 'process-library/inventory-mover-checks-physical-inventory.md',
  activity: 'Record a Physical Inventory Count',
  steps: [
    ...signIn,
    ...receiveDirect({ productId: 'DEMO_2_1', quantity: 8, acquireCost: '7.50', location: '01010202' }),
    {
      name: 'find the stock at 01010202 in Inventory',
      run: async (page, engine) => {
        await page.goto('marble/Asset/Asset/FindSummary?assetTypeEnumId=AstTpInventory&productId=DEMO_2_1'
          + '&facilityId=ZIRET_WH&locationSeqId=01010202', { waitUntil: 'domcontentloaded' });
        await page.waitForLoadState('networkidle');
        await expect(summaryRow(page)).toHaveCount(1);
        counted[engine] = await onHand(page);
        expect(counted[engine], 'the 8 just received are on hand').toBeGreaterThanOrEqual(8);
        return counted[engine];
      },
      verify: async quantities => expect(quantities.rust, 'both engines have the same quantity on hand').toBe(quantities.java),
    },
    {
      name: 'open the PhI Qty dialog',
      run: async page => {
        await summaryRow(page).getByText(/PhI Qty/).click();
        const form = page.locator('[id^="PhysicalQuantityDialog"] form').filter({ visible: true }).first();
        await expect(form).toBeVisible();
        await expect(form.locator('input[name="quantity"]')).toBeVisible();
        await expect(form.getByText(/01010202/).first()).toBeVisible();
      },
    },
    {
      name: 'record a count of 2 less than on hand, the other 2 damaged',
      writes: true,
      run: async (page, engine) => {
        const form = page.locator('[id^="PhysicalQuantityDialog"] form').filter({ visible: true }).first();
        await form.locator('input[name="quantity"]').fill(String(counted[engine] - 2));
        await choose(page, await selectId(form, 'varianceReasonEnumId'), 'Damaged');
        await form.locator('textarea[name="comments"]').fill('Two cases crushed on the bottom shelf');
        await submitTo(page, form.locator('[type="submit"]'), findSummary);
        // Recording the count adjusts the location's assets down to the counted quantity.
        await expect.poll(() => onHand(page)).toBe(counted[engine] - 2);
      },
    },
  ],
});
