// Step 13 activity: "Create, Pack and Ship a Transfer Shipment" and "Receive a Transfer Shipment" from
// walkthroughs/transfer-shipments.md. The demo data has one warehouse, so the shipper first adds the facility to
// transfer to; then transfers 4 of the stock just received there: add the item, schedule, pack and issue it from
// the asset, pack, ship, receive it at the destination and set the shipment delivered.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { receiveDirect } = require('../../../inventory-steps');
const { button, choose, openDialog, sameId, selectId, signIn, submitTo, urlParam } = require('../../../process-helpers');
const { expectShipmentStatus, shipOrder, shipmentDetail } = require('../../../sales-order-steps');

const [, , setScheduled, , setPacked, setShipped] = shipOrder;

// The asset received at the warehouse, per engine, packed and issued from.
const received = {};

registerActivity({
  source: 'walkthroughs/transfer-shipments.md',
  activity: 'Transfer Shipment',
  steps: [
    ...signIn,
    ...receiveDirect({ productId: 'DEMO_2_1', quantity: 6, acquireCost: '7.50' }),
    {
      name: 'open Facilities',
      run: async (page, engine) => {
        received[engine] = urlParam(page, 'assetId');
        expect(received[engine], 'the received asset').toBeTruthy();
        await page.goto('marble/Facility/FindFacility', { waitUntil: 'domcontentloaded' });
        await page.waitForLoadState('networkidle');
        await expect(button(page, 'New Facility')).toBeVisible();
      },
    },
    {
      name: 'add the store back room facility',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Facility', 'NewFacilityDialog');
        await form.locator('input[name="pseudoId"]').fill('ZIRET_BACK');
        await form.locator('input[name="facilityName"]').fill('Ziziwork Retail Back Room');
        await choose(page, 'NewFacilityForm_ownerPartyId', 'Ziziwork Retail', 'Ziziwork Retail');
        await submitTo(page, form.locator('[type="submit"]'), /\/marble\/Facility\/EditFacility\?/);
        return urlParam(page, 'facilityId');
      },
      verify: sameId('facilityId'),
    },
    {
      name: 'open Shipments',
      run: async page => {
        await page.goto('marble/Shipment/FindShipment', { waitUntil: 'domcontentloaded' });
        await page.waitForLoadState('networkidle');
        await expect(button(page, 'New Transfer Shipment')).toBeVisible();
      },
    },
    {
      name: 'create a transfer from the warehouse to the back room',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'New Transfer Shipment', 'NewTransferShipmentDialog');
        // Re-choosing the option a Tom Select already shows leaves it open: choose the origin only if it differs.
        if (await page.locator('#NewTransferShipment_originFacilityId').inputValue() !== 'ZIRET_WH')
          await choose(page, 'NewTransferShipment_originFacilityId', 'Ziziwork Retail Warehouse', 'Ziziwork Retail W');
        await choose(page, 'NewTransferShipment_destinationFacilityId', 'Ziziwork Retail Back Room', 'Back Room');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expectShipmentStatus(page, 'Input');
        return urlParam(page, 'shipmentId');
      },
      verify: sameId('shipmentId'),
    },
    {
      name: 'add 4 DEMO_2_1 to transfer',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Add Item', 'AddItemContainer');
        await choose(page, 'AddItemForm_productId', 'DEMO_2_1', 'DEMO_2_1');
        await form.locator('input[name="quantity"]').fill('4');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expect(button(page, 'Pack/Issue Item')).toBeVisible();
      },
    },
    setScheduled,
    {
      name: 'pack and issue the 4 from the received asset',
      writes: true,
      run: async (page, engine) => {
        const form = await openDialog(page, 'Pack/Issue Item', 'PackItemContainer');
        await expect(form.locator('input[name="quantity"]')).toHaveValue('4');
        await choose(page, await selectId(form, 'assetId'), `${received[engine]} - `, received[engine]);
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expect(page.getByText(/Packed\/Issued: 4, Remaining: 0/).filter({ visible: true }).first()).toBeVisible();
      },
    },
    setPacked,
    setShipped,
    {
      name: 'open the Receive Product dialog',
      run: async page => {
        await button(page, 'Receive Product').click();
        const form = page.locator('form[id^="ReceiveForm"]').filter({ visible: true }).first();
        await expect(form).toBeVisible();
        await expect(form.getByText('Ziziwork Retail Back Room').first()).toBeVisible();
      },
    },
    {
      name: 'receive the 4 into the back room',
      writes: true,
      run: async page => {
        const form = page.locator('form[id^="ReceiveForm"]').filter({ visible: true }).first();
        await form.locator('input[name="quantityAccepted"]').fill('4');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expect(page.getByText(/Receive Accepted: 4, Rejected: 0, Remaining: 0/).filter({ visible: true }).first())
          .toBeVisible();
      },
    },
    {
      name: 'set the shipment delivered',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Set Delivered', 'SetDeliveredDialog');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expectShipmentStatus(page, 'Delivered');
      },
    },
  ],
});
