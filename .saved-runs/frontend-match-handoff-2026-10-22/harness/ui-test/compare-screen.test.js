const { test } = require('node:test');
const assert = require('node:assert/strict');
const { options, selectRoute, run } = require('./compare-screen');

const route = 'marble/Shipment/FindShipment?shipmentTypeEnumId=ShpTpTransfer';

test('explicit screen defaults to apps and qapps without changing source', () => {
  const config = options(['--route', route, '--run-dir', '/tmp/probe']);
  assert.deepEqual(config.modes, ['apps', 'qapps']);
  assert.equal(selectRoute(config).route, route);
  assert.equal(config.runDir, '/tmp/probe');
});

test('individual modes and named dialogs are parameter-driven', () => {
  const config = options(['--route', route, '--modes', 'qapps', '--dialog-id', 'ShipmentList_hdialog', '--dialog-label', 'Find Options']);
  assert.deepEqual(config.modes, ['qapps']);
  assert.deepEqual(config.dialog, { id: 'ShipmentList_hdialog', label: 'Find Options' });
});

test('invalid selections fail before browser startup', () => {
  for (const argv of [[], ['--route', route, '--random'], ['--route', route, '--modes', 'vapps'],
    ['--route', route, '--modes', 'apps,apps'], ['--route', route, '--modes', ''],
    ['--route', route, '--dialog-id', 'only'], ['--route', '/apps/marble'],
    ['--route', 'marble/../Login'], ['--route', 'marble/dashboard#other'],
    ['--random', '--dialog-id', 'id', '--dialog-label', 'label']]) {
    assert.throws(() => options(argv), undefined, argv.join(' '));
  }
});

test('random selection records its unique mapped route pool', () => {
  const selected = selectRoute(options(['--random']));
  assert.ok(selected.candidates.includes(selected.route));
  assert.equal(new Set(selected.candidates).size, selected.candidates.length);
  assert.ok(selected.candidates.every(candidate => candidate.startsWith('marble/')));
});

test('literal shell templates are blocked, not treated as valid screens', () => {
  const { shellTemplateUnrendered } = require('./process-runner');
  assert.equal(shellTemplateUnrendered('<#assign headerLogoList = sri.getThemeValues("STRT_HEADER_LOGO")>'), true);
  assert.equal(shellTemplateUnrendered('<#assign footerItemList = sri.getThemeValues("STRT_FOOTER_ITEM")>'), true);
  assert.equal(shellTemplateUnrendered('Find Shipments Type: Transfer'), false);
  assert.equal(shellTemplateUnrendered('Documentation: <#assign example = 1>'), false);
});

test('output requires an explicit run directory', async () => {
  await assert.rejects(run({ route, modes: ['apps', 'qapps'] }), /run-dir or MOQUI_RUN_DIR is required/);
});
