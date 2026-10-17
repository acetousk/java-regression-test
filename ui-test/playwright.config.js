const { defineConfig } = require('@playwright/test');
const path = require('node:path');

const runDir = process.env.MOQUI_RUN_DIR
  ? path.resolve(process.env.MOQUI_RUN_DIR)
  : path.resolve(__dirname, '../.runs', new Date().toISOString().replace(/:/g, '-'));

module.exports = defineConfig({
  testDir: './docs/business-process',
  testMatch: ['**/*.visual.spec.js', '**/*.activity.spec.js'],
  workers: 1,
  globalTeardown: './summarize-run.js',
  retries: 0,
  timeout: 60000,
  metadata: { runDir },
  outputDir: path.join(runDir, 'ui-test/test-results'),
  use: {
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    locale: 'en-US',
    timezoneId: 'UTC',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    launchOptions: process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
});
