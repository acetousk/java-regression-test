# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: walkthroughs/find-and-create-customer.activity.spec.js >> walkthroughs/find-and-create-customer.md :: Create Individual Customer >> 02 log in
- Location: activity-harness.js:98:7

# Error details

```
Error: Java/Rust screenshots differ: 77311 pixels
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - toolbar [ref=e5]:
      - button [ref=e6] [cursor=pointer]:
        - img [ref=e8]:
          - generic [ref=e9]: menu
      - link "Home" [ref=e10] [cursor=pointer]:
        - /url: /qapps
        - img "Home" [ref=e12]
      - generic [ref=e13] [cursor=pointer]: Applications
      - generic [ref=e15]: chevron_right
      - link "App List" [ref=e16] [cursor=pointer]:
        - /url: /qapps/AppList
      - button [ref=e17] [cursor=pointer]:
        - img [ref=e19]:
          - generic [ref=e20]: edit_location
      - button [ref=e21] [cursor=pointer]:
        - img [ref=e23]:
          - generic [ref=e24]: notifications
      - button [ref=e25] [cursor=pointer]:
        - img [ref=e27]:
          - generic [ref=e28]: history
      - button [ref=e29] [cursor=pointer]:
        - img [ref=e31]:
          - generic [ref=e32]: account_circle
  - generic [ref=e34]:
    - text:    
    - main [ref=e35]:
      - generic [ref=e38]:
        - heading "Choose an Application" [level=2] [ref=e39]
        - link " Marble ERP" [ref=e41] [cursor=pointer]:
          - /url: /qapps/marble/dashboard
          - generic [ref=e42]:
            - generic [ref=e43]: 
            - text: Marble ERP
        - link " My Account" [ref=e45] [cursor=pointer]:
          - /url: /qapps/my
          - generic [ref=e46]:
            - generic [ref=e47]: 
            - text: My Account
        - link " System" [ref=e49] [cursor=pointer]:
          - /url: /qapps/system
          - generic [ref=e50]:
            - generic [ref=e51]: 
            - text: System
        - link " Tools" [ref=e53] [cursor=pointer]:
          - /url: /qapps/tools
          - generic [ref=e54]:
            - generic [ref=e55]: 
            - text: Tools
        - paragraph [ref=e56]
        - generic [ref=e57]:
          - text: You are using the
          - strong [ref=e58]: dynamic Material
          - text: UI
        - link "Switch to the standard UI" [ref=e60] [cursor=pointer]:
          - /url: /apps
  - contentinfo [ref=e61]:
    - generic [ref=e62]:
      - link "Built on Moqui 0.1.0" [ref=e64] [cursor=pointer]:
        - /url: https://www.moqui.org/
      - link "Site Map" [ref=e66] [cursor=pointer]:
        - /url: /qapps/ScreenTree
```

# Test source

