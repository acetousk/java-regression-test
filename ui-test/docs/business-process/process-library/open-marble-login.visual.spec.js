const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const { PNG } = require('pngjs');

// Initial Setup and Basics: visit a protected screen as an anonymous user.
// Temporary all-data mode shows seeded-user login, NOT initial-admin creation.
for (const renderMode of ['apps', 'vapps', 'qapps']) {
test(`${renderMode}: open Marble ERP and compare the anonymous login screen`, async ({ browser }) => {
  const pixelmatch = (await import('pixelmatch')).default;
  const directory = path.join(test.info().config.metadata.runDir,
    'ui-test/process-library/open-marble-login', renderMode);
  fs.mkdirSync(directory, { recursive: true });
  const prefix = path.join(directory, 'screen');
  const urls = {
    java: process.env.JAVA_BASE_URL || 'http://127.0.0.1:8080',
    rust: process.env.RUST_BASE_URL || 'http://127.0.0.1:8081',
  };
  const captures = {};
  const finalURLs = {};
  for (const [engine, baseURL] of Object.entries(urls)) {
    // Separate contexts: never carry Java cookies or local storage into Rust.
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const response = await page.goto(`${baseURL}/${renderMode}/marble`, { waitUntil: 'networkidle' });
      expect(response.ok(), `${engine}: protected screen request failed`).toBeTruthy();
      finalURLs[engine] = page.url();
      const login = page.locator('#login_form');
      await expect(login).toBeVisible();
      await expect(login.getByRole('textbox', { name: 'Username', exact: true })).toBeVisible();
      await expect(login.locator('input[name="password"]')).toBeVisible();
      await expect(login.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(Array.from(document.images, image => image.decode().catch(() => {})));
      });
      captures[engine] = PNG.sync.read(await page.screenshot({
        path: `${prefix}.${engine}.visual.png`, fullPage: true,
        animations: 'disabled', caret: 'hide',
      }));
      await test.info().attach(`${engine} login`, {
        path: `${prefix}.${engine}.visual.png`, contentType: 'image/png',
      });
    } finally {
      await context.close();
    }
  }
  // Pad unequal sizes instead of resizing (resizing would conceal layout errors).
  const width = Math.max(captures.java.width, captures.rust.width);
  const height = Math.max(captures.java.height, captures.rust.height);
  const padded = Object.values(captures).map(image => {
    const canvas = new PNG({ width, height, fill: true });
    PNG.bitblt(image, canvas, 0, 0, image.width, image.height, 0, 0);
    return canvas;
  });
  const diff = new PNG({ width, height });
  const differentPixels = pixelmatch(padded[0].data, padded[1].data, diff.data,
    width, height, { threshold: 0.1 });
  const dimensionsEqual = captures.java.width === captures.rust.width &&
    captures.java.height === captures.rust.height;
  fs.writeFileSync(`${prefix}.diff.visual.png`, PNG.sync.write(diff));
  fs.writeFileSync(path.join(directory, 'comparison.json'), JSON.stringify({
    activity: 'Open Marble ERP anonymously (all demo data loaded)',
    source: 'docs/business-processes/walkthroughs/initial-setup-and-basics.md',
    renderMode, urls, finalURLs, dimensions: Object.fromEntries(Object.entries(captures).map(([engine, image]) =>
      [engine, { width: image.width, height: image.height }])),
    dimensionsEqual, differentPixels, comparedPixels: width * height,
    differencePercent: 100 * differentPixels / (width * height),
    threshold: 0.1, equal: dimensionsEqual && differentPixels === 0,
  }, null, 2) + '\n');
  await test.info().attach('visual difference', {
    path: `${prefix}.diff.visual.png`, contentType: 'image/png',
  });
  expect(dimensionsEqual, 'Java/Rust screenshot dimensions differ').toBeTruthy();
  expect(differentPixels, 'Java/Rust visual mismatch; inspect PNGs and comparison.json').toBe(0);
});
}
