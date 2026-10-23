// Step 5 activity: "Place and Approve Sales Order" from walkthroughs/place-and-approve-sales-order.md.
// A CSR takes a phone order from demo customer Joe Q Public: one DEMO_1_1, paid by the card on file.
const { registerActivity } = require('../../../activity-harness');
const { signIn } = require('../../../process-helpers');
const { placeAndApproveOrder } = require('../../../sales-order-steps');

registerActivity({
  source: 'walkthroughs/place-and-approve-sales-order.md',
  activity: 'Place and Approve Sales Order',
  steps: [...signIn, ...placeAndApproveOrder],
});
