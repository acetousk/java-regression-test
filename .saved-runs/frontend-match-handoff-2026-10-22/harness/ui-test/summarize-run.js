const fs = require('node:fs');
const path = require('node:path');

function files(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? files(file) : [file];
  });
}
module.exports = async config => {
  const runDir = config.metadata.runDir;
  const uiDir = path.join(runDir, 'ui-test');
  const summaries = ['walkthroughs', 'process-library'].flatMap(group =>
    files(path.join(uiDir, group)).filter(file => file.endsWith('.summary.json')));
  if (!summaries.length) return;
  const result = { runDir, documents: 0, documentModes: summaries.length, activityModes: 0,
    partial: 0, blocked: 0, screenshots: 0, comparisons: 0, diagnosticComparisons: 0,
    visualMatches: 0, visualMismatches: 0, completeWorkflows: 0,
    uniqueCaptures: 0, uniqueScreenshots: 0, openedDialogs: 0, captureStatuses: {},
    byMode: {}, processes: [],
    note: 'Best-effort read-only evidence sweep, not a complete workflow suite. Entry candidates and error pages are not activity coverage. Reused captures are explicitly identified.',
  };
  const documents = new Set();
  for (const file of summaries) {
    const summary = JSON.parse(fs.readFileSync(file));
    documents.add(summary.source);
    const counts = result.byMode[summary.mode] ||= { partial: 0, blocked: 0, comparisons: 0, visualMismatches: 0 };
    for (const activity of summary.activities) {
      result.activityModes++;
      result[activity.coverage]++;
      counts[activity.coverage]++;
      if (activity.comparison?.status === 'compared' || activity.comparison?.status === 'diagnostic-only') {
        result.comparisons++;
        counts.comparisons++;
        if (activity.comparison.status === 'diagnostic-only') result.diagnosticComparisons++;
        if (activity.comparison.equal) result.visualMatches++;
        else { result.visualMismatches++; counts.visualMismatches++; }
      }
    }
    result.processes.push({ source: summary.source, mode: summary.mode,
      activities: summary.activities.length, summary: path.relative(runDir, file) });
  }
  result.documents = documents.size;
  for (const file of files(path.join(uiDir, '_captures')).filter(file => path.basename(file) === 'capture.json')) {
    const capture = JSON.parse(fs.readFileSync(file));
    result.uniqueCaptures++;
    if (fs.existsSync(path.join(path.dirname(file), 'screen.visual.png'))) result.uniqueScreenshots++;
    if (capture.dialogOpened) result.openedDialogs++;
    const key = `${capture.engine}/${capture.mode}/${capture.status}`;
    result.captureStatuses[key] = (result.captureStatuses[key] || 0) + 1;
  }
  result.screenshots = ['walkthroughs', 'process-library'].flatMap(group => files(path.join(uiDir, group)))
    .filter(file => /screen\.(java|rust)\.visual\.png$/.test(file)).length;
  fs.writeFileSync(path.join(uiDir, 'summary.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(`\nEvidence sweep: ${result.documents} documents; ${result.activityModes} activity/mode records; ${result.screenshots} screenshots; ${result.blocked} blocked; ${result.completeWorkflows} complete workflows.\nSummary: ${path.join(uiDir, 'summary.json')}`);
  // Never turn a completed data collection into a false parity/workflow pass.
  if (result.blocked || result.partial || result.visualMismatches) {
    throw new Error('Evidence collected, but the business-process/visual gate is incomplete or failed; see ui-test/summary.json');
  }
};
