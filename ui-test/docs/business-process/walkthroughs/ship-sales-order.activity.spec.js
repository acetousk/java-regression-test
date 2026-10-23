// Step 5 activity: "Ship Sales Order" from walkthroughs/ship-sales-order.md.
// A shipper takes an approved order through Order Detail and Shipment Detail: create the shipment, schedule it,
// issue and pack the item, then set it packed (which invoices it) and shipped. No carrier gateway is configured, so
// the label steps do not apply.
const { registerActivity } = require('../../../activity-harness');
const { signIn } = require('../../../process-helpers');
const { placeAndApproveOrder, shipOrder } = require('../../../sales-order-steps');

registerActivity({
  source: 'walkthroughs/ship-sales-order.md',
  activity: 'Ship Sales Order',
  steps: [...signIn, ...placeAndApproveOrder, ...shipOrder],
});
