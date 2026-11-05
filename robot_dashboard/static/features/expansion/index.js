import {createTransport} from './transport.js';

const config = JSON.parse(document.querySelector('#expansion-config').textContent);
const host = document.querySelector('#expansion-host');
const nav = document.querySelector('#expansion-nav');
const status = document.querySelector('#expansion-status');
const buttons = new Map();
const features = [
  ['multimap', '여러 지도 합치기'],
  ['scene', '장애물 3D 관측'],
  ['cones', '콘 표시'],
  ['replay', '주행 기록 재생'],
  ['diagnostics', '성능 진단 안내'],
];
let current = null, currentName = null, generation = 0, closed = false;
function unavailable(name) {
  if (name === 'diagnostics') return null;
  const flag = name === 'cones' ? 'scene' : name;
  if (!config.flags[flag]) return `FEATURE_DISABLED · 기능이 꺼져 있습니다. 관리자에게 ${flag === 'replay' ? '로컬 기록 재생' : '해당 기능'} 활성화를 요청하세요.`;
  if (name === 'replay') return null;
  if (config.auth === 'BLOCKED_AUTH') return 'UNAVAILABLE · 서버의 확장 기능 연결 설정을 확인하세요.';
  return null;
}
function dispose() {
  current?.destroy();
  current = null;
  currentName = null;
  host.replaceChildren();
}
function initialFeature() {
  const fragment = location.hash.slice(1);
  if (buttons.has(fragment)) return fragment;
  return ['multimap', 'scene', 'replay'].find(name => config.flags[name]) || 'multimap';
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
  else if (/403/.test(message)) explanation = '접속 주소 오류 · 안내된 HTTPS 주소에서 다시 여세요.';
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
  status.textContent = blocked || '';
  if (blocked || name === 'diagnostics') return;
  const abort = new AbortController(), handles = [];
  current = {destroy() { abort.abort(); for (const item of handles.reverse()) item.destroy(); }};
  const request = createTransport({signal: abort.signal});
  try {
    if (name === 'multimap') {
      const [{mount, createRobotSceneRenderer}, {createC1Ports}] = await Promise.all([import('../multimap_fusion/index.js'), import('../multimap_fusion/c1_ports.js')]);
      if (mine !== generation || closed) return;
      const ports = createC1Ports(request);
      handles.push(mount(host, {...ports, renderer: createRobotSceneRenderer(window.RobotScene3D)}));
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
  button.title = unavailable(name) || '열기';
  button.addEventListener('click', () => open(name));
  buttons.set(name, button); nav.append(button);
}
document.querySelector('#expansion-theme').addEventListener('click', () => {
  document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
});
addEventListener('pagehide', () => {
  closed = true;
  generation++;
  dispose();
});
addEventListener('pageshow', event => {
  if (!event.persisted) return;
  closed = false;
  open(initialFeature());
});
open(initialFeature());
