import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { captureStickyLogScroll, scheduleStickyLogScroll } from '../../core/log_scroll.js';

const NAVIGATION_LOG_LIMIT = 100;
const NAVIGATION_LOG_MAX_LINES = 300;
const NAVIGATION_LOG_PHASES = new Set(['idle', 'starting', 'running', 'stopping', 'failed']);
const NAVIGATION_LOG_SOURCES = new Set(['manager', 'runtime', 'parameters']);
const ui = {
  navigationLogPhase: $('#navigationLogPhase'),
  navigationLogRuntimeState: $('#navigationLogRuntimeState'),
  navigationLogTimestamp: $('#navigationLogTimestamp'),
  navigationLogAutoScroll: $('#navigationLogAutoScroll'),
  navigationLogClear: $('#navigationLogClear'),
  navigationLogOutput: $('#navigationLogOutput'),
  navigationLogEmpty: $('#navigationLogEmpty'),
  navigationLogNotice: $('#navigationLogNotice'),
};
let navigationLogEntries = [];
let navigationLogCursor = 0;
let navigationLogLatestCursor = 0;
let navigationLogStreamId = '';
let navigationLogInitialized = false;
let navigationLogBusy = false;
let navigationLogRequestGeneration = 0;
let navigationLogRenderGeneration = 0;
let navigationLogJob = null;
let navigationLogError = false;
let navigationLogTruncated = false;
let navigationLogHasMore = false;
let initialized = false;
let getActivePage = () => '';
let getNavigationSnapshot = () => null;
let getNavigationApiAvailable = () => null;

function normalizeNavigationLogEntry(value) {
  if (!value || typeof value !== 'object') return null;
  const seq = Number(value.seq);
  const phase = typeof value.phase === 'string' ? value.phase.toLowerCase() : '';
  const source = typeof value.source === 'string' ? value.source.toLowerCase() : '';
  const timestamp = typeof value.timestamp === 'string' ? value.timestamp : '';
  if (!Number.isSafeInteger(seq) || seq <= 0) return null;
  if (!NAVIGATION_LOG_PHASES.has(phase) || !NAVIGATION_LOG_SOURCES.has(source)) return null;
  if (!timestamp || timestamp.length > 64 || !Number.isFinite(Date.parse(timestamp))) return null;
  if (typeof value.message !== 'string') return null;
  const message = value.message.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 320);
  if (!message) return null;
  return { seq, timestamp, phase, source, message };
}

function navigationLogTimestampLabel(value, includeDate = false) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '—';
  try {
    const options = includeDate
      ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
      : { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    return new Intl.DateTimeFormat('ko-KR', options).format(date);
  } catch (_) {
    return date.toISOString().slice(includeDate ? 5 : 11, 19).replace('T', ' ');
  }
}

function scheduleNavigationLogScroll(scrollSnapshot, { forceBottom = false } = {}) {
  const generation = ++navigationLogRenderGeneration;
  scheduleStickyLogScroll(ui.navigationLogOutput, scrollSnapshot, {
    forceBottom,
    shouldApply: () => (
      generation === navigationLogRenderGeneration && getActivePage() === 'navigation'
    ),
  });
}

