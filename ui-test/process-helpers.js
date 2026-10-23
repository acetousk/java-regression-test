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
 * Choose an option in a drop-down field (the `<select id="<form>_<field>">`) as a user does: open it, type
 * `search` for a server-search drop-down, then click the option whose label contains `optionText`. Java's apps
 * enhance the select with select2 and Rust's with Tom Select; both are driven by what the user sees.
 */
async function choose(page, selectId, optionText, search) {
  const select = page.locator(`#${selectId}`);
  const tomControl = page.locator(`#${selectId}-ts-control`);
  let options;
  if (await tomControl.count()) {
    await page.locator(`#${selectId}`).locator('xpath=following-sibling::div[contains(@class,"ts-wrapper")][1]')
      .locator('.ts-control').click();
    if (search !== undefined) {
      // A keystroke typed while Tom Select is still opening can be lost ("Joe" became "oe"): type once the input
      // has focus, and type again until the input holds the whole search.
      await expect(tomControl).toBeFocused();
      await expect(async () => {
        if (await tomControl.inputValue() !== search) {
          await tomControl.fill('');
          await tomControl.pressSequentially(search, { delay: 20 });
        }
        await expect(tomControl).toHaveValue(search, { timeout: 1000 });
      }).toPass({ timeout: 10000 });
    }
    options = page.locator(`#${selectId}-ts-dropdown .option`);
  } else {
    await select.locator('xpath=following-sibling::span[contains(@class,"select2")][1]')
      .locator('.select2-selection').click();
    if (search !== undefined) {
      await page.locator('.select2-container--open .select2-search__field').pressSequentially(search, { delay: 20 });
    }
    options = page.locator('.select2-container--open .select2-results__option');
  }
  const option = options.filter({ hasText: optionText }).first();
  await expect(option).toBeVisible();
  await option.click();
  await expect(select).not.toHaveValue('');
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
