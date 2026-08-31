const WORKSPACE_QUERY_KEY = 'workspace';

export const COCKPIT_WINDOW_MODE = 'cockpit';
export const COCKPIT_WINDOW_NAME = 'robot-scope-cockpit-workspace';

function asUrl(locationValue) {
  if (locationValue instanceof URL) return new URL(locationValue.href);
  const href = typeof locationValue === 'string' ? locationValue : locationValue?.href;
  return new URL(href || '/', 'http://localhost');
}

function boundedInteger(value, fallback, minimum, maximum) {
  const number = Number(value);
  const candidate = Number.isFinite(number) && number > 0 ? number : fallback;
  return Math.min(maximum, Math.max(minimum, Math.floor(candidate)));
}

function boundedCoordinate(value, fallback, minimum, maximum) {
  const number = Number(value);
  const candidate = Number.isFinite(number) ? number : fallback;
  return Math.min(maximum, Math.max(minimum, Math.floor(candidate)));
}

export function workspaceWindowMode(locationValue) {
  const values = asUrl(locationValue).searchParams.getAll(WORKSPACE_QUERY_KEY);
  return values.length === 1 && values[0] === COCKPIT_WINDOW_MODE
    ? COCKPIT_WINDOW_MODE
    : null;
}

export function cockpitWindowUrl(locationValue) {
  const url = asUrl(locationValue);
  url.search = '';
  url.searchParams.set(WORKSPACE_QUERY_KEY, COCKPIT_WINDOW_MODE);
  url.hash = '#cockpit';
  return url.href;
}

export function dashboardWindowUrl(locationValue) {
  const url = asUrl(locationValue);
  url.search = '';
  url.hash = '#overview';
  return url.href;
}

export function cockpitWindowFeatures(screenValue = {}, windowValue = {}) {
  const width = boundedInteger(screenValue.availWidth, windowValue.outerWidth || 1366, 640, 7680);
  const height = boundedInteger(screenValue.availHeight, windowValue.outerHeight || 768, 480, 4320);
  const left = boundedCoordinate(screenValue.availLeft, 0, -7680, 7680);
  const top = boundedCoordinate(screenValue.availTop, 0, -4320, 4320);
  return `popup=yes,resizable=yes,scrollbars=no,width=${width},height=${height},left=${left},top=${top}`;
}

export function openCockpitWorkspaceWindow(windowValue = globalThis.window) {
  if (!windowValue?.open || !windowValue?.location) {
    return Object.freeze({ opened: false, popup: null, reason: 'unsupported' });
  }
  const url = cockpitWindowUrl(windowValue.location);
  const features = cockpitWindowFeatures(windowValue.screen, windowValue);
  const popup = windowValue.open(url, COCKPIT_WINDOW_NAME, features);
  if (!popup) return Object.freeze({ opened: false, popup: null, reason: 'blocked', url, features });
  try { popup.opener = null; } catch (_error) { /* Cross-origin browser policy may reject this assignment. */ }
  try { popup.focus(); } catch (_error) { /* The window is still open when focus is policy-blocked. */ }
  return Object.freeze({ opened: true, popup, reason: 'opened', url, features });
}

export async function toggleDocumentFullscreen(documentValue = globalThis.document) {
  if (documentValue?.fullscreenElement) {
    if (typeof documentValue.exitFullscreen !== 'function') throw new Error('Fullscreen exit is unavailable.');
    await documentValue.exitFullscreen();
    return false;
  }
  const target = documentValue?.documentElement;
  if (typeof target?.requestFullscreen !== 'function') throw new Error('Fullscreen is unavailable.');
  await target.requestFullscreen();
  return true;
}

export function initializeCockpitWindowMode({
  windowValue = globalThis.window,
  documentValue = globalThis.document,
  onOpened = () => {},
  onBlocked = () => {},
  onFullscreenError = () => {},
} = {}) {
  const mode = workspaceWindowMode(windowValue?.location);
  const dedicated = mode === COCKPIT_WINDOW_MODE;
  const launcher = documentValue?.querySelector?.('#cockpitOpenWindowButton');
  const windowBar = documentValue?.querySelector?.('#cockpitWindowBar');
  const fullscreenButton = documentValue?.querySelector?.('#cockpitFullscreenButton');
  const closeButton = documentValue?.querySelector?.('#cockpitCloseWindowButton');
  const listeners = new AbortController();

  if (dedicated) {
    documentValue.documentElement.dataset.workspaceWindow = COCKPIT_WINDOW_MODE;
    documentValue.title = 'Robot Cockpit · Robot Scope';
    if (windowBar) windowBar.hidden = false;
  }

  const syncFullscreenButton = () => {
    const active = Boolean(documentValue?.fullscreenElement);
    fullscreenButton?.setAttribute('aria-pressed', String(active));
    if (fullscreenButton) fullscreenButton.textContent = active ? '전체 화면 종료' : '브라우저 전체 화면';
  };
  const launch = () => {
    const result = openCockpitWorkspaceWindow(windowValue);
    if (result.opened) onOpened(result);
    else onBlocked(result);
  };
  const toggleFullscreen = async () => {
    try {
      await toggleDocumentFullscreen(documentValue);
      syncFullscreenButton();
    } catch (error) {
      onFullscreenError(error);
    }
  };
  const close = async () => {
    if (!dedicated) return;
    if (documentValue?.fullscreenElement && typeof documentValue.exitFullscreen === 'function') {
      try { await documentValue.exitFullscreen(); } catch (_error) { /* Closing still performs fail-safe cleanup. */ }
    }
    windowValue.close();
    windowValue.setTimeout(() => {
      if (!windowValue.closed) windowValue.location.assign(dashboardWindowUrl(windowValue.location));
    }, 100);
  };

  launcher?.addEventListener('click', launch, { signal: listeners.signal });
  fullscreenButton?.addEventListener('click', toggleFullscreen, { signal: listeners.signal });
  closeButton?.addEventListener('click', close, { signal: listeners.signal });
  documentValue?.addEventListener?.('fullscreenchange', syncFullscreenButton, { signal: listeners.signal });
  syncFullscreenButton();

  const controller = Object.freeze({
    mode,
    dedicated,
    pageFromHash(knownPages) {
      if (dedicated) return 'cockpit';
      const route = String(windowValue.location.hash || '').replace(/^#\/?/, '').trim();
      return Object.hasOwn(knownPages, route) ? route : 'overview';
    },
    resolvePage(page) { return dedicated ? 'cockpit' : page; },
    shouldReplaceHash(requested) { return Boolean(requested || dedicated); },
    destroy() { listeners.abort(); },
  });
  windowValue.RobotScopeCockpitWindow = controller;
  return controller;
}
