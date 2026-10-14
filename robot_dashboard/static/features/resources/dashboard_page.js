import { createResourceMonitor } from './view.js';

const host = document.querySelector('#resourceMonitor');
let monitor = null;
let loading = false;
let active = document.documentElement.dataset.activePage === 'resources';

async function sync() {
  monitor?.setActive(active);
  if (!host || !active || monitor || loading) return;
  loading = true;
  try {
    const response = await fetch('/static/resources.html', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const source = new DOMParser().parseFromString(await response.text(), 'text/html');
    const content = source.querySelector('main.resource-content');
    const badge = source.querySelector('#connectionState');
    if (!content || !badge) throw new Error('자원 화면을 찾을 수 없습니다.');
    host.replaceChildren(document.importNode(badge, true), document.importNode(content, true));
    // Route links stay within the existing dashboard and its safety lifecycle.
    host.querySelectorAll('a[href="/#topics"]').forEach((link) => { link.href = '#topics'; });
    monitor = createResourceMonitor(host, { active });
  } catch (error) {
    const message = document.createElement('p'); message.setAttribute('role', 'status');
    message.textContent = `자원 화면 로드 실패: ${error.message}`;
    const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = '다시 시도';
    retry.addEventListener('click', sync);
    host.replaceChildren(message, retry);
  } finally { loading = false; }
}

document.addEventListener('robot-scope:page-change', (event) => {
  active = event.detail?.activePage === 'resources'; sync();
});
sync();