function renderNavigationLog() {
  if (!ui.navigationLogOutput) return;
  const logScrollSnapshot = captureStickyLogScroll(
    ui.navigationLogOutput,
    ui.navigationLogAutoScroll.checked,
  );
  const lines = navigationLogEntries.map((entry) => (
    `[${navigationLogTimestampLabel(entry.timestamp)}] [${entry.phase.toUpperCase()}] [${entry.source.toUpperCase()}] ${entry.message}`
  ));
  ui.navigationLogOutput.textContent = lines.join('\n');
  ui.navigationLogOutput.setAttribute('aria-busy', navigationLogBusy ? 'true' : 'false');
  ui.navigationLogEmpty.hidden = lines.length > 0;
  ui.navigationLogEmpty.textContent = navigationLogError
    ? 'Navigation 로그 API에 연결할 수 없습니다.'
    : navigationLogBusy ? '서버 로그를 불러오고 있습니다.' : '표시할 Navigation 로그가 없습니다.';
  ui.navigationLogClear.disabled = lines.length === 0;

  const lastEntry = navigationLogEntries[navigationLogEntries.length - 1] || null;
  const phase = navigationLogJob?.phase || lastEntry?.phase || 'idle';
  const reportedRuntimeState = String(getNavigationSnapshot()?.pipeline?.state || '').toLowerCase();
  const runtimeState = NAVIGATION_LOG_PHASES.has(reportedRuntimeState)
    ? reportedRuntimeState : getNavigationApiAvailable() === false ? 'offline' : 'waiting';
  ui.navigationLogPhase.textContent = NAVIGATION_LOG_PHASES.has(phase) ? phase.toUpperCase() : 'IDLE';
  ui.navigationLogRuntimeState.textContent = runtimeState.toUpperCase();
  ui.navigationLogTimestamp.textContent = lastEntry ? navigationLogTimestampLabel(lastEntry.timestamp, true) : '—';
  ui.navigationLogPhase.dataset.state = phase;
  ui.navigationLogRuntimeState.dataset.state = runtimeState;

  if (navigationLogError) {
    ui.navigationLogNotice.textContent = '로그 상태를 불러오지 못했습니다. Navigation 상태와 제어 기능은 별도로 갱신됩니다.';
    ui.navigationLogNotice.classList.add('is-error');
  } else if (navigationLogHasMore) {
    ui.navigationLogNotice.textContent = '남은 정제 로그를 다음 갱신에서 이어서 불러옵니다.';
    ui.navigationLogNotice.classList.remove('is-error');
  } else if (navigationLogTruncated) {
    ui.navigationLogNotice.textContent = '서버 보존 범위보다 오래된 로그는 생략되었습니다. 최신 정제 로그만 표시합니다.';
    ui.navigationLogNotice.classList.remove('is-error');
  } else {
    ui.navigationLogNotice.textContent = '서버가 공개한 고정·정제 로그만 표시합니다. CLEAR VIEW는 이 브라우저 화면만 비웁니다.';
    ui.navigationLogNotice.classList.remove('is-error');
  }
  scheduleNavigationLogScroll(logScrollSnapshot);
}

function resetNavigationLogView(streamId = '') {
  navigationLogEntries = [];
  navigationLogCursor = 0;
  navigationLogLatestCursor = 0;
  navigationLogStreamId = streamId;
  navigationLogInitialized = false;
  navigationLogJob = null;
  navigationLogTruncated = false;
  navigationLogHasMore = false;
}

function applyNavigationLogPayload(payload, requestedAfter) {
  if (!payload || typeof payload !== 'object') throw new Error('invalid navigation log response');
  const streamId = typeof payload.stream_id === 'string' && /^[0-9a-f]{32}$/.test(payload.stream_id)
    ? payload.stream_id : '';
  const cursor = Number(payload.cursor);
  const latestCursor = Number(payload.latest_cursor);
  if (!streamId || !Number.isSafeInteger(cursor) || cursor < 0 ||
      !Number.isSafeInteger(latestCursor) || latestCursor < 0 || cursor > latestCursor ||
      !Array.isArray(payload.entries)) throw new Error('invalid navigation log response');

  const streamChanged = Boolean(navigationLogStreamId && navigationLogStreamId !== streamId);
  const cursorOutsideWindow = requestedAfter > 0 && requestedAfter > latestCursor;
  const continuityLost = requestedAfter > 0 && payload.truncated === true;
  if (streamChanged) resetNavigationLogView(streamId);
  if ((streamChanged && requestedAfter > 0) || cursorOutsideWindow || continuityLost) {
    resetNavigationLogView(streamId);
    return { refetchTail: true };
  }

  const phase = typeof payload.job?.phase === 'string' ? payload.job.phase.toLowerCase() : '';
  navigationLogJob = NAVIGATION_LOG_PHASES.has(phase)
    ? { phase, startedAt: typeof payload.job?.started_at === 'string' ? payload.job.started_at : null }
    : null;
  if (payload.entries.length > NAVIGATION_LOG_LIMIT) throw new Error('invalid navigation log response');
  const entries = payload.entries.map(normalizeNavigationLogEntry);
  if (entries.some((entry) => !entry)) throw new Error('invalid navigation log response');
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const previous = entries[index - 1];
    if (entry.seq > latestCursor || (requestedAfter > 0 && entry.seq <= requestedAfter) ||
        (previous && entry.seq <= previous.seq)) throw new Error('invalid navigation log response');
  }
  if (entries.length > 0 && entries[entries.length - 1].seq !== cursor) {
    throw new Error('invalid navigation log response');
  }
  const merged = requestedAfter === 0 ? entries : navigationLogEntries.concat(entries);
  const bySequence = new Map();
  merged.forEach((entry) => bySequence.set(entry.seq, entry));
  navigationLogEntries = [...bySequence.values()]
    .sort((left, right) => left.seq - right.seq)
    .slice(-NAVIGATION_LOG_MAX_LINES);
  navigationLogStreamId = streamId;
  navigationLogCursor = cursor;
  navigationLogLatestCursor = latestCursor;
  navigationLogInitialized = true;
  navigationLogError = false;
  navigationLogTruncated = payload.truncated === true;
  navigationLogHasMore = payload.has_more === true && cursor < latestCursor;
  return { refetchTail: false };
}

