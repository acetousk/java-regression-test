const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { captureStep } = require('./capture-step');

test('shared steps reuse screenshots, while engine, mode and dialog stay distinct', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'moqui-steps-'));
  let screenshots = 0;
  const page = {
    url: () => 'http://example/apps/marble/Order/FindOrder',
    evaluate: async () => {},
    screenshot: async ({ path: file }) => { screenshots++; fs.writeFileSync(file, 'screenshot'); },
  };
  const identity = { engine: 'java', mode: 'apps', step: 'screen', route: 'marble/Order/FindOrder' };
  try {
    const first = await captureStep(page, directory, identity);
    const reused = await captureStep(page, directory, identity);
    assert.equal(first.reused, false);
    assert.equal(reused.reused, true);
    assert.equal(first.screenshot, reused.screenshot);
    assert.equal(screenshots, 1);
    for (const variant of [{ engine: 'rust' }, { mode: 'vapps' }, { step: 'dialog', dialog: 'CreateSalesOrderDialog' }]) {
      assert.equal((await captureStep(page, directory, { ...identity, ...variant })).reused, false);
    }
    assert.equal(screenshots, 4);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('failed screenshots are retried rather than reused', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'moqui-steps-'));
  const page = { url: () => 'http://example', evaluate: async () => {}, screenshot: async ({ path: file }) => {
    fs.writeFileSync(file, 'incomplete');
    throw new Error('capture failed');
  } };
  try {
    const failed = await captureStep(page, directory, { step: 'login' });
    assert.equal(failed.error, 'capture failed');
    assert.equal(fs.existsSync(failed.screenshot), false);
    page.screenshot = async ({ path: file }) => fs.writeFileSync(file, 'complete');
    const retried = await captureStep(page, directory, { step: 'login' });
    assert.equal(retried.reused, false);
    assert.equal(retried.error, undefined);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
