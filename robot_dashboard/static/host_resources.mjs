export function percent(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? `${value.toFixed(1)}%` : 'N/A';
}

export function capacity(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `${(value / 1073741824).toFixed(1)} GiB` : 'N/A';
}

export function sparkline(history, field) {
  let connected = false;
  return (Array.isArray(history) ? history.slice(-60) : []).map((point, index) => {
    const value = point?.[field];
    if (typeof value !== 'number' || !Number.isFinite(value)) { connected = false; return ''; }
    const command = connected ? 'L' : 'M';
    connected = true;
    return `${command}${(index * 4).toFixed(1)},${(48 - Math.min(100, Math.max(0, value)) * .44).toFixed(1)}`;
  }).join(' ');
}

export function mountResources(panel, fetcher = fetch) {
  let timer, active = false, request = null, stopped = false;
  const put = (name, value) => {
    const node = panel.querySelector(`[data-resource="${name}"]`);
    if (node) node.textContent = value;
  };
  function render(data) {
    put('host', `${data.host?.model || '알 수 없는 호스트'} · 대시보드 실행 호스트`);
    put('cpu', percent(data.cpu?.percent));
    put('gpu', percent(data.gpu?.percent));
    put('ram', percent(data.ram?.percent));
    put('ram-detail', `${capacity(data.ram?.used_bytes)} / ${capacity(data.ram?.total_bytes)}`);
    put('swap', `${capacity(data.swap?.used_bytes)} / ${capacity(data.swap?.total_bytes)}`);
    put('disk', percent(data.disk?.percent));
    put('disk-detail', `여유 ${capacity(data.disk?.free_bytes)}`);
    const temperature = data.temperature?.max_celsius;
    put('temperature', typeof temperature === 'number' && Number.isFinite(temperature) ? `${temperature.toFixed(1)} °C` : 'N/A');
    const date = new Date(data.sampled_at);
    put('updated', Number.isNaN(date.getTime()) ? '측정 시각 N/A' : `${date.toLocaleTimeString()} · 최근 ${data.history?.length || 0}표본`);
    put('state', '측정 중');
    put('notes', (data.unavailable || []).join(' · ') || '호스트 전체 사용량 · 온도만으로 클럭 저하 여부를 판정하지 않습니다.');
    for (const path of panel.querySelectorAll('[data-resource-chart]')) {
      path.setAttribute('d', sparkline(data.history, path.dataset.resourceChart));
    }
    panel.dataset.state = 'observed';
  }
  async function sample() {
    if (!active || stopped || request) return;
    request = new AbortController();
    const timeout = setTimeout(() => request?.abort(), 4500);
    try {
      const response = await fetcher('/api/v1/system/resources', { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('resource response unavailable');
      const data = await response.json();
      if (data.schema_version !== 1 || data.scope !== 'dashboard_host') throw new Error('unknown resource contract');
      if (active && !stopped) render(data);
    } catch (error) {
      if (active && !stopped) {
        put('state', '연결 확인 필요');
        put('notes', '최신 자원 표본을 받지 못했습니다. 표시된 값은 이전 측정치입니다.');
        panel.dataset.state = 'stale';
      }
    } finally {
      clearTimeout(timeout);
      request = null;
      if (active && !stopped) timer = setTimeout(sample, 2000);
    }
  }
  function visibility() {
    active = !document.hidden && location.hash === '#settings';
    clearTimeout(timer);
    if (active) sample(); else request?.abort();
  }
  window.addEventListener('hashchange', visibility);
  document.addEventListener('visibilitychange', visibility);
  visibility();
  return () => {
    stopped = true; clearTimeout(timer); request?.abort();
    window.removeEventListener('hashchange', visibility);
    document.removeEventListener('visibilitychange', visibility);
  };
}

if (typeof document !== 'undefined') {
  const panel = document.getElementById('hostResourcePanel');
  if (panel) mountResources(panel);
}
