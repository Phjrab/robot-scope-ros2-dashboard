import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

function functionSource(name, nextName) {
  const starts = [
    appSource.indexOf(`function ${name}(`),
    appSource.indexOf(`async function ${name}(`),
  ].filter((value) => value >= 0);
  const start = starts.length ? Math.min(...starts) : -1;
  const ends = [
    appSource.indexOf(`\nfunction ${nextName}(`, start),
    appSource.indexOf(`\nasync function ${nextName}(`, start),
  ].filter((value) => value > start);
  const end = ends.length ? Math.min(...ends) : -1;
  assert.ok(start >= 0 && end > start, `${name} source must exist`);
  return appSource.slice(start, end);
}

test('Navigation exposes a terminal-shaped read-only sanitized event view', () => {
  const start = indexSource.indexOf('<article class="panel navigation-log-panel"');
  const end = indexSource.indexOf('</article>', start) + '</article>'.length;
  const panel = indexSource.slice(start, end);
  assert.ok(start >= 0 && end > start);
  for (const id of [
    'navigationLogPhase', 'navigationLogRuntimeState', 'navigationLogTimestamp',
    'navigationLogAutoScroll', 'navigationLogClear', 'navigationLogOutput',
    'navigationLogEmpty', 'navigationLogNotice',
  ]) assert.match(panel, new RegExp(`id="${id}"`));
  assert.match(panel, /<pre[^>]+role="log"[^>]*>/);
  assert.match(panel, /READ-ONLY · SANITIZED EVENTS/);
  assert.doesNotMatch(panel, /contenteditable|type="(?:text|password)"|COPY|command/i);
  assert.equal((panel.match(/<input\b/g) || []).length, 1);
  assert.match(panel, /navigationLogAutoScroll" type="checkbox"/);
});

test('log polling uses only the fixed bounded GET API and its own generation', () => {
  const refresh = functionSource('refreshNavigationLogs', 'applyNavigationSnapshot');
  assert.match(refresh, /api\(`\/api\/v1\/navigation\/logs\?after=\$\{requestedAfter\}&limit=\$\{NAVIGATION_LOG_LIMIT\}`\)/);
  assert.match(appSource, /const NAVIGATION_LOG_LIMIT = 100/);
  assert.match(refresh, /const generation = \+\+navigationLogRequestGeneration/);
  assert.match(refresh, /generation !== navigationLogRequestGeneration/);
  assert.doesNotMatch(refresh, /navigationStatusRequestGeneration|method:\s*'POST'|body:|fetch\(/);
});

test('entries are strictly allowlisted, bounded and rendered through textContent only', () => {
  const normalize = functionSource('normalizeNavigationLogEntry', 'navigationLogTimestampLabel');
  const render = functionSource('renderNavigationLog', 'resetNavigationLogView');
  const context = {};
  vm.runInNewContext(`
    const NAVIGATION_LOG_PHASES = new Set(['idle', 'starting', 'running', 'stopping', 'failed']);
    const NAVIGATION_LOG_SOURCES = new Set(['manager', 'runtime', 'parameters']);
    ${normalize}
    this.normalize = normalizeNavigationLogEntry;
  `, context);
  assert.equal(context.normalize({ seq: 1, timestamp: '2026-08-13T01:02:03Z', phase: 'running', source: 'runtime', message: 'ready' }).message, 'ready');
  assert.equal(context.normalize({ seq: 1, timestamp: '2026-08-13T01:02:03Z', phase: 'running', source: 'shell', message: 'bad' }), null);
  assert.equal(context.normalize({ seq: 1, timestamp: 'bad', phase: 'running', source: 'runtime', message: 'bad' }), null);
  assert.equal(context.normalize({ seq: 1, timestamp: '2026-08-13T01:02:03Z', phase: 'running', source: 'runtime', message: 'x'.repeat(400) }).message.length, 320);
  assert.match(render, /navigationLogOutput\.textContent = lines\.join/);
  assert.doesNotMatch(render, /innerHTML|insertAdjacentHTML|job_id/);
});

test('stream changes and lost cursor continuity clear the local buffer and request one tail', () => {
  const normalize = functionSource('normalizeNavigationLogEntry', 'navigationLogTimestampLabel');
  const reset = functionSource('resetNavigationLogView', 'applyNavigationLogPayload');
  const apply = functionSource('applyNavigationLogPayload', 'clearNavigationLogView');
  const context = {};
  vm.runInNewContext(`
    const NAVIGATION_LOG_LIMIT = 100;
    const NAVIGATION_LOG_MAX_LINES = 300;
    const NAVIGATION_LOG_PHASES = new Set(['idle', 'starting', 'running', 'stopping', 'failed']);
    const NAVIGATION_LOG_SOURCES = new Set(['manager', 'runtime', 'parameters']);
    let navigationLogEntries = [];
    let navigationLogCursor = 0;
    let navigationLogLatestCursor = 0;
    let navigationLogStreamId = '';
    let navigationLogInitialized = false;
    let navigationLogJob = null;
    let navigationLogError = false;
    let navigationLogTruncated = false;
    let navigationLogHasMore = false;
    ${normalize}
    ${reset}
    ${apply}
    this.apply = applyNavigationLogPayload;
    this.state = () => ({ entries: navigationLogEntries, cursor: navigationLogCursor, stream: navigationLogStreamId });
  `, context);
  const entry = (seq) => ({ seq, timestamp: '2026-08-13T01:02:03Z', job_id: null, phase: 'running', source: 'manager', message: `event ${seq}` });
  const payload = (stream, latest, entries = [], extra = {}) => ({
    stream_id: stream, job: { id: null, phase: 'running', started_at: null }, entries,
    cursor: entries.at(-1)?.seq ?? latest, latest_cursor: latest, truncated: false, has_more: false,
    limits: { max_entries: 100, max_message_chars: 320 }, ...extra,
  });
  const streamA = 'a'.repeat(32);
  const streamB = 'b'.repeat(32);
  assert.equal(context.apply(payload(streamA, 1, [entry(1)]), 0).refetchTail, false);
  assert.equal(context.state().entries.length, 1);
  assert.equal(context.apply(payload(streamB, 2, [entry(2)]), 1).refetchTail, true);
  assert.equal(context.state().entries.length, 0);
  assert.equal(context.apply(payload(streamB, 2, [entry(2)]), 0).refetchTail, false);
  assert.equal(context.apply(payload(streamB, 1, [], { cursor: 1, truncated: true }), 2).refetchTail, true);
  assert.equal(context.state().entries.length, 0);
});

test('clear and auto-scroll stay client-only and Safari page lifecycle rejects stale work', () => {
  const clear = functionSource('clearNavigationLogView', 'invalidateNavigationLogRequests');
  const scroll = functionSource('scheduleNavigationLogScroll', 'renderNavigationLog');
  const stickyStart = appSource.indexOf('function scheduleStickyLogScroll(');
  const stickyEnd = appSource.indexOf('// LiDAR identity is intentionally resolved', stickyStart);
  const stickyScroll = appSource.slice(stickyStart, stickyEnd);
  assert.match(clear, /navigationLogEntries = \[\]/);
  assert.match(clear, /navigationLogCursor = navigationLogLatestCursor/);
  assert.match(clear, /navigationLogRequestGeneration \+= 1/);
  assert.doesNotMatch(clear, /api\(|fetch\(|POST|DELETE/);
  assert.match(scroll, /scheduleStickyLogScroll/);
  assert.match(scroll, /generation === navigationLogRenderGeneration/);
  assert.match(scroll, /activePage === 'navigation'/);
  assert.match(stickyScroll, /requestAnimationFrame/);
  assert.match(stickyScroll, /Math\.abs\([\s\S]*?renderedScrollTop/);
  assert.match(appSource, /previousPage === 'navigation' && activePage !== 'navigation'[\s\S]*?invalidateNavigationLogRequests\(\)/);
  assert.match(appSource, /visibilitychange[\s\S]*?invalidateNavigationLogRequests\(\)/);
  assert.match(appSource, /pagehide[\s\S]*?invalidateNavigationLogRequests\(\)/);
  assert.match(appSource, /pageshow[\s\S]*?invalidateNavigationLogRequests\(\)[\s\S]*?refreshNavigationLogs\(true\)/);
  assert.match(appSource, /setInterval\(refreshNavigationLogs, 1000\)/);
});

test('console remains usable on Safari and narrow mobile layouts', () => {
  assert.match(stylesSource, /\.navigation-log-output \{[^}]*overflow:auto[^}]*-webkit-overflow-scrolling:touch[^}]*white-space:pre-wrap/s);
  assert.match(stylesSource, /@media \(max-width: 800px\)[\s\S]*?\.navigation-log-header \{ align-items:stretch; flex-direction:column; \}/);
  assert.match(stylesSource, /@media \(max-width: 520px\)[\s\S]*?\.navigation-log-summary \{ grid-template-columns:1fr; \}/);
});

test('idle readiness stays WAIT until a navigation pipeline is active', () => {
  const render = functionSource('renderNavigationStatus', 'normalizeNavigationLogEntry');
  assert.match(render, /const needsInitialPose = pipelineRunning && key === 'localization' && value === false/);
  assert.match(render, /const blocked = pipelineRunning && value === false && !needsInitialPose/);
  assert.match(render, /needsInitialPose \? 'NEED POSE' : blocked \? 'BLOCKED' : 'WAIT'/);
  assert.match(render, /pipelineActive \? '초기 위치 필요' : 'START NAV2 후 초기 위치 필요'/);
});
