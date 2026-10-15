import { requestId } from './state.js';
export function createPlanClient(fetchValue = globalThis.fetch.bind(globalThis)) {
  async function api(url, body, method = 'POST') {
    const response = await fetchValue(url, body === undefined ? { credentials: 'same-origin' } : { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await response.json(); if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : '요청 형식 또는 서버 상태를 확인하세요.'); error.status = response.status; throw error; } return data;
  }
  const pins = (entry) => ({ revision: entry.revision, request_id: requestId() });
  return {
    list: () => api('/api/v1/mission-plans'), runs: () => api('/api/v1/mission-runs'),
    run: (identifier) => api(`/api/v1/mission-runs/${identifier}`),
    exportRun: (identifier) => api(`/api/v1/mission-runs/${identifier}/export`),
    remove: (entry) => api(`/api/v1/mission-plans/${entry.id}`, pins(entry), 'DELETE'),
    save: (draft, saved, copy = false) => api(saved?.id && !copy ? `/api/v1/mission-plans/${saved.id}` : '/api/v1/mission-plans', { ...draft, request_id: requestId(), ...(saved?.id && !copy ? { base_revision: saved.revision } : {}) }, saved?.id && !copy ? 'PATCH' : 'POST'),
    validate: (entry) => api(`/api/v1/mission-plans/${entry.id}/validate`, pins(entry)),
    preview: (entry, start = null) => api(`/api/v1/mission-plans/${entry.id}/plan-preview`, { ...pins(entry), start_source: start ? 'hypothetical_preview_start' : 'current_operational_pose', start }),
    compile: (entry) => api(`/api/v1/mission-plans/${entry.id}/compile`, pins(entry)),
    createRun: (entry) => api(`/api/v1/mission-plans/${entry.id}/runs`, pins(entry)),
    // An uncertain mutation keeps the same request ID until an explicit refresh
    // resolves it. Calling retry() never constructs another action payload.
    action: (run, action, token, key = requestId()) => api(`/api/v1/mission-runs/${run}/${action}`, { request_id: key, confirmation_token: token || null }),
    maps: () => api('/api/v1/saved-maps'), routes: () => api('/api/v1/routes'), route: (routeId) => api(`/api/v1/routes/${routeId}`), routeDraft: (routeId) => api(`/api/v1/mission-route-drafts/${routeId}`),
    map: async (mapId) => { const [data, family, annotations] = await Promise.all(['data', 'family', 'annotations'].map((part) => api(`/api/v1/saved-maps/${mapId}/${part}`))); return { data, family, annotations }; },
  };
}
