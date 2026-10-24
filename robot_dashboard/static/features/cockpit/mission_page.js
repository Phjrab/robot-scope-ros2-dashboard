import { createMissionWorkspace } from '../mission_route/workspace.js';
import { createMissionPanel } from './panels/mission_panel.js';

// Reuse the workspace's client/owner: opening this page never starts a mission.
export function initializeMissionPage({ client, navigationAdapter, getContext, document: doc = globalThis.document }) {
  const host = doc?.querySelector?.('#dashboardMissionHost');
  if (!host) return null;
  const help = doc.querySelector('[data-page="missions"] .mission-page-help');
  if (help) help.textContent = '저장 지도를 불러와 방문과 작업을 편집하고 저장·검사하세요. E1 경로도 미션 초안으로 가져올 수 있습니다. 새 실행 만들기와 실행 시작은 별도 단계이며, 실행 조건이 부족하면 이유를 표시합니다. 화면 이동·새로고침은 실행을 시작하거나 중지하지 않습니다.';
  const panel = createMissionWorkspace({ host, client, navigationAdapter, getContext, document: doc });
  const advanced = doc.createElement('details');
  const summary = doc.createElement('summary'); summary.textContent = '기존 주석 미션 · 고급'; advanced.append(summary); host.append(advanced);
  const legacy = createMissionPanel({ authoring: true, client, navigationAdapter, getContext, document: doc }); legacy.mount(advanced);
  let activePage = '';
  const sync = () => { if (activePage === 'missions' && !doc.hidden) { panel.activate(); legacy.activate(); } else { panel.deactivate(); legacy.deactivate(); } };
  const change = (event) => { activePage = String(event.detail?.activePage || ''); sync(); };
  const hide = () => { panel.deactivate(); legacy.deactivate(); };
  doc.addEventListener('robot-scope:page-change', change);
  doc.addEventListener('visibilitychange', sync);
  globalThis.addEventListener?.('pagehide', hide);
  globalThis.addEventListener?.('pageshow', sync);
  return { destroy() {
    doc.removeEventListener('robot-scope:page-change', change);
    doc.removeEventListener('visibilitychange', sync);
    globalThis.removeEventListener?.('pagehide', hide);
    globalThis.removeEventListener?.('pageshow', sync);
    panel.destroy(); legacy.destroy(); advanced.remove();
  } };
}
