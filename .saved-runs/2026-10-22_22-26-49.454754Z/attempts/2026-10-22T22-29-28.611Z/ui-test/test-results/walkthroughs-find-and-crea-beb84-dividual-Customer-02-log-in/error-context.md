# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: walkthroughs/find-and-create-customer.activity.spec.js >> walkthroughs/find-and-create-customer.md :: Create Individual Customer >> 02 log in
- Location: activity-harness.js:96:7

# Error details

```
Error: java: locator.click: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('#login_form').locator('button[type="submit"]')
    - locator resolved to <button type="submit" class="btn btn-lg btn-primary btn-block">Sign in</button>
  - attempting click action
    - waiting for element to be visible, enabled and stable
    - element is visible, enabled and stable
    - scrolling into view if needed
    - done scrolling
    - performing click action
    - click action done
    - waiting for scheduled navigations to finish

rust: locator.click: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('#login_form').locator('button[type="submit"]')
    - locator resolved to <button type="submit" data-size="lg" data-btn="primary">Sign in</button>
  - attempting click action
    - waiting for element to be visible, enabled and stable
    - element is visible, enabled and stable
    - scrolling into view if needed
    - done scrolling
    - performing click action
    - click action done
    - waiting for scheduled navigations to finish

```

# Page snapshot

```yaml
- generic [ref=e2]: deterministic request failed
```

# Test source

