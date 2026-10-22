// Targeted, read-only Playwright probe; use only against isolated test servers.
const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const { loadProcess, modes } = require('./process-plan');
const { capture, compare } = require('./process-runner');

(async () => {
  if (!process.env.MOQUI_RUN_DIR) throw new Error('MOQUI_RUN_DIR is required');
  const runDir = path.resolve(process.env.MOQUI_RUN_DIR);
  const activity = loadProcess('walkthroughs/place-and-approve-sales-order.md').activities
    .find(activity => activity.id === 'activity-008');
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
  const reports = [];
  try {
    for (const mode of modes) {
      const directory = path.join(runDir, 'ui-test/sales-order-probe', mode);
      fs.mkdirSync(directory, { recursive: true });
      const captures = [];
      for (const engine of ['java', 'rust']) {
        const result = await capture(browser, engine, mode, activity, runDir);
        captures.push(result);
        const screenshot = path.join(result.directory, 'screen.visual.png');
        if (fs.existsSync(screenshot)) fs.copyFileSync(screenshot, path.join(directory, `screen.${engine}.visual.png`));
      }
      const report = { mode, activity, captures, comparison: await compare(directory, captures) };
      fs.writeFileSync(path.join(directory, 'report.json'), JSON.stringify(report, null, 2));
      reports.push(report);
      console.log(mode, captures.map(capture => `${capture.engine}: ${capture.status}; dialog=${!!capture.dialogOpened}`).join('; '));
    }
    fs.writeFileSync(path.join(runDir, 'ui-test/sales-order-probe/summary.json'), JSON.stringify(reports, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
