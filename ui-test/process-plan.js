const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const docs = path.join(root, 'docs/business-processes');
const screens = path.join(root, 'moqui-framework/runtime/component/SimpleScreens/screen/SimpleScreens');
const modes = ['apps', 'vapps', 'qapps'];

// These are entry-screen candidates, NOT implementations of the prose stories.
// External/storefront stories intentionally have no Marble substitute.
const entries = {
  'accountant-receives-invoice-and-sends-payment': 'Accounting/Invoice/FindInvoice?invoiceType=Payable',
  'accountant-reconciles-bank-account': 'Accounting/Payment/FindPayment',
  'accountant-sends-invoice-and-receives-payment': 'Accounting/Invoice/FindInvoice?invoiceType=Receivable',
  'buyer-places-purchase-order': 'Order/FindOrder?orderType=Purchase',
  'company-approves-sales-order': 'Order/FindOrder?orderType=Sales',
  'company-fulfills-sales-order': 'Shipping/dashboard',
  'company-processes-return-received': 'Return/FindReturn?returnType=Customer',
  'customer-cancels-order': 'Order/FindOrder?orderType=Sales',
  'customer-returns-product': 'Return/FindReturn?returnType=Customer',
  'inventory-mover-checks-physical-inventory': 'Asset/PhysicalInventory/FindPhysicalInventory',
  'inventory-mover-does-stock-move': 'Asset/Asset/FindSummary',
  'inventory-mover-puts-away-inventory': 'Asset/Asset/FindSummary',
  'placing-customer-places-a-sales-order-through-csr': 'Order/FindOrder?orderType=Sales',
  'product-marketer-maintains-product-information': 'Catalog/Product/FindProduct',
  'sales-representative-leads-prospects-from-rfq-to-sales-order': 'Request/FindRequest',
  'sales-representative-seeks-prospects-and-opportunities': 'Customer/FindCustomer',
  'shipment-receiver-receives-shipment': 'Shipment/FindShipment?shipmentTypeEnumId=ShpTpPurchase',
  'b2b-sales-process': 'Customer/FindCustomer',
  'story-of-online-retail-company': 'dashboard',
  'bank-accounts': 'Party/FindParty?roleTypeId=OrgInternal',
  'company-setup': 'Party/FindParty?roleTypeId=OrgInternal',
  'find-and-create-customer': 'Customer/FindCustomer',
  'initial-setup-and-basics': 'dashboard',
  'period-closing': 'Accounting/TimePeriod/FindTimePeriod',
  'place-and-approve-sales-order': 'Order/FindOrder?orderType=Sales',
  'pricing-and-promotions': 'Catalog/Product/FindProduct',
  'procure-to-pay': 'Order/FindOrder?orderType=Purchase',
  'ship-sales-order': 'Shipment/FindShipment?shipmentTypeEnumId=ShpTpSales',
  'shipping-management-with-picklists': 'Shipping/Picklist/FindPicklist',
  'transfer-shipments': 'Shipment/FindShipment?shipmentTypeEnumId=ShpTpTransfer',
};
const navigation = {
  'Customers': 'Customer/FindCustomer', 'Find Customer': 'Customer/FindCustomer',
  'Internal': 'Party/FindParty?roleTypeId=OrgInternal', 'All Parties': 'Party/FindParty',
  'Employees': 'Party/FindParty?roleTypeId=Employee',
  'Products': 'Catalog/Product/FindProduct', 'Facilities': 'Facility/FindFacility',
  'Stores': 'ProductStore/FindProductStore', 'Projects': 'Project/FindProject',
  'Tasks': 'Task/FindTask', 'Labor Rates': 'HumanRes/EditRateAmounts',
  'Sales Orders & Quotes': 'Order/FindOrder?orderType=Sales',
  'Purchase Orders & Quotes': 'Order/FindOrder?orderType=Purchase',
  'Receivable Invoices': 'Accounting/Invoice/FindInvoice?invoiceType=Receivable',
  'Payable Invoices': 'Accounting/Invoice/FindInvoice?invoiceType=Payable',
  'Customer Payments': 'Accounting/Payment/FindPayment?paymentType=Incoming',
  'Supplier Payments': 'Accounting/Payment/FindPayment?paymentType=Outgoing',
  'Accounting': 'Accounting/dashboard', 'Reports': 'Accounting/Reports/ReportList',
  'Inventory': 'Asset/Asset/FindSummary?assetTypeEnumId=AstTpInventory',
};
function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry =>
    entry.isDirectory() ? walk(path.join(directory, entry.name)) : [path.join(directory, entry.name)]);
}
const dialogs = [];
for (const file of walk(screens).filter(file => file.endsWith('.xml'))) {
  const xml = fs.readFileSync(file, 'utf8');
  const route = path.relative(screens, file).replace(/\.xml$/, '').split(path.sep).join('/');
  for (const match of xml.matchAll(/<(?:container-dialog|dynamic-dialog)\b[^>]*>/g)) {
    const label = match[0].match(/button-text="([^"]+)"/);
    const id = match[0].match(/\bid="([^"]+)"/);
    if (label && id && !label[1].includes('${')) dialogs.push({
      label: label[1].replace(/&amp;/g, '&'), id: id[1], route,
    });
  }
}
function loadProcess(relative) {
  const file = path.join(docs, relative);
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  const slug = path.basename(relative, '.md');
  const activities = [];
  let block = [], headings = [], currentRoute = entries[slug] || null;
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const heading = line.match(/^(#{1,6})\s+(.+)/);
    if (heading) {
      headings = headings.slice(0, heading[1].length - 1);
      headings[heading[1].length - 1] = heading[2];
      block = [];
    } else if (/^\s*- visual test:/.test(line)) {
      const text = block.filter(line => !/^\s*- transition test:/.test(line)).join('\n').trim();
      const context = [...headings, text].join('\n');
      const explicit = [...text.matchAll(/marble\/[A-Za-z0-9_/?=&.-]+/g)].map(m => m[0].replace(/^marble\//, ''));
      let mapping = 'entry-candidate';
      if (explicit.length) { currentRoute = explicit.at(-1); mapping = 'documented-url'; }
      else {
        for (const [label, route] of Object.entries(navigation)) {
          if (text.includes(`**${label}**`) || text.includes(`*${label}*`)) {
            currentRoute = route;
            mapping = 'documented-navigation-label';
          }
        }
      }
      const labels = [...text.matchAll(/\*\*([^*]+)\*\*/g)].map(m => m[1]);
      const candidates = /dialog|drop-down|popup|menu/i.test(text)
        ? dialogs.filter(dialog => labels.includes(dialog.label)) : [];
      const dialog = candidates.find(dialog => currentRoute?.split('?')[0] === dialog.route) ||
        (candidates.length === 1 ? candidates[0] : null);
      if (dialog) { currentRoute = dialog.route; mapping = 'documented-dialog-label'; }
      activities.push({
        id: `activity-${String(activities.length + 1).padStart(3, '0')}`,
        sourceLine: index + 1, headings: headings.filter(Boolean), text: text || headings.at(-1),
        route: currentRoute ? `marble/${currentRoute}` : null,
        dialog: dialog || null, mapping,
        limitation: currentRoute
          ? 'Read-only screen/dialog evidence only. Prerequisite creation, field input, submissions, integrations and full story transitions are not executed.'
          : 'No verified browser workflow in the installed Marble components; storefront, integration, manual action or mapping required.',
      });
      block = [];
    } else if (!/^\s*- transition test:/.test(line)) {
      block.push(line);
    }
  }
  return { source: `docs/business-processes/${relative}`, group: path.dirname(relative), slug, activities };
}
module.exports = { root, docs, modes, loadProcess };
