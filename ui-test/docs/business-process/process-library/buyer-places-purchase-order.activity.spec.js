// Step 7 activity: "Buyer Places Purchase Order" from process-library/buyer-places-purchase-order.md. The buyer
// orders 10 DEMO_1_1 from demo supplier Ziddleman & Sons for the Ziziwork Retail warehouse, then places and approves
// the order.
const { registerActivity } = require('../../../activity-harness');
const { signIn } = require('../../../process-helpers');
const { placeAndApprovePurchaseOrder } = require('../../../purchase-order-steps');

registerActivity({
  source: 'process-library/buyer-places-purchase-order.md',
  activity: 'Place Purchase Order',
  steps: [...signIn, ...placeAndApprovePurchaseOrder],
});
