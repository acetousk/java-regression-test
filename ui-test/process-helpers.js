// What a Marble ERP user does on a qapps screen, shared by the business-process activity specs.
const { expect } = require('@playwright/test');
const { login } = require('./activity-harness');

// Every activity starts signed out at Login, so it runs on its own.
const signIn = [
  {
    name: 'open Login',
    writes: true,
    run: async page => {
      await page.goto('../Login', { waitUntil: 'domcontentloaded' });
      await expect(page.locator('#login_form')).toBeVisible();
    },
  },
  { name: 'log in', writes: true, run: async page => login(page) },
];

/** The button labelled exactly `text`; qapps buttons put an icon glyph before the label. */
function button(page, text) {
  const label = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return page.getByRole('button', { name: new RegExp(`^\\W*${label}\\s*$`) }).first();
}

/** Open a container-dialog by its button text; resolves to the dialog's form. */
async function openDialog(page, buttonText, dialogId) {
  await button(page, buttonText).click();
  const form = page.locator(`#${dialogId} form`).first();
  await expect(form).toBeVisible();
  return form;
}

/**
 * Choose an option in an m-drop-down (a Quasar q-select with id `<form>_<field>`): open it, type the
 * search term for server-search drop-downs, then click the option whose label contains `optionText`.
 */
async function choose(page, selectId, optionText, search) {
  const input = page.locator(`#${selectId}`);
  await input.click();
  if (search !== undefined) await input.fill(search);
  const option = page.locator('.q-menu .q-item').filter({ hasText: optionText }).first();
  await expect(option).toBeVisible();
  await option.click();
  await expect(page.locator('.q-menu')).toHaveCount(0);
}

/** Click a submit or hidden-form link button and wait for the screen it lands on. */
async function submitTo(page, locator, url) {
  await Promise.all([page.waitForURL(url), locator.click()]);
  await page.waitForLoadState('networkidle');
}

/** The query parameter `name` of the current URL, e.g. the new record's id. */
function urlParam(page, name) {
  return new URL(page.url()).searchParams.get(name);
}

/** verify() for a step that returns an id: both engines must assign the same id. */
function sameId(label) {
  return async ids => {
    expect(ids.java, label).toBeTruthy();
    expect(ids.rust, `both engines assign the same ${label}`).toBe(ids.java);
  };
}

module.exports = { button, choose, openDialog, sameId, signIn, submitTo, urlParam };
