// Explicit localhost fixture view. Production has no matching activation API.
export function createOfflineSignalDemo({row, summary, document: doc}) {
  if (new URLSearchParams(globalThis.location?.search || '').get('offline_signal') !== '1') return null;
  let disposed = false, pending = false;
  const endpoint = '/__fixture/native-signal';
  const label = doc.createElement('label'); label.textContent = '오프라인 신호 시나리오';
  const select = doc.createElement('select'); select.setAttribute('aria-label', label.textContent);
  for (const [value, text] of [['normal','GREEN 통과'],['red','RED 유지'],['unknown','UNKNOWN 유지'],['delayed_plan','계획 지연 중 STOP']]) {
    const o = doc.createElement('option'); o.value=value; o.textContent=text; select.append(o);
  }
  label.append(select); row.append(label);
  summary.dataset.offlineSignal = 'true';
  function render(s) {
    if (disposed) return;
    summary.textContent = `OFFLINE SYNTHETIC · 실제 주행 아님\n선택 source: ${s.source} · mode ${s.mode}\n실행 ${s.run_id || '없음'} · phase ${s.phase} · 차단/대기 ${s.reason || '명시적 시작 대기'}\n마지막 관측 ${s.last_observation_s ?? '—'}s · goal ${s.goal_count}회 · 계획 응답 ${s.planning_delayed ? '대기 중' : '완료/없음'}\n신호 RAW ${s.observation?.raw_state || 'UNKNOWN'} / stable ${s.observation?.stable_state || 'UNKNOWN'}\n독립 앞발 ${s.observation?.front_left_status || '—'} / ${s.observation?.front_right_status || '—'} · 독립 정지 ${s.observation?.body_motion_status || '—'}\n유효 정차 ${Number(s.dwell_elapsed_s || 0).toFixed(1)}s · 이동 evidence ${s.departed ? '시뮬레이션 관측됨' : '아직 없음'}\n${s.trace?.map(x=>`${x.time_s}s ${x.phase}`).join(' → ') || ''}\n${s.error || ''}`;
    summary.dataset.phase = s.phase;
  }
  async function request(body) {
    const r = await fetch(endpoint, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {cache:'no-store'});
    if (!r.ok) throw new Error('전용 로컬 fixture 서버에서만 사용 가능합니다.');
    const result = await r.json(); render(result); return result;
  }
  for (const [text, action] of [['오프라인 신호 시작','start'],['오프라인 STOP','stop']]) {
    const b = doc.createElement('button'); b.type='button'; b.textContent=text;
    b.addEventListener('click', async () => {
      if (pending && action !== 'stop') return;
      pending = true;
      try { await request({action, scenario:select.value, request_id:crypto.randomUUID().replaceAll('-','')}); }
      catch (error) { if (!disposed) summary.textContent=error.message; }
      finally { pending=false; }
    }); row.append(b);
  }
  return {async refresh() { try { await request(); } catch (e) { if (!disposed) summary.textContent=e.message; } }, destroy() { disposed=true; }};
}
