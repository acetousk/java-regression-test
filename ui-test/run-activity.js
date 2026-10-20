// Browser-only rerun against the persistent, isolated --hold engines. Never boots or resets them.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

async function main() {
  const [sessionFile, spec = 'find-and-create-customer'] = process.argv.slice(2);
  if (!sessionFile) throw new Error('Usage: node ui-test/run-activity.js <run>/activity-session.json [spec]');
  const session = JSON.parse(fs.readFileSync(sessionFile, 'utf8'));
  for (const key of ['MOQUI_RUN_DIR', 'MOQUI_HARNESS_STATUS_URL', 'JAVA_BASE_URL', 'RUST_BASE_URL']) {
    if (!session[key]) throw new Error(`Session missing ${key}`);
  }
  const response = await fetch(session.MOQUI_HARNESS_STATUS_URL);
  if (!response.ok) throw new Error(`Harness status HTTP ${response.status}`);
  const status = await response.json();
  if (status.error) throw new Error(`Harness failed; cannot rerun: ${status.error}`);
  if (Object.values(status.unpaired_writes).some(Boolean) || Object.values(status.waiting_at_barrier).some(Boolean)) {
    throw new Error('Harness has unfinished writes; restart the isolated engines before rerunning');
  }
  const directory = path.join(session.MOQUI_RUN_DIR, 'attempts', new Date().toISOString().replace(/:/g, '-'));
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, 'harness-before.json'), JSON.stringify(status, null, 2) + '\n');
  console.log(`Evidence: ${directory}`);
  const result = spawnSync(process.execPath, [require.resolve('@playwright/test/cli'), 'test', spec], {
    cwd: __dirname, stdio: 'inherit',
    env: { ...process.env, ...session, MOQUI_RUN_DIR: directory },
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