```ts
  47  |   const response = await fetch(process.env.MOQUI_HARNESS_STATUS_URL);
  48  |   if (!response.ok) throw new Error(`Transaction harness status failed: HTTP ${response.status}`);
  49  |   return response.json();
  50  | }
  51  | 
  52  | // Every write an engine commits blocks at the coordinator until its peer commits the matching write,
  53  | // so actions must be issued to both engines at once. Sequential driving would deadlock at the barrier.
  54  | async function both(pages, action) {
  55  |   const results = await Promise.allSettled(engines.map(engine => action(pages[engine], engine)));
  56  |   const failures = results.map((result, index) => result.status === 'rejected'
  57  |     ? `${engines[index]}: ${result.reason?.message || result.reason}` : null).filter(Boolean);
  58  |   if (failures.length) throw new Error(failures.join('\n'));
  59  |   return Object.fromEntries(engines.map((engine, index) => [engine, results[index].value]));
  60  | }
  61  | 
  62  | /**
  63  |  * Register an activity as serial steps. A failed step stops the activity: later steps are not run.
  64  |  * Each step: {name, writes, run(page, engine), verify?(results)}; `writes: true` requires the step to
  65  |  * commit at least one paired, database-compared write transaction.
  66  |  */
  67  | function registerActivity({ source, activity, mode = 'apps', steps }) {
  68  |   test.describe(`${source} :: ${activity}`, () => {
  69  |     test.describe.configure({ mode: 'serial', retries: 0 });
  70  |     const contexts = {}, pages = {};
  71  |     const directory = path.join(process.env.MOQUI_RUN_DIR || path.resolve(__dirname, '../.runs/manual'),
  72  |       'ui-test/activities', source.replace(/\.md$/, ''), activity.toLowerCase().replace(/[^a-z0-9]+/g, '-'));
  73  |     const record = { source, activity, mode, steps: [], passed: false };
  74  | 
  75  |     test.beforeAll(async ({ browser }) => {
  76  |       if (!process.env.MOQUI_HARNESS_STATUS_URL) {
  77  |         throw new Error('Activity specs submit data and must run under the transaction harness ' +
  78  |           '(java-regression-test.py Step 5 sets MOQUI_HARNESS_STATUS_URL)');
  79  |       }
  80  |       const status = await harnessStatus();
  81  |       if (status.error) throw new Error(`Transaction harness already failed: ${status.error}`);
  82  |       for (const engine of engines) {
  83  |         contexts[engine] = await browser.newContext({ baseURL: `${baseURL(engine)}/${mode}/` });
  84  |         contexts[engine].setDefaultTimeout(15000);
  85  |         contexts[engine].setDefaultNavigationTimeout(120000);
  86  |         pages[engine] = await contexts[engine].newPage();
  87  |       }
  88  |     });
  89  |     test.afterAll(async () => {
  90  |       record.passed = record.steps.length === steps.length && record.steps.every(step => step.passed);
  91  |       writeJSON(path.join(directory, 'activity.json'), record);
  92  |       await Promise.all(Object.values(contexts).map(context => context.close()));
  93  |     });
  94  | 
  95  |     steps.forEach((step, index) => {
  96  |       test(`${String(index + 1).padStart(2, '0')} ${step.name}`, async () => {
  97  |         test.setTimeout(180000);
  98  |         const entry = { name: step.name, writes: Boolean(step.writes), passed: false };
  99  |         record.steps.push(entry);
  100 |         const stepDir = path.join(directory, `step-${String(index + 1).padStart(2, '0')}`);
  101 |         try {
  102 |           entry.before = await harnessStatus();
  103 |           expect(entry.before.error, 'transaction harness error before step').toBeNull();
  104 |           const results = await both(pages, step.run);
  105 |           if (step.verify) await step.verify(results, pages);
  106 |           // Background commits may still be pairing; wait until both engines are settled.
  107 |           await expect.poll(async () => {
  108 |             entry.after = await harnessStatus();
  109 |             return entry.after.error || entry.after.unpaired_writes;
  110 |           }, { message: 'transaction harness settled with no unpaired writes', timeout: 15000 })
  111 |             .toEqual({ java: 0, rust: 0 });
  112 |           expect(entry.after.database_comparisons, 'every paired write was database-compared')
  113 |             .toBe(entry.after.write_transactions);
  114 |           entry.pairedWrites = entry.after.write_transactions - entry.before.write_transactions;
  115 |           if (step.writes) {
  116 |             expect(entry.pairedWrites, 'step committed paired, compared writes').toBeGreaterThan(0);
  117 |           }
  118 |           entry.passed = true;
  119 |         } catch (error) {
  120 |           entry.error = error.message;
  121 |           entry.after = await harnessStatus().catch(statusError => ({ statusError: statusError.message }));
  122 |           throw error;
  123 |         } finally {
  124 |           fs.mkdirSync(stepDir, { recursive: true });
  125 |           await Promise.all(engines.map(engine => pages[engine]?.screenshot({
  126 |             path: path.join(stepDir, `${engine}.png`), fullPage: true }).catch(() => {})));
  127 |           entry.urls = Object.fromEntries(engines.map(engine => [engine, pages[engine]?.url()]));
  128 |           // Retain unmodified screenshots and fail this step on an unapproved visual difference.
  129 |           entry.visual = await diffScreenshots(stepDir).catch(error => ({ status: 'failed', reason: error.message }));
  130 |           if (entry.visual.status !== 'compared') {
  131 |             entry.passed = false;
  132 |             entry.error ||= `Screenshot comparison unavailable: ${entry.visual.reason}`;
  133 |           }
  134 |           if (entry.visual.status === 'compared' && !entry.visual.equal) {
  135 |             const approval = visualApproval(activity, step.name);
  136 |             if (approval) entry.visual.approval = approval;
  137 |             if (!approval) {
  138 |               entry.passed = false;
  139 |               entry.error ||= `Java/Rust screenshots differ: ${entry.visual.differentPixels} pixels`;
  140 |             } else if (entry.visual.differencePercent > approval.max_difference_percent) {
  141 |               entry.passed = false;
  142 |               entry.error ||= `Java/Rust screenshots differ by ${entry.visual.differencePercent.toFixed(3)}%, ` +
  143 |                 `more than the approved ${approval.max_difference_percent}%`;
  144 |             }
  145 |           }
  146 |           writeJSON(path.join(stepDir, 'step.json'), entry);
> 147 |           if (!entry.passed) throw new Error(entry.error);
      |                                    ^ Error: java: locator.click: Timeout 15000ms exceeded.
  148 |         }
  149 |       });
  150 |     });
  151 |   });
  152 | }
  153 | 
  154 | async function login(page) {
  155 |   const form = page.locator('#login_form');
  156 |   await form.locator('[name="username"]').fill(process.env.VISUAL_USERNAME || 'john.doe');
  157 |   await form.locator('[name="password"]').fill(process.env.VISUAL_PASSWORD || 'moqui');
  158 |   await Promise.all([
  159 |     page.waitForURL(url => !/\/Login(?:[/?#]|$)/.test(url.pathname), { timeout: 30000 }),
  160 |     form.locator('button[type="submit"]').click(),
  161 |   ]);
  162 | }
  163 | 
  164 | module.exports = { both, engines, login, registerActivity };
  165 | 
```