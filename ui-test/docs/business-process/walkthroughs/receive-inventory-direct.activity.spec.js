// Step 10 activity: "Receive or Record Inventory" from walkthroughs/initial-setup-and-basics.md. Without a purchase
// order or an incoming shipment, the inventory mover receives stock directly from the Inventory summary: product,
// quantity, facility, owner and acquire cost.
const { registerActivity } = require('../../../activity-harness');
const { receiveDirect } = require('../../../inventory-steps');
const { signIn } = require('../../../process-helpers');

registerActivity({
  source: 'walkthroughs/initial-setup-and-basics.md',
  activity: 'Receive Inventory Direct',
  steps: [
    ...signIn,
    ...receiveDirect({ productId: 'DEMO_2_1', quantity: 5, acquireCost: '7.50' }),
  ],
});
