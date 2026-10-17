const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { docs, loadProcess, modes } = require('./process-plan');
const summarize = require('./summarize-run');

test('every visual placeholder in every source document gets a source-linked record', () => {
  let count = 0;
  for (const group of ['walkthroughs', 'process-library']) {
    for (const file of fs.readdirSync(path.join(docs, group)).filter(file => file.endsWith('.md'))) {
      const process = loadProcess(`${group}/${file}`);
      const lines = fs.readFileSync(path.join(docs, group, file), 'utf8').split('\n');
      assert.equal(process.activities.length, lines.filter(line => /^\s*- visual test:/.test(line)).length);
      assert.equal(new Set(process.activities.map(activity => activity.id)).size, process.activities.length);
      for (const activity of process.activities) {
        assert.match(lines[activity.sourceLine - 1], /^\s*- visual test:/);
        assert.ok(activity.limitation);
        assert.ok(activity.text);
      }
      count++;
    }
  }
  assert.equal(count, 42);
  assert.deepEqual(modes, ['apps', 'vapps', 'qapps']);
});

test('manual carrier story is not replaced by an invented ERP flow', () => {
  const process = loadProcess('process-library/carrier-does-not-deliver-shipment-to-customer.md');
  assert.ok(process.activities.length);
  assert.ok(process.activities.every(activity => activity.route === null));
});

test('documented dialog labels resolve to screen XML without requiring submission', () => {
  const process = loadProcess('walkthroughs/company-setup.md');
  const activity = process.activities.find(activity => activity.dialog?.label === 'New Organization');
  assert.equal(activity.route, 'marble/Party/FindParty');
  assert.equal(activity.dialog.id, 'CreateOrganizationDialog');
  assert.equal(activity.mapping, 'documented-dialog-label');
});

test('all-data mode does not remove original initial-setup activities from the inventory', () => {
  const process = loadProcess('walkthroughs/initial-setup-and-basics.md');
  assert.ok(process.activities.some(activity => activity.headings.includes('Create Initial Admin user (a one time action)')));
  assert.ok(process.activities.some(activity => activity.text.includes('entity_empty_db_load')));
});

test('partial and blocked evidence is retained but fails the final gate', async () => {
  const runDir = fs.mkdtempSync(path.join(os.tmpdir(), 'moqui-visual-test-'));
  try {
    const directory = path.join(runDir, 'ui-test/process-library/example');
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, 'apps.summary.json'), JSON.stringify({
      source: 'example.md', mode: 'apps', activities: [
        { id: 'activity-001', coverage: 'partial' },
        { id: 'activity-002', coverage: 'blocked' },
      ],
    }));
    await assert.rejects(summarize({ metadata: { runDir } }), /incomplete or failed/);
    const result = JSON.parse(fs.readFileSync(path.join(runDir, 'ui-test/summary.json')));
    assert.equal(result.activityModes, 2);
    assert.equal(result.partial, 1);
    assert.equal(result.blocked, 1);
    assert.equal(result.completeWorkflows, 0);
  } finally { fs.rmSync(runDir, { recursive: true, force: true }); }
});
