const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

async function captureStep(page, directory, identity) {
  const key = crypto.createHash('sha256').update(JSON.stringify(identity)).digest('hex').slice(0, 24);
  const screenshot = path.join(directory, '_steps', `${key}.visual.png`);
  const result = { ...identity, finalURL: page.url(), screenshot, reused: fs.existsSync(screenshot) };
  if (!result.reused) {
    fs.mkdirSync(path.dirname(screenshot), { recursive: true });
    try {
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(Array.from(document.images, image => image.decode().catch(() => {})));
      });
      await page.screenshot({ path: screenshot, fullPage: true, animations: 'disabled', caret: 'hide', timeout: 8000 });
    } catch (error) {
      // A failed attempt must not become a reusable screenshot.
      if (fs.existsSync(screenshot)) fs.unlinkSync(screenshot);
      result.error = error.message;
    }
  }
  return result;
}
module.exports = { captureStep };
