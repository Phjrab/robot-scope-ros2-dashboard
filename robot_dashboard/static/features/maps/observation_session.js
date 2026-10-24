// Fixed observation service controls. Never sends a robot motion command.
export function observationSessionView(state = {}, elapsedSeconds = 0) {
  const labels = { UNAVAILABLE: '관측기 사용 불가', CHECKING: '관측기 확인 중', STOPPED: '관측기 정지',
    FAILED: '관측기 종료 / 시작 실패', STARTING: '관측기 시작 중', WAITING_INPUTS: '새 입력 수신 대기',
    READY: '입력 준비 완료', STOPPING: '관측기 종료 중', UNKNOWN: '관측기 상태 확인 필요' };
  const remaining = Number.isFinite(state.remaining_s) ? Math.max(0, state.remaining_s - elapsedSeconds) : null;
  return { label: labels[state.state] || labels.UNKNOWN,
    detail: `${state.reason || ''}${remaining === null ? '' : ` · 남은 ${Math.ceil(remaining / 60)}분`}`,
    canStart: state.can_start === true, canStop: state.can_stop === true && /^[a-f0-9]{32}$/.test(state.session_id || ''),
    ready: state.state === 'READY', sessionId: state.session_id || null };
}

export function initializeObservationSession({ panel, getContext, onSessionChange, onStart, onStop }) {
  const host = document.createElement('div'); host.className = 'saved-observation-session';
  host.innerHTML = `<div class="saved-live-heading"><strong>1. 관측기 실행</strong><span id="savedSessionState" role="status">관측기 확인 중</span></div>
    <p>관측기는 최대 30분 실행됩니다. 입력 준비 후 아래에서 지도 기준점을 연결하세요.</p>
    <div class="saved-live-actions"><button id="savedSessionStart" type="button" disabled>관측 시작 (30분)</button><button id="savedSessionStop" type="button" disabled>관측 종료</button><button id="savedSessionAnchor" type="button" disabled>2. 기준점 설정</button></div>
    <small id="savedSessionDetail"></small><small id="savedSessionError" role="alert"></small>`;
  panel.querySelector('.saved-live-heading').after(host);
  const el = name => host.querySelector(`#savedSession${name}`);
  let state = {}, received = performance.now(), pending = false, disposed = false, controller = null, lastSession = null, error = '';
  function render() {
    const view = observationSessionView(state, (performance.now() - received) / 1000);
    el('State').textContent = view.label; el('Detail').textContent = view.detail; el('Error').textContent = error;
    el('Start').disabled = pending || !view.canStart || !getContext().meta;
    el('Stop').disabled = pending || !view.canStop;
    el('Anchor').disabled = pending || !view.ready || !getContext().meta;
  }
  async function request(action = null) {
    if (disposed || pending) return;
    pending = true; render(); controller = new AbortController();
    const timer = setTimeout(() => controller?.abort(), action ? 12000 : 3000);
    try {
      const response = await fetch(`/api/v1/observations/fastlio${action ? '/' + action : ''}`, {
        signal: controller.signal, ...(action ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirmed: true, ...(action === 'stop' ? { session_id: state.session_id } : {}) }) } : {}) });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `관측 상태 조회 실패 (${response.status})`);
      state = value; received = performance.now(); error = '';
      if (state.session_id && state.active && state.session_id !== lastSession) {
        lastSession = state.session_id; onSessionChange();
      } else if (lastSession && !state.active && !['STARTING', 'UNKNOWN'].includes(state.state)) {
        lastSession = null; onStop();
      }
    } catch (e) {
      error = e.name === 'AbortError' ? '응답 대기 중입니다. 다시 시작하지 않고 상태를 확인합니다.' : e.message;
      // A failed write may have reached the server. Only a later GET enables START.
      state = { ...state, state: 'UNKNOWN', can_start: false, can_stop: false };
    } finally { clearTimeout(timer); controller = null; pending = false; render(); }
  }
  el('Start').addEventListener('click', () => { onStart(); void request('start'); });
  el('Stop').addEventListener('click', () => { onStop(); void request('stop'); });
  el('Anchor').addEventListener('click', () => {
    const details = panel.querySelector('#savedLiveAnchorDetails'); details.open = true;
    details.querySelector('input').focus();
  });
  const timer = setInterval(() => { render(); if (getContext().visible && !document.hidden) void request(); }, 1000);
  void request();
  return { render, destroy() { disposed = true; clearInterval(timer); controller?.abort(); host.remove(); } };
}
