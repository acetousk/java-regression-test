const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('@playwright/test');
const { waitQapps } = require('./wait-qapps');

test('qapps waits for nested screen completion, not an early history change', async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
  try {
    const page = await browser.newPage();
    await page.setContent('<div id="current-page-root"><div class="spinner"></div></div>');
    await page.evaluate(() => {
      window.moqui = { webrootVue: {
        loading: 1, currentPath: '/qapps/marble/Order/FindOrder',
        currentPathList: ['marble', 'Order', 'FindOrder'],
        activeSubscreens: [{ pathName: 'marble' }],
        $nextTick: callback => Promise.resolve().then(callback),
        $watch: (getter, callback) => { window.changed = callback; return () => { window.unwatched = true; }; }
      } };
    });
    const pending = waitQapps(page, 'marble/Order/FindOrder?orderType=Purchase');
    // This second evaluation runs after waitQapps has installed its observers.
    await page.evaluate(() => {
      const vm = moqui.webrootVue;
      vm.loading = 0;
      window.changed();
    });
    assert.equal(await page.evaluate(() => !!window.unwatched), false);
    await page.evaluate(() => {
      const vm = moqui.webrootVue;
      vm.activeSubscreens.push({ pathName: 'Order' }, { pathName: 'FindOrder' });
      window.changed();
    });
    assert.equal(await page.evaluate(() => !!window.unwatched), false);
    await page.evaluate(() => { document.querySelector('#current-page-root').innerHTML = '<form id="OrderList"></form>'; });
    await pending;
    assert.equal(await page.evaluate(() => window.unwatched), true);
  } finally { await browser.close(); }
});

test('qapps rejects missing roots and unfinished screens instead of capturing them', async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
  try {
    const page = await browser.newPage();
    await page.setContent('<div></div>');
    await assert.rejects(waitQapps(page, 'marble/dashboard'), /Vue root is missing/);
    await page.evaluate(() => {
      window.moqui = { webrootVue: {
        loading: 1, currentPath: '/qapps/marble/dashboard', currentPathList: ['marble', 'dashboard'], activeSubscreens: [],
        $nextTick: callback => Promise.resolve().then(callback), $watch: () => () => {}
      } };
    });
    await assert.rejects(waitQapps(page, 'marble/dashboard', 50), /did not finish loading/);
  } finally { await browser.close(); }
});
