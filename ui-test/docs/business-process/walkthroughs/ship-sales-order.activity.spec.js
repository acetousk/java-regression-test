// Step 5 activity: "Ship Sales Order" from walkthroughs/ship-sales-order.md.
// A shipper takes an approved order through Order Detail and Shipment Detail: create the shipment, schedule it,
// issue and pack the item, then set it packed (which invoices it) and shipped. No carrier gateway is configured, so
// the label steps do not apply.
const { expect } = require('@playwright/test');
const { registerActivity } = require('../../../activity-harness');
const { button, openDialog, sameId, signIn, submitTo, urlParam } = require('../../../process-helpers');
const { orderDetail, placeAndApproveOrder } = require('../../../sales-order-steps');

const shipmentDetail = /\/marble\/Shipment\/ShipmentDetail\?/;

/** The status shown in the Shipment Detail header form. */
async function expectShipmentStatus(page, status) {
  await expect(page.getByText(status, { exact: true }).filter({ visible: true }).first()).toBeVisible();
}

registerActivity({
  source: 'walkthroughs/ship-sales-order.md',
  activity: 'Ship Sales Order',
  steps: [
    ...signIn,
    ...placeAndApproveOrder,
    {
      name: 'create a shipment for the order part',
      writes: true,
      run: async page => {
        await submitTo(page, button(page, 'Create Shipment'), orderDetail);
        await expect(page.getByRole('link', { name: /Shipment\s+\d+/ }).filter({ visible: true }).first()).toBeVisible();
      },
    },
    {
      name: 'open the shipment',
      run: async page => {
        await submitTo(page, page.getByRole('link', { name: /Shipment\s+\d+/ }).filter({ visible: true }).first(),
          shipmentDetail);
        await expect(button(page, 'Set Scheduled')).toBeVisible();
        return urlParam(page, 'shipmentId');
      },
      verify: sameId('shipmentId'),
    },
    {
      name: 'set the shipment scheduled',
      writes: true,
      run: async page => {
        await submitTo(page, button(page, 'Set Scheduled'), shipmentDetail);
        await expectShipmentStatus(page, 'Scheduled');
      },
    },
    {
      name: 'issue and pack the reserved item',
      writes: true,
      run: async page => {
        await submitTo(page, button(page, 'Issue & Pack'), shipmentDetail);
        await expect(button(page, 'Set Packed')).toBeVisible();
      },
    },
    {
      name: 'set the shipment packed',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Set Packed', 'SetPackedDialog');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expectShipmentStatus(page, 'Packed');
      },
    },
    {
      name: 'set the shipment shipped',
      writes: true,
      run: async page => {
        const form = await openDialog(page, 'Set Shipped', 'SetShippedDialog');
        await submitTo(page, form.locator('[type="submit"]'), shipmentDetail);
        await expectShipmentStatus(page, 'Shipped');
        // The status history and actual start are dates as Java shows them, not epoch millis.
        await expect(page.locator('body')).not.toContainText(/\b\d{13}\b/);
      },
    },
  ],
});
