// Read-only comparison against already-running isolated Java/Rust test servers.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { parseArgs } = require('node:util');

function options(argv) {
  const { values } = parseArgs({ args: argv, options: {
    route: { type: 'string' }, random: { type: 'boolean' },
    modes: { type: 'string', default: 'apps,qapps' },
    'dialog-id': { type: 'string' }, 'dialog-label': { type: 'string' },
    'run-dir': { type: 'string' },
  } });
  if (!!values.route === !!values.random) throw new Error('Choose exactly one of --route or --random');
  const modes = values.modes.split(',');
  if (!modes.length || new Set(modes).size !== modes.length || modes.some(mode => !['apps', 'qapps'].includes(mode))) {
    throw new Error('--modes must contain apps and/or qapps, without duplicates');
  }
  if (!!values['dialog-id'] !== !!values['dialog-label']) throw new Error('Supply both --dialog-id and --dialog-label');
  if (values.random && values['dialog-id']) throw new Error('A dialog requires an explicit --route');
  if (values.route && (!values.route.startsWith('marble/') || values.route.includes('#') ||
      values.route.split('?')[0].split('/').some(part => part === '.' || part === '..'))) {
    throw new Error('--route must be a relative marble/ screen path, optionally with query parameters');
  }
  return { route: values.route, random: !!values.random, modes,
    dialog: values['dialog-id'] ? { id: values['dialog-id'], label: values['dialog-label'] } : undefined,
    runDir: values['run-dir'] || process.env.MOQUI_RUN_DIR };
}

function selectRoute(config) {
  if (!config.random) return { ...config, selection: 'explicit' };
  const { loadProcess } = require('./process-plan');
  const directory = path.resolve(__dirname, '../docs/business-processes/walkthroughs');
  const candidates = [...new Set(fs.readdirSync(directory).filter(file => file.endsWith('.md'))
    .flatMap(file => loadProcess(`walkthroughs/${file}`).activities)
    .filter(activity => activity.route && !activity.dialog).map(activity => activity.route))];
  if (!candidates.length) throw new Error('No mapped walkthrough screen routes');
  return { ...config, route: candidates[crypto.randomInt(candidates.length)],
    selection: 'random unique mapped walkthrough route', candidates };
}

async function run(config) {
  if (!config.runDir) throw new Error('--run-dir or MOQUI_RUN_DIR is required');
  const selected = selectRoute(config);
  const runDir = path.resolve(config.runDir);
  const directory = path.join(runDir, 'ui-test/screen-probe');
  // One invocation per run: never silently reuse captures from a prior comparison.
  if (fs.existsSync(directory)) throw new Error(`Comparison output already exists: ${directory}`);
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, 'selection.json'), JSON.stringify(selected, null, 2) + '\n');
  console.log(`Comparing ${selected.route} in ${selected.modes.join(', ')}`);
  const { chromium } = require('@playwright/test');
  const { capture, compare } = require('./process-runner');
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
  const reports = [];
  try {
    for (const mode of selected.modes) {
      const output = path.join(directory, mode);
      fs.mkdirSync(output);
      const captures = [];
      for (const engine of ['java', 'rust']) {
        const result = await capture(browser, engine, mode, { route: selected.route, dialog: selected.dialog }, runDir);
        captures.push(result);
        const screenshot = path.join(result.directory, 'screen.visual.png');
        if (fs.existsSync(screenshot)) fs.copyFileSync(screenshot, path.join(output, `screen.${engine}.visual.png`));
      }
      const report = { mode, route: selected.route, dialog: selected.dialog, captures,
        comparison: await compare(output, captures) };
      fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
      reports.push(report);
      console.log(`${mode}: ${report.comparison.status}; differing pixels=${report.comparison.differencePercent ?? 'unavailable'}%`);
    }
  } finally {
    fs.writeFileSync(path.join(directory, 'summary.json'), JSON.stringify(reports, null, 2) + '\n');
    await browser.close();
  }
  // Successful collection is not visual parity, nor a completed business workflow.
  return reports.every(report => report.comparison.status === 'compared' && report.comparison.equal);
}

if (require.main === module) {
  Promise.resolve().then(() => run(options(process.argv.slice(2))))
    .then(equal => { if (!equal) process.exitCode = 1; })
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
module.exports = { options, selectRoute, run };
