import {createTransport} from './transport.js';

const config = JSON.parse(document.querySelector('#expansion-config').textContent);
const host = document.querySelector('#expansion-host');
const nav = document.querySelector('#expansion-nav');
const status = document.querySelector('#expansion-status');
const sessionPanel = document.querySelector('#expansion-session');
const login = document.querySelector('#expansion-login');
const codeInput = document.querySelector('#expansion-code');
const activeSession = document.querySelector('#expansion-session-active');
const sessionInfo = document.querySelector('#expansion-session-info');
const sessionStatus = document.querySelector('#expansion-session-status');
const reviewSession = config.auth === 'REVIEW_SESSION';
const secureSession = reviewSession && location.protocol === 'https:';
const buttons = new Map();
const features = [
  ['multimap', '여러 지도 합치기'],
  ['scene', '장애물 3D 관측'],
  ['cones', '콘 표시'],
  ['replay', '주행 기록 재생'],
  ['diagnostics', '성능 진단 안내'],
];
let current = null, currentName = null, generation = 0, closed = false;
let sessionRole = null, authenticated = false, sessionEpoch = 0;
let sessionTimer = null, sessionAbort = null, sessionBusy = false;

function localFeature(name) {
  return name === 'replay' || name === 'diagnostics';
}
function unavailable(name) {
  if (name === 'diagnostics') return null;
  const flag = name === 'cones' ? 'scene' : name;
  if (!config.flags[flag]) return `FEATURE_DISABLED · 기능이 꺼져 있습니다. 관리자에게 ${flag === 'replay' ? '로컬 기록 재생' : '해당 기능'} 활성화를 요청하세요.`;
  if (name === 'replay') return null;
  if (reviewSession && !secureSession) return 'HTTPS_REQUIRED · 관리자에게 HTTPS 주소와 인증서 신뢰 설정을 확인하세요. 연결을 준비하면 검토 코드를 입력할 수 있습니다.';
  if (config.auth === 'BLOCKED_AUTH') return 'BLOCKED_AUTH · 서버 인증이 미연결입니다. 관리자의 HTTPS·검토 세션 설정이 필요합니다.';
  if (reviewSession && !authenticated) return 'LOGIN_REQUIRED · 일회용 검토 코드로 로그인해 주세요.';
  return null;
}
function syncSession() {
  sessionPanel.hidden = !reviewSession;
  login.hidden = !secureSession || authenticated || sessionBusy;
  activeSession.hidden = !authenticated;
  for (const [name, button] of buttons) {
    button.title = unavailable(name) || (sessionRole === 'read' && name === 'multimap' ? '읽기 권한 · 조회·비교 가능' : '열기');
  }
}
function dispose() {
  current?.destroy();
  current = null;
  currentName = null;
  host.replaceChildren();
}
function clearSession(message, {preserveReplay = false, pending = false} = {}) {
  sessionEpoch++;
  sessionAbort?.abort();
  sessionAbort = null;
  clearTimeout(sessionTimer);
  sessionTimer = null;
  sessionRole = null;
  authenticated = false;
  sessionBusy = pending;
  codeInput.value = '';
  sessionInfo.textContent = '';
  if (!(preserveReplay && localFeature(currentName))) {
    generation++;
    dispose();
    for (const button of buttons.values()) button.setAttribute('aria-pressed', 'false');
  }
  sessionStatus.textContent = message;
  syncSession();
}
function initialFeature() {
  const fragment = location.hash.slice(1);
  if (buttons.has(fragment)) return fragment;
  return ['multimap', 'scene', 'replay'].find(name => config.flags[name]) || 'multimap';
}
function installSession(value, epoch) {
  if (closed || epoch !== sessionEpoch) return false;
  if (!value || !['read', 'review'].includes(value.role) || !Number.isSafeInteger(value.remaining_seconds) || value.remaining_seconds <= 0) throw new Error('SESSION_INVALID');
  sessionRole = value.role;
  authenticated = true;
  sessionBusy = false;
  sessionInfo.textContent = value.role === 'review' ? '검토 권한 · 계산·수락·사본 저장 가능' : '읽기 권한 · 조회·비교 가능';
  sessionStatus.textContent = '세션이 연결되었습니다.';
  syncSession();
  clearTimeout(sessionTimer);
  sessionTimer = setTimeout(() => clearSession('세션이 만료되었습니다. 다시 로그인해 주세요.', {preserveReplay: true}), Math.min(value.remaining_seconds * 1000, 2147483647));
  return true;
}
function openAfterLogin() {
  if (!localFeature(currentName)) open(currentName || initialFeature());
}
async function checkSession() {
  const epoch = ++sessionEpoch;
  sessionAbort?.abort();
  sessionAbort = new AbortController();
  try {
    const value = await createTransport({signal: sessionAbort.signal})('/api/v1/extensions/session');
    if (installSession(value, epoch)) openAfterLogin();
  } catch {
    if (!closed && epoch === sessionEpoch) clearSession('로그인이 필요합니다.', {preserveReplay: true});
  }
}
function stylesheet(name) {
  const href = `/static/features/${name}`;
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet'; link.href = href; document.head.append(link);
}
function showError(error) {
  const message = error.message || String(error);
  let explanation = '요청을 완료하지 못했습니다. 상태를 확인하고 다시 시도하세요.';
  if (/503|BLOCKED_INPUTS|UNAVAILABLE/.test(message)) explanation = 'UNAVAILABLE · 지도 또는 관측 데이터 제공자가 미연결입니다. 관리자에게 입력 구성을 확인하세요.';
  else if (/403/.test(message)) explanation = '권한 부족 · 현재 권한 또는 HTTPS 접속 주소를 확인하세요.';
  else if (/409/.test(message)) explanation = '지도·관측 정보가 변경되었습니다. 최신 자료를 다시 선택하세요.';
  status.textContent = `${explanation} ${message}`;
}
async function open(name) {
  if (closed || !buttons.has(name)) return;
  const mine = ++generation;
  dispose();
  currentName = name;
  history.replaceState(null, '', `#${name}`);
  for (const [key, button] of buttons) button.setAttribute('aria-pressed', String(key === name));
  for (const help of document.querySelectorAll('[data-help]')) help.hidden = help.dataset.help !== name;
  document.querySelector('#expansion-demo-help').hidden = name !== 'scene' && name !== 'cones';
  const blocked = unavailable(name);
  status.textContent = blocked || (name === 'multimap' && sessionRole === 'read' ? '읽기 권한 · 지도 계산·수락·저장에는 검토 권한이 필요합니다.' : '');
  if (blocked || name === 'diagnostics') return;
  const abort = new AbortController(), handles = [];
  current = {destroy() { abort.abort(); for (const item of handles.reverse()) item.destroy(); }};
  const request = createTransport({signal: abort.signal, onUnauthorized: () => {
    if (reviewSession && mine === generation && !closed) clearSession('세션이 만료되었거나 종료되었습니다.', {preserveReplay: true});
  }});
  try {
    if (name === 'multimap') {
      const [{mount, createRobotSceneRenderer}, {createC1Ports}] = await Promise.all([import('../multimap_fusion/index.js'), import('../multimap_fusion/c1_ports.js')]);
      if (mine !== generation || closed) return;
      const ports = createC1Ports(request);
      handles.push(mount(host, {...ports, readOnly: reviewSession && sessionRole === 'read', renderer: createRobotSceneRenderer(window.RobotScene3D)}));
      if (config.flags.usability) {
        stylesheet('operator_usability/operator_usability.css');
        const {mountOperatorUsability} = await import('../operator_usability/index.js');
        if (mine !== generation || closed) return;
        handles.push(mountOperatorUsability(host.querySelector('.mmf'), 'multimap'));
      }
    } else {
      const {mountObservationReview} = await import('./scene.js');
      if (mine !== generation || closed) return;
      handles.push(await mountObservationReview(host, {name: name === 'cones' ? 'scene' : name, request, signal: abort.signal, usability: config.flags.usability, onStatus: kind => {
        if (mine === generation && !closed) status.textContent = `ADVISORY_ONLY · ${kind === 'SYNTHETIC' ? 'SIMULATED · 합성 관측' : kind || '출처 미확인'}`;
      }, onError: error => {
        if (mine === generation && !closed) showError(error);
      }}));
    }
  } catch (error) {
    if (mine === generation && !closed) showError(error);
  }
}
for (const [name, label] of features) {
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = label; button.dataset.feature = name;
  button.addEventListener('click', () => open(name));
  buttons.set(name, button); nav.append(button);
}
document.querySelector('#expansion-theme').addEventListener('click', () => {
  document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
});
login.addEventListener('submit', async event => {
  event.preventDefault();
  if (!secureSession || closed || sessionBusy) return;
  const code = codeInput.value;
  codeInput.value = '';
  const epoch = ++sessionEpoch;
  sessionAbort?.abort(); sessionAbort = new AbortController();
  sessionBusy = true; sessionStatus.textContent = '로그인 확인 중입니다.'; syncSession();
  const request = createTransport({signal: sessionAbort.signal});
  try {
    await request('/api/v1/extensions/session', {method: 'POST', body: code});
    if (epoch !== sessionEpoch || closed) return;
    const value = await request('/api/v1/extensions/session');
    if (installSession(value, epoch)) openAfterLogin();
  } catch {
    if (epoch === sessionEpoch && !closed) clearSession('로그인하지 못했습니다. 코드·HTTPS 주소·서버 설정을 확인해 주세요.', {preserveReplay: true});
  } finally {
    if (epoch === sessionEpoch) { sessionBusy = false; syncSession(); }
  }
});
document.querySelector('#expansion-logout').addEventListener('click', async () => {
  if (!secureSession || closed) return;
  clearSession('로그아웃 중입니다.', {pending: true, preserveReplay: true});
  const epoch = sessionEpoch;
  sessionAbort = new AbortController();
  try {
    await createTransport({signal: sessionAbort.signal})('/api/v1/extensions/session/logout', {method: 'POST'});
    if (epoch === sessionEpoch && !closed) sessionStatus.textContent = '로그아웃되었습니다.';
  } catch {
    if (epoch === sessionEpoch && !closed) sessionStatus.textContent = '화면을 지웠습니다. 서버 로그아웃을 확인하지 못했습니다.';
  } finally {
    if (epoch === sessionEpoch) { sessionBusy = false; syncSession(); }
  }
});
addEventListener('pagehide', () => {
  closed = true;
  if (reviewSession) clearSession('다시 로그인 상태를 확인합니다.');
  else { generation++; dispose(); }
});
addEventListener('pageshow', event => {
  if (!event.persisted) return;
  closed = false;
  open(initialFeature());
  if (secureSession) checkSession();
});
syncSession();
open(initialFeature());
if (secureSession) checkSession();
