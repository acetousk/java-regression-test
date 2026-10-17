// Step 5 driver: perform a business-process activity like a user, on Java and Rust in lockstep,
// with every step checked against the deterministic transaction coordinator.
const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const engines = ['java', 'rust'];

function baseURL(engine) {
  return process.env[`${engine.toUpperCase()}_BASE_URL`] || `http://127.0.0.1:${engine === 'java' ? 8080 : 8081}`;
}
function writeJSON(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}

async function harnessStatus() {
  const response = await fetch(process.env.MOQUI_HARNESS_STATUS_URL);
  if (!response.ok) throw new Error(`Transaction harness status failed: HTTP ${response.status}`);
  return response.json();
}

// Every write an engine commits blocks at the coordinator until its peer commits the matching write,
// so actions must be issued to both engines at once. Sequential driving would deadlock at the barrier.
async function both(pages, action) {
  const results = await Promise.allSettled(engines.map(engine => action(pages[engine], engine)));
  const failures = results.map((result, index) => result.status === 'rejected'
    ? `${engines[index]}: ${result.reason?.message || result.reason}` : null).filter(Boolean);
  if (failures.length) throw new Error(failures.join('\n'));
  return Object.fromEntries(engines.map((engine, index) => [engine, results[index].value]));
}

/**
 * Register an activity as serial steps. A failed step stops the activity: later steps are not run.
 * Each step: {name, writes, run(page, engine), verify?(results)}; `writes: true` requires the step to
 * commit at least one paired, database-compared write transaction.
 */
function registerActivity({ source, activity, mode = 'apps', steps }) {
  test.describe(`${source} :: ${activity}`, () => {
    test.describe.configure({ mode: 'serial', retries: 0 });
    const contexts = {}, pages = {};
    const directory = path.join(process.env.MOQUI_RUN_DIR || path.resolve(__dirname, '../.runs/manual'),
      'ui-test/activities', source.replace(/\.md$/, ''), activity.toLowerCase().replace(/[^a-z0-9]+/g, '-'));
    const record = { source, activity, mode, steps: [], passed: false };

    test.beforeAll(async ({ browser }) => {
      if (!process.env.MOQUI_HARNESS_STATUS_URL) {
        throw new Error('Activity specs submit data and must run under the transaction harness ' +
          '(java-regression-test.py Step 5 sets MOQUI_HARNESS_STATUS_URL)');
      }
      const status = await harnessStatus();
      if (status.error) throw new Error(`Transaction harness already failed: ${status.error}`);
      for (const engine of engines) {
        contexts[engine] = await browser.newContext({ baseURL: `${baseURL(engine)}/${mode}/` });
        pages[engine] = await contexts[engine].newPage();
      }
    });
    test.afterAll(async () => {
      record.passed = record.steps.length === steps.length && record.steps.every(step => step.passed);
      writeJSON(path.join(directory, 'activity.json'), record);
      await Promise.all(Object.values(contexts).map(context => context.close()));
    });

    steps.forEach((step, index) => {
      test(`${String(index + 1).padStart(2, '0')} ${step.name}`, async () => {
        const entry = { name: step.name, writes: Boolean(step.writes), passed: false };
        record.steps.push(entry);
        const stepDir = path.join(directory, `step-${String(index + 1).padStart(2, '0')}`);
        try {
          entry.before = await harnessStatus();
          expect(entry.before.error, 'transaction harness error before step').toBeNull();
          const results = await both(pages, step.run);
          if (step.verify) await step.verify(results, pages);
          // Background commits may still be pairing; wait until both engines are settled.
          await expect.poll(async () => {
            entry.after = await harnessStatus();
            return entry.after.error || entry.after.unpaired_writes;
          }, { message: 'transaction harness settled with no unpaired writes', timeout: 15000 })
            .toEqual({ java: 0, rust: 0 });
          expect(entry.after.database_comparisons, 'every paired write was database-compared')
            .toBe(entry.after.write_transactions);
          entry.pairedWrites = entry.after.write_transactions - entry.before.write_transactions;
          if (step.writes) {
            expect(entry.pairedWrites, 'step committed paired, compared writes').toBeGreaterThan(0);
          }
          entry.passed = true;
        } catch (error) {
          entry.error = error.message;
          throw error;
        } finally {
          fs.mkdirSync(stepDir, { recursive: true });
          await Promise.all(engines.map(engine => pages[engine]?.screenshot({
            path: path.join(stepDir, `${engine}.png`), fullPage: true }).catch(() => {})));
          entry.urls = Object.fromEntries(engines.map(engine => [engine, pages[engine]?.url()]));
          writeJSON(path.join(stepDir, 'step.json'), entry);
        }
      });
    });
  });
}

async function login(page) {
  await page.goto('../Login', { waitUntil: 'domcontentloaded' });
  const form = page.locator('#login_form');
  await form.locator('[name="username"]').fill(process.env.VISUAL_USERNAME || 'john.doe');
  await form.locator('[name="password"]').fill(process.env.VISUAL_PASSWORD || 'moqui');
  await Promise.all([
    page.waitForURL(url => !/\/Login(?:[/?#]|$)/.test(url.pathname), { timeout: 30000 }),
    form.locator('button[type="submit"]').click(),
  ]);
}

module.exports = { both, engines, login, registerActivity };
