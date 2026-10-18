const DIAGNOSTICS_MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024;
let requestSequence = 0;

function createBrowserSessionId() {
  const generated = globalThis.crypto?.randomUUID?.();
  if (generated) return generated;
  return `browser_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
}

const browserSessionId = createBrowserSessionId();

export function operatorRequestHeaders(headers = {}) {
  requestSequence = Math.min(Number.MAX_SAFE_INTEGER, requestSequence + 1);
  return {
    ...headers,
    'Content-Type': 'application/json',
    'X-Robot-Scope-Browser-Session': browserSessionId,
    'X-Robot-Scope-Request-Sequence': String(requestSequence),
  };
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: operatorRequestHeaders(options.headers || {}),
    cache: 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function downloadApi(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: operatorRequestHeaders(options.headers || {}),
    cache: 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.headers.get('Content-Type')?.split(';', 1)[0] !== 'application/zip') {
    throw new Error('diagnostics response is not a ZIP bundle');
  }
  const blob = await response.blob();
  if (blob.size <= 0 || blob.size > DIAGNOSTICS_MAX_DOWNLOAD_BYTES) {
    throw new Error('diagnostics bundle exceeds the browser size limit');
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="(robot-scope-diagnostics-[0-9]{8}T[0-9]{6}Z\.zip)"/);
  return { blob, filename: match?.[1] || 'robot-scope-diagnostics.zip' };
}

export async function latestApi(path, seq) {
  const response = await fetch(`${path}?since=${encodeURIComponent(seq)}`, { cache: 'no-store' });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}
