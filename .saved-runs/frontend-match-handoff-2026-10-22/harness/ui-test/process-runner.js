const { test } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { PNG } = require('pngjs');
const { modes, loadProcess } = require('./process-plan');
const { captureStep } = require('./capture-step');
const contextOptions = { viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1,
  locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', reducedMotion: 'reduce' };

function writeJSON(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}
function copyEvidence(source, destination) {
  if (!fs.existsSync(source)) return;
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  if (fs.existsSync(destination)) fs.unlinkSync(destination);
  try { fs.linkSync(source, destination); }
  catch { fs.copyFileSync(source, destination); }
}
async function authenticate(browser, baseURL, directory) {
  const key = crypto.createHash('sha256').update(baseURL).digest('hex').slice(0, 16);
  const state = path.join(directory, '_sessions', `${key}.json`);
  const evidence = path.join(directory, '_sessions', `${key}.login.json`);
  if (fs.existsSync(evidence)) {
    const login = JSON.parse(fs.readFileSync(evidence));
    return { ...login, state: fs.existsSync(state) ? state : undefined,
      steps: (login.steps || []).map(step => ({ ...step, reused: !step.error })) };
  }
  const context = await browser.newContext(contextOptions);
  const result = { baseURL, authenticated: false, steps: [] };
  try {
    const page = await context.newPage();
    await page.goto(`${baseURL}/Login`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    result.steps.push(await captureStep(page, directory, { baseURL, step: 'login', url: page.url() }));
    const form = page.locator('#login_form');
    await form.locator('[name="username"]').fill(process.env.VISUAL_USERNAME || 'john.doe', { timeout: 4000 });
    await form.locator('[name="password"]').fill(process.env.VISUAL_PASSWORD || 'moqui', { timeout: 4000 });
    await Promise.all([
      page.waitForURL(url => !/\/Login(?:[/?#]|$)/.test(url.pathname), { timeout: 15000 }),
      form.locator('button[type="submit"]').click({ timeout: 4000 }),
    ]);
    result.authenticated = !/\/Login(?:[/?#]|$)/.test(new URL(page.url()).pathname);
    result.finalURL = page.url();
    result.steps.push(await captureStep(page, directory, { baseURL, step: 'authenticated', url: page.url() }));
    fs.mkdirSync(path.dirname(state), { recursive: true, mode: 0o700 });
    await context.storageState({ path: state });
    fs.chmodSync(state, 0o600);
  } catch (error) {
    result.error = error.message;
  } finally { await context.close(); }
  writeJSON(evidence, result);
  return { state: fs.existsSync(state) ? state : undefined, ...result };
}
function shellTemplateUnrendered(text) {
  return /<#assign\s+(?:headerLogoList|headerTitleList|footerItemList|screenHistoryList)\b/.test(text);
}
async function capture(browser, engine, mode, activity, runDir) {
  const baseURL = process.env[`${engine.toUpperCase()}_BASE_URL`] ||
    `http://127.0.0.1:${engine === 'java' ? 8080 : 8081}`;
  const key = crypto.createHash('sha256').update(JSON.stringify({
    baseURL, engine, mode, route: activity.route, dialog: activity.dialog,
  })).digest('hex').slice(0, 24);
  const directory = path.join(runDir, 'ui-test/_captures', key);
  const reportFile = path.join(directory, 'capture.json');
  if (fs.existsSync(reportFile)) {
    const cached = JSON.parse(fs.readFileSync(reportFile));
    return { ...cached, directory, reused: true,
      steps: (cached.steps || []).map(step => ({ ...step, reused: !step.error })) };
  }
  fs.mkdirSync(directory, { recursive: true });
  const login = await authenticate(browser, baseURL, path.join(runDir, 'ui-test'));
  const context = await browser.newContext({ ...contextOptions, storageState: login.state });
  const result = { engine, mode, route: activity.route, dialog: activity.dialog,
    authenticated: login.authenticated, loginError: login.error, errors: [],
    failedRequests: [], httpErrors: [], consoleErrors: [], status: 'blocked', reused: false,
    steps: [...(login.steps || [])] };
  try {
    const page = await context.newPage();
    page.on('pageerror', error => result.errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') result.consoleErrors.push(message.text());
    });
    page.on('requestfailed', request => result.failedRequests.push({
      url: request.url(), error: request.failure()?.errorText,
    }));
    page.on('response', response => {
      if (response.status() >= 400) result.httpErrors.push({ url: response.url(), status: response.status() });
    });
    const destination = `${baseURL}/${mode}/${activity.route}`;
    result.requestedURL = destination;
    try {
      // Begin at the dashboard and follow an actual link when available.
      // A documented deep link is retained as an explicitly recorded fallback.
      await page.goto(`${baseURL}/${mode}/marble/dashboard`, {
        waitUntil: 'domcontentloaded', timeout: 12000,
      });
      await page.waitForLoadState('networkidle', { timeout: 15000 });
      if (mode === 'qapps') await require('./wait-qapps').waitQapps(page, 'marble/dashboard');
      result.steps.push(await captureStep(page, path.join(runDir, 'ui-test'), {
        baseURL, engine, mode, step: 'screen', route: 'marble/dashboard', url: page.url(),
      }));
      const link = page.locator('a[href]').filter({ visible: true });
      const hrefs = await link.evaluateAll(nodes => nodes.map(node => node.href));
      const target = new URL(destination);
      const href = hrefs.find(href => {
        const candidate = new URL(href);
        return candidate.pathname === target.pathname && candidate.search === target.search;
      });
      if (href) {
        result.navigation = 'dashboard-link';
        await link.nth(hrefs.indexOf(href)).click({ timeout: 5000 });
        await page.waitForURL(url => url.pathname === target.pathname || url.hash.includes(activity.route), { timeout: 5000 });
      } else {
        result.navigation = 'documented-or-candidate-deep-link';
        const response = await page.goto(destination, { waitUntil: 'domcontentloaded', timeout: 12000 });
        result.httpStatus = response?.status();
      }
      await page.waitForLoadState('networkidle', { timeout: 15000 });
      if (mode === 'qapps') await require('./wait-qapps').waitQapps(page, activity.route);
      result.finalURL = page.url();
      result.steps.push(await captureStep(page, path.join(runDir, 'ui-test'), {
        baseURL, engine, mode, step: 'screen', route: activity.route, url: page.url(),
      }));
      if (page.url().includes('/Login') || !login.authenticated) {
        result.errors.push('Authenticated activity not reached; login prerequisite failed');
      } else if (activity.dialog && !(result.httpStatus >= 400)) {
        const button = page.getByRole('button', { name: activity.dialog.label, exact: true });
        const anchor = page.getByRole('link', { name: activity.dialog.label, exact: true });
        result.dialogNamedTrigger = await button.or(anchor).filter({ visible: true }).count() > 0;
        const trigger = page.locator(`[id="${activity.dialog.id}-button"]`)
          .or(button).or(anchor).filter({ visible: true }).first();
        await trigger.click({ timeout: 3500 });
        // Component IDs may belong to the always-visible trigger wrapper, not the dialog.
        const dialog = page.getByRole('dialog').filter({ visible: true }).first();
        await dialog.waitFor({ state: 'visible', timeout: 3500 });
        await dialog.evaluate(async node => {
          // Vue starts the enter transition on the next frame; visibility alone can precede opacity.
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          await Promise.all(node.getAnimations({ subtree: true }).map(animation => animation.finished.catch(() => {})));
        });
        result.dialogOpened = true;
        result.steps.push(await captureStep(page, path.join(runDir, 'ui-test'), {
          baseURL, engine, mode, step: 'dialog', route: activity.route,
          dialog: activity.dialog.id, url: page.url(),
        }));
      }
      const bodyText = await page.locator('body').innerText();
      if (bodyText.includes('Error rendering section [')) {
        result.errors.push('Server-side section rendering failed (see page text)');
      }
      if (shellTemplateUnrendered(bodyText)) {
        result.errors.push('Unrendered shell template directives (see page text)');
      }
      if (result.httpStatus >= 400) result.errors.push(`HTTP ${result.httpStatus}`);
      if (result.httpErrors.length) result.errors.push('One or more HTTP resources failed (see httpErrors)');
      result.status = result.errors.length ? 'blocked' : 'captured';
    } catch (error) { result.errors.push(error.message); }
    result.finalURL = page.url();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(Array.from(document.images, image => image.decode().catch(() => {})));
    }).catch(error => result.errors.push(error.message));
    const finalStep = result.steps.at(-1);
    if (!result.errors.length && finalStep && !finalStep.error) {
      copyEvidence(finalStep.screenshot, path.join(directory, 'screen.visual.png'));
    } else {
      await page.screenshot({ path: path.join(directory, 'screen.visual.png'), fullPage: true,
        animations: 'disabled', caret: 'hide', timeout: 8000 }).catch(error => result.errors.push(error.message));
    }
    fs.writeFileSync(path.join(directory, 'page.html'), await page.content().catch(() => ''));
    fs.writeFileSync(path.join(directory, 'page.txt'), await page.locator('body').innerText().catch(() => ''));
    for (const step of result.steps) {
      if (step.error) result.errors.push(`Screenshot step ${step.step}: ${step.error}`);
    }
    if (result.errors.length) result.status = 'blocked';
  } finally {
    await context.close();
    writeJSON(reportFile, result);
  }
  return { ...result, directory };
}
async function compare(directory, captures) {
  const key = crypto.createHash('sha256').update(JSON.stringify(captures.map(capture => capture.directory))).digest('hex');
  const cacheDir = captures[0]?.directory && path.join(path.dirname(captures[0].directory), `diff-${key}`);
  if (cacheDir && fs.existsSync(path.join(cacheDir, 'comparison.json'))) {
    copyEvidence(path.join(cacheDir, 'screen.diff.visual.png'), path.join(directory, 'screen.diff.visual.png'));
    return JSON.parse(fs.readFileSync(path.join(cacheDir, 'comparison.json')));
  }
  const files = ['java', 'rust'].map(engine => path.join(directory, `screen.${engine}.visual.png`));
  if (!files.every(file => fs.existsSync(file))) return { status: 'unavailable', reason: 'Missing screenshot' };
  const images = files.map(file => PNG.sync.read(fs.readFileSync(file)));
  const width = Math.max(...images.map(image => image.width));
  const height = Math.max(...images.map(image => image.height));
  const padded = images.map(image => {
    const canvas = new PNG({ width, height, fill: true });
    PNG.bitblt(image, canvas, 0, 0, image.width, image.height, 0, 0);
    return canvas;
  });
  const diff = new PNG({ width, height });
  const pixelmatch = (await import('pixelmatch')).default;
  const differentPixels = pixelmatch(padded[0].data, padded[1].data, diff.data, width, height, { threshold: 0.1 });
  const dimensionsEqual = images[0].width === images[1].width && images[0].height === images[1].height;
  fs.writeFileSync(path.join(directory, 'screen.diff.visual.png'), PNG.sync.write(diff));
  const result = { status: captures.every(capture => capture.status === 'captured') ? 'compared' : 'diagnostic-only',
    equal: dimensionsEqual && differentPixels === 0,
    dimensions: images.map(image => ({ width: image.width, height: image.height })),
    dimensionsEqual, differentPixels, comparedPixels: width * height,
    differencePercent: differentPixels * 100 / (width * height), threshold: 0.1 };
  if (cacheDir) {
    writeJSON(path.join(cacheDir, 'comparison.json'), result);
    copyEvidence(path.join(directory, 'screen.diff.visual.png'), path.join(cacheDir, 'screen.diff.visual.png'));
  }
  return result;
}
function registerProcess(relative) {
  const process = loadProcess(relative);
  for (const mode of modes) test(`${process.slug}: ${mode}: all documented activities (best effort)`, async ({ browser }) => {
    test.setTimeout(1800000);
    const runDir = test.info().config.metadata.runDir;
    const processDir = path.join(runDir, 'ui-test', process.group, process.slug);
    const reports = [];
    for (const activity of process.activities) {
      const directory = path.join(processDir, activity.id, mode);
      const report = { ...activity, source: process.source, mode, coverage: 'blocked', captures: [] };
      if (activity.route) {
        for (const engine of ['java', 'rust']) {
          try {
            const captured = await capture(browser, engine, mode, activity, runDir);
            for (const [source, target] of [['screen.visual.png', `screen.${engine}.visual.png`],
              ['page.html', `screen.${engine}.html`], ['page.txt', `screen.${engine}.txt`]]) {
              copyEvidence(path.join(captured.directory, source), path.join(directory, target));
            }
            report.captures.push(captured);
          } catch (error) { report.captures.push({ engine, status: 'blocked', errors: [error.message] }); }
        }
        try { report.comparison = await compare(directory, report.captures); }
        catch (error) { report.comparison = { status: 'unavailable', error: error.message }; }
        if (report.captures.every(capture => capture.status === 'captured')) report.coverage = 'partial';
      } else report.reason = activity.limitation;
      writeJSON(path.join(directory, 'comparison.json'), report);
      reports.push({ id: activity.id, sourceLine: activity.sourceLine, coverage: report.coverage,
        comparison: report.comparison, report: path.relative(runDir, path.join(directory, 'comparison.json')) });
    }
    writeJSON(path.join(processDir, `${mode}.summary.json`), {
      source: process.source, mode, activities: reports,
      note: 'Evidence sweep only; no complete business-process execution is claimed.',
    });
  });
}
module.exports = { registerProcess, capture, compare, shellTemplateUnrendered };