```ts
  51  |   return response.json();
  52  | }
  53  | 
  54  | // Every write an engine commits blocks at the coordinator until its peer commits the matching write,
  55  | // so actions must be issued to both engines at once. Sequential driving would deadlock at the barrier.
  56  | async function both(pages, action) {
  57  |   const results = await Promise.allSettled(engines.map(engine => action(pages[engine], engine)));
  58  |   const failures = results.map((result, index) => result.status === 'rejected'
  59  |     ? `${engines[index]}: ${result.reason?.message || result.reason}` : null).filter(Boolean);
  60  |   if (failures.length) throw new Error(failures.join('\n'));
  61  |   return Object.fromEntries(engines.map((engine, index) => [engine, results[index].value]));
  62  | }
  63  | 
  64  | /**
  65  |  * Register an activity as serial steps. A failed step stops the activity: later steps are not run.
  66  |  * Each step: {name, writes, run(page, engine), verify?(results)}; `writes: true` requires the step to
  67  |  * commit at least one paired, database-compared write transaction.
  68  |  */
  69  | function registerActivity({ source, activity, mode = 'apps', steps }) {
  70  |   test.describe(`${source} :: ${activity}`, () => {
  71  |     test.describe.configure({ mode: 'serial', retries: 0 });
  72  |     const contexts = {}, pages = {};
  73  |     const directory = path.join(process.env.MOQUI_RUN_DIR || path.resolve(__dirname, '../.runs/manual'),
  74  |       'ui-test/activities', source.replace(/\.md$/, ''), activity.toLowerCase().replace(/[^a-z0-9]+/g, '-'));
  75  |     const record = { source, activity, mode, steps: [], passed: false };
  76  | 
  77  |     test.beforeAll(async ({ browser }) => {
  78  |       if (!process.env.MOQUI_HARNESS_STATUS_URL) {
  79  |         throw new Error('Activity specs submit data and must run under the transaction harness ' +
  80  |           '(java-regression-test.py Step 5 sets MOQUI_HARNESS_STATUS_URL)');
  81  |       }
  82  |       const status = await harnessStatus();
  83  |       if (status.error) throw new Error(`Transaction harness already failed: ${status.error}`);
  84  |       for (const engine of engines) {
  85  |         contexts[engine] = await browser.newContext({ baseURL: `${baseURL(engine)}/${mode}/` });
  86  |         contexts[engine].setDefaultTimeout(15000);
  87  |         contexts[engine].setDefaultNavigationTimeout(BARRIER_TIMEOUT);
  88  |         pages[engine] = await contexts[engine].newPage();
  89  |       }
  90  |     });
  91  |     test.afterAll(async () => {
  92  |       record.passed = record.steps.length === steps.length && record.steps.every(step => step.passed);
  93  |       writeJSON(path.join(directory, 'activity.json'), record);
  94  |       await Promise.all(Object.values(contexts).map(context => context.close()));
  95  |     });
  96  | 
  97  |     steps.forEach((step, index) => {
  98  |       test(`${String(index + 1).padStart(2, '0')} ${step.name}`, async () => {
  99  |         test.setTimeout(180000);
  100 |         const entry = { name: step.name, writes: Boolean(step.writes), passed: false };
  101 |         record.steps.push(entry);
  102 |         const stepDir = path.join(directory, `step-${String(index + 1).padStart(2, '0')}`);
  103 |         try {
  104 |           entry.before = await harnessStatus();
  105 |           expect(entry.before.error, 'transaction harness error before step').toBeNull();
  106 |           const results = await both(pages, step.run);
  107 |           if (step.verify) await step.verify(results, pages);
  108 |           // Background commits may still be pairing, one database comparison per write; wait until both engines settle.
  109 |           await expect.poll(async () => {
  110 |             entry.after = await harnessStatus();
  111 |             return entry.after.error || entry.after.unpaired_writes;
  112 |           }, { message: 'transaction harness settled with no unpaired writes', timeout: BARRIER_TIMEOUT })
  113 |             .toEqual({ java: 0, rust: 0 });
  114 |           expect(entry.after.database_comparisons, 'every paired write was database-compared')
  115 |             .toBe(entry.after.write_transactions);
  116 |           entry.pairedWrites = entry.after.write_transactions - entry.before.write_transactions;
  117 |           if (step.writes) {
  118 |             expect(entry.pairedWrites, 'step committed paired, compared writes').toBeGreaterThan(0);
  119 |           }
  120 |           entry.passed = true;
  121 |         } catch (error) {
  122 |           entry.error = error.message;
  123 |           entry.after = await harnessStatus().catch(statusError => ({ statusError: statusError.message }));
  124 |           throw error;
  125 |         } finally {
  126 |           fs.mkdirSync(stepDir, { recursive: true });
  127 |           // A Vue page renders after its own requests; an unsettled page is caught by the screenshot diff.
  128 |           await Promise.all(engines.map(engine => pages[engine]?.waitForLoadState('networkidle').catch(() => {})));
  129 |           await Promise.all(engines.map(engine => pages[engine]?.screenshot({
  130 |             path: path.join(stepDir, `${engine}.png`), fullPage: true }).catch(() => {})));
  131 |           entry.urls = Object.fromEntries(engines.map(engine => [engine, pages[engine]?.url()]));
  132 |           // Retain unmodified screenshots and fail this step on an unapproved visual difference.
  133 |           entry.visual = await diffScreenshots(stepDir).catch(error => ({ status: 'failed', reason: error.message }));
  134 |           if (entry.visual.status !== 'compared') {
  135 |             entry.passed = false;
  136 |             entry.error ||= `Screenshot comparison unavailable: ${entry.visual.reason}`;
  137 |           }
  138 |           if (entry.visual.status === 'compared' && !entry.visual.equal) {
  139 |             const approval = visualApproval(activity, step.name);
  140 |             if (approval) entry.visual.approval = approval;
  141 |             if (!approval) {
  142 |               entry.passed = false;
  143 |               entry.error ||= `Java/Rust screenshots differ: ${entry.visual.differentPixels} pixels`;
  144 |             } else if (entry.visual.differencePercent > approval.max_difference_percent) {
  145 |               entry.passed = false;
  146 |               entry.error ||= `Java/Rust screenshots differ by ${entry.visual.differencePercent.toFixed(3)}%, ` +
  147 |                 `more than the approved ${approval.max_difference_percent}%`;
  148 |             }
  149 |           }
  150 |           writeJSON(path.join(stepDir, 'step.json'), entry);
> 151 |           if (!entry.passed) throw new Error(entry.error);
      |                                    ^ Error: Java/Rust screenshots differ: 77311 pixels
  152 |         }
  153 |       });
  154 |     });
  155 |   });
  156 | }
  157 | 
  158 | async function login(page) {
  159 |   const form = page.locator('#login_form');
  160 |   await form.locator('[name="username"]').fill(process.env.VISUAL_USERNAME || 'john.doe');
  161 |   await form.locator('[name="password"]').fill(process.env.VISUAL_PASSWORD || 'moqui');
  162 |   await Promise.all([
  163 |     page.waitForURL(url => !/\/Login(?:[/?#]|$)/.test(url.pathname), { timeout: BARRIER_TIMEOUT }),
  164 |     // The submit's navigation waits while each login write is paired and compared.
  165 |     form.locator('button[type="submit"]').click({ timeout: BARRIER_TIMEOUT }),
  166 |   ]);
  167 | }
  168 | 
  169 | module.exports = { both, engines, login, registerActivity };
  170 | 
```