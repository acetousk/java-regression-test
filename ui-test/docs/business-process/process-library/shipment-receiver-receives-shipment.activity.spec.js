// Step 8 activity: "Shipment Receiver Receives Shipment" from process-library/shipment-receiver-receives-shipment.md.
// The buyer's approved purchase order gets an incoming shipment; the receiver schedules it and receives every item
// into the warehouse.
const { registerActivity } = require('../../../activity-harness');
const { signIn } = require('../../../process-helpers');
const { placeAndApprovePurchaseOrder, receivePurchaseOrder } = require('../../../purchase-order-steps');

registerActivity({
  source: 'process-library/shipment-receiver-receives-shipment.md',
  activity: 'Receive Purchase Shipment',
  steps: [...signIn, ...placeAndApprovePurchaseOrder, ...receivePurchaseOrder],
});
