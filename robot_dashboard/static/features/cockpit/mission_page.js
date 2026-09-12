import { createMissionPanel } from './panels/mission_panel.js';

// Reuse the workspace's client/owner: opening this page never starts a mission.
export function initializeMissionPage({ client, navigationAdapter, getContext, document: doc = globalThis.document }) {
  const host = doc?.querySelector?.('#dashboardMissionHost');
  if (!host) return null;
  const panel = createMissionPanel({ client, navigationAdapter, getContext, document: doc });
  panel.mount(host);
  let activePage = '';
  const sync = () => { if (activePage === 'missions' && !doc.hidden) panel.activate(); else panel.deactivate(); };
  const change = (event) => { activePage = String(event.detail?.activePage || ''); sync(); };
  const hide = () => panel.deactivate();
  doc.addEventListener('robot-scope:page-change', change);
  doc.addEventListener('visibilitychange', sync);
  globalThis.addEventListener?.('pagehide', hide);
  globalThis.addEventListener?.('pageshow', sync);
  return { destroy() {
    doc.removeEventListener('robot-scope:page-change', change);
    doc.removeEventListener('visibilitychange', sync);
    globalThis.removeEventListener?.('pagehide', hide);
    globalThis.removeEventListener?.('pageshow', sync);
    panel.destroy();
  } };
}
