# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: process-library/open-marble-login.visual.spec.js >> vapps: open Marble ERP and compare the anonymous login screen
- Location: docs/business-process/process-library/open-marble-login.visual.spec.js:9:1

# Error details

```
Error: rust: protected screen request failed

expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1  | const { test, expect } = require('@playwright/test');
  2  | const fs = require('node:fs');
  3  | const path = require('node:path');
  4  | const { PNG } = require('pngjs');
  5  | 
  6  | // Initial Setup and Basics: visit a protected screen as an anonymous user.
  7  | // Temporary all-data mode shows seeded-user login, NOT initial-admin creation.
  8  | for (const renderMode of ['apps', 'vapps', 'qapps']) {
  9  | test(`${renderMode}: open Marble ERP and compare the anonymous login screen`, async ({ browser }) => {
  10 |   const pixelmatch = (await import('pixelmatch')).default;
  11 |   const directory = path.join(test.info().config.metadata.runDir,
  12 |     'ui-test/process-library/open-marble-login', renderMode);
  13 |   fs.mkdirSync(directory, { recursive: true });
  14 |   const prefix = path.join(directory, 'screen');
  15 |   const urls = {
  16 |     java: process.env.JAVA_BASE_URL || 'http://127.0.0.1:8080',
  17 |     rust: process.env.RUST_BASE_URL || 'http://127.0.0.1:8081',
  18 |   };
  19 |   const captures = {};
  20 |   const finalURLs = {};
  21 |   for (const [engine, baseURL] of Object.entries(urls)) {
  22 |     // Separate contexts: never carry Java cookies or local storage into Rust.
  23 |     const context = await browser.newContext();
  24 |     try {
  25 |       const page = await context.newPage();
  26 |       const response = await page.goto(`${baseURL}/${renderMode}/marble`, { waitUntil: 'networkidle' });
> 27 |       expect(response.ok(), `${engine}: protected screen request failed`).toBeTruthy();
     |                                                                           ^ Error: rust: protected screen request failed
  28 |       finalURLs[engine] = page.url();
  29 |       const login = page.locator('#login_form');
  30 |       await expect(login).toBeVisible();
  31 |       await expect(login.getByRole('textbox', { name: 'Username', exact: true })).toBeVisible();
  32 |       await expect(login.locator('input[name="password"]')).toBeVisible();
  33 |       await expect(login.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  34 |       await page.evaluate(async () => {
  35 |         await document.fonts.ready;
  36 |         await Promise.all(Array.from(document.images, image => image.decode().catch(() => {})));
  37 |       });
  38 |       captures[engine] = PNG.sync.read(await page.screenshot({
  39 |         path: `${prefix}.${engine}.visual.png`, fullPage: true,
  40 |         animations: 'disabled', caret: 'hide',
  41 |       }));
  42 |       await test.info().attach(`${engine} login`, {
  43 |         path: `${prefix}.${engine}.visual.png`, contentType: 'image/png',
  44 |       });
  45 |     } finally {
  46 |       await context.close();
  47 |     }
  48 |   }
  49 |   // Pad unequal sizes instead of resizing (resizing would conceal layout errors).
  50 |   const width = Math.max(captures.java.width, captures.rust.width);
  51 |   const height = Math.max(captures.java.height, captures.rust.height);
  52 |   const padded = Object.values(captures).map(image => {
  53 |     const canvas = new PNG({ width, height, fill: true });
  54 |     PNG.bitblt(image, canvas, 0, 0, image.width, image.height, 0, 0);
  55 |     return canvas;
  56 |   });
  57 |   const diff = new PNG({ width, height });
  58 |   const differentPixels = pixelmatch(padded[0].data, padded[1].data, diff.data,
  59 |     width, height, { threshold: 0.1 });
  60 |   const dimensionsEqual = captures.java.width === captures.rust.width &&
  61 |     captures.java.height === captures.rust.height;
  62 |   fs.writeFileSync(`${prefix}.diff.visual.png`, PNG.sync.write(diff));
  63 |   fs.writeFileSync(path.join(directory, 'comparison.json'), JSON.stringify({
  64 |     activity: 'Open Marble ERP anonymously (all demo data loaded)',
  65 |     source: 'docs/business-processes/walkthroughs/initial-setup-and-basics.md',
  66 |     renderMode, urls, finalURLs, dimensions: Object.fromEntries(Object.entries(captures).map(([engine, image]) =>
  67 |       [engine, { width: image.width, height: image.height }])),
  68 |     dimensionsEqual, differentPixels, comparedPixels: width * height,
  69 |     differencePercent: 100 * differentPixels / (width * height),
  70 |     threshold: 0.1, equal: dimensionsEqual && differentPixels === 0,
  71 |   }, null, 2) + '\n');
  72 |   await test.info().attach('visual difference', {
  73 |     path: `${prefix}.diff.visual.png`, contentType: 'image/png',
  74 |   });
  75 |   expect(dimensionsEqual, 'Java/Rust screenshot dimensions differ').toBeTruthy();
  76 |   expect(differentPixels, 'Java/Rust visual mismatch; inspect PNGs and comparison.json').toBe(0);
  77 | });
  78 | }
  79 | 
```