function clearNavigationLogView() {
  navigationLogRequestGeneration += 1;
  navigationLogRenderGeneration += 1;
  navigationLogBusy = false;
  navigationLogEntries = [];
  navigationLogCursor = navigationLogLatestCursor;
  navigationLogInitialized = Boolean(navigationLogStreamId);
  navigationLogError = false;
  navigationLogTruncated = false;
  navigationLogHasMore = false;
  renderNavigationLog();
}

function invalidateNavigationLogRequests() {
  navigationLogRequestGeneration += 1;
  navigationLogRenderGeneration += 1;
  navigationLogBusy = false;
}

async function refreshNavigationLogs(force = false) {
  if (getActivePage() !== 'navigation' || document.hidden || navigationLogBusy) return;
  navigationLogBusy = true;
  navigationLogError = false;
  const generation = ++navigationLogRequestGeneration;
  let requestedAfter = navigationLogInitialized ? navigationLogCursor : 0;
  let tailRefetched = requestedAfter === 0;
  renderNavigationLog();
  try {
    while (true) {
      const payload = await api(`/api/v1/navigation/logs?after=${requestedAfter}&limit=${NAVIGATION_LOG_LIMIT}`);
      if (generation !== navigationLogRequestGeneration || getActivePage() !== 'navigation' || document.hidden) return;
      const result = applyNavigationLogPayload(payload, requestedAfter);
      if (result.refetchTail && !tailRefetched) {
        requestedAfter = 0;
        tailRefetched = true;
        continue;
      }
      break;
    }
  } catch (_) {
    if (generation !== navigationLogRequestGeneration) return;
    navigationLogError = true;
  } finally {
    if (generation === navigationLogRequestGeneration) {
      navigationLogBusy = false;
      renderNavigationLog();
    }
  }
}

export function initializeNavigationLogFeature(options = {}) {
  if (initialized) return feature;
  initialized = true;
  getActivePage = options.getActivePage || getActivePage;
  getNavigationSnapshot = options.getNavigationSnapshot || getNavigationSnapshot;
  getNavigationApiAvailable = options.getNavigationApiAvailable || getNavigationApiAvailable;
  ui.navigationLogAutoScroll?.addEventListener('change', () => {
    navigationLogRenderGeneration += 1;
    if (ui.navigationLogAutoScroll.checked) {
      scheduleNavigationLogScroll(captureStickyLogScroll(ui.navigationLogOutput, false), { forceBottom: true });
    }
  });
  ui.navigationLogClear?.addEventListener('click', clearNavigationLogView);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) invalidateNavigationLogRequests();
    else if (getActivePage() === 'navigation') void refreshNavigationLogs(true);
  });
  window.addEventListener('pagehide', invalidateNavigationLogRequests);
  window.addEventListener('pageshow', () => {
    invalidateNavigationLogRequests();
    if (getActivePage() === 'navigation') void refreshNavigationLogs(true);
  });
  setInterval(refreshNavigationLogs, 1000);
  renderNavigationLog();
  return feature;
}

const feature = Object.freeze({
  render: renderNavigationLog,
  refresh: refreshNavigationLogs,
  invalidate: invalidateNavigationLogRequests,
  onPageChange(previousPage, activePage) {
    if (previousPage === 'navigation' && activePage !== 'navigation') invalidateNavigationLogRequests();
    if (activePage === 'navigation') void refreshNavigationLogs(true);
  },
});
