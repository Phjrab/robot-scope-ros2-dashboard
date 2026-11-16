export function projectPoint(p, view) {
  if (view === 'xy') return [p[0], p[1]];
  if (view === 'xz') return [p[0], p[2]];
  return [(p[0] - p[1]) * .7071, p[2] * .8165 - (p[0] + p[1]) * .4082];
}

export function sharedBounds(comparison, view) {
  const all = [...comparison.before, ...comparison.after, ...comparison.path_before, ...comparison.path_after];
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const point of all) {
    const [x, y] = projectPoint(point, view);
    minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return all.length ? {minX, maxX, minY, maxY} : {minX: -1, maxX: 1, minY: -1, maxY: 1};
}

export function actions(job) {
  return {run: Boolean(job && job.state !== 'RUNNING' && !job.saved), cancel: job?.state === 'RUNNING',
    save: job?.state === 'SUCCEEDED' && !job.saved, download: Boolean(job?.saved && job.revision)};
}

if (typeof document !== 'undefined') {
  const $ = id => document.getElementById(id);
  let job = null, comparison = null, generation = 0, pending = false;
  const states = {IMPORTED:'기록 준비', RUNNING:'루프 검색 및 최적화 중', SUCCEEDED:'보정 완료',
    NO_LOOP:'검증된 루프 없음 — 결과 지도는 저장하지 않았습니다', FAILED:'계산 실패',
    CANCELLED:'작업 취소', TIMED_OUT:'계산 시간 초과', INTERRUPTED:'서버 종료로 중단됨'};
  async function api(path, options = {}) {
    const response = await fetch('./api/' + path, options);
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '입력 값을 확인하세요.');
    return body;
  }
  const post = body => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  function buttons() {
    const enabled = actions(job);
    for (const key of ['run','cancel','save']) $(key).disabled = pending || !enabled[key];
    $('download').hidden = !enabled.download;
    if (enabled.download) $('download').href = `./api/sessions/${job.id}/export?revision=${job.revision}`;
  }
  function show() {
    buttons();
    if (!job) return;
    const option = [...$('sessions').options].find(item => item.value === job.id);
    if (option) option.textContent = `${job.id.slice(0,8)} · ${job.keyframes} frames · ${states[job.state] || job.state}`;
    $('status').textContent = `${states[job.state] || job.state} · ${job.keyframes} 키프레임 · ${job.provenance === 'synthetic_fixture' ? '합성 시험 데이터' : '주행 기록'}${job.saved ? ' · 새 지도 저장됨' : ''}`;
    if (job.error) $('error').textContent = job.error;
    $('metrics').replaceChildren();
    const labels = {accepted_loops:'채택 루프',initial_cost:'최적화 전 비용',final_cost:'최적화 후 비용',
      endpoint_gap_before_m:'보정 전 끝점 간격 (m)',endpoint_gap_after_m:'보정 후 끝점 간격 (m)',evaluations:'함수 평가 횟수'};
    for (const [key,label] of Object.entries(labels)) {
      if (job.metrics?.[key] === undefined) continue;
      const item = document.createElement('div'); item.className = 'metric'; item.textContent = label;
      const value = document.createElement('b'); value.textContent = Number(job.metrics[key]).toFixed(key === 'accepted_loops' || key === 'evaluations' ? 0 : 3);
      item.append(value); $('metrics').append(item);
    }
    $('loops').replaceChildren();
    for (const loop of job.candidates || []) {
      const row = document.createElement('tr');
      for (const value of [`${loop.i} ↔ ${loop.j}`,loop.reason,loop.overlap?.toFixed(3) ?? '—',loop.rmse_m?.toFixed(3) ?? '—']) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      $('loops').append(row);
    }
  }
  function draw() {
    if (!comparison) return;
    const view = $('view').value, bounds = sharedBounds(comparison, view);
    for (const side of ['before','after']) {
      const canvas = $(side), dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth, height = canvas.clientHeight;
      canvas.width = width*dpr; canvas.height = height*dpr;
      const ctx = canvas.getContext('2d'); ctx.scale(dpr,dpr); ctx.clearRect(0,0,width,height);
      const scale = Math.min((width-40)/Math.max(.1,bounds.maxX-bounds.minX),(height-40)/Math.max(.1,bounds.maxY-bounds.minY));
      const pixel = p => {const [x,y] = projectPoint(p,view); return [width/2+(x-(bounds.minX+bounds.maxX)/2)*scale,height/2-(y-(bounds.minY+bounds.maxY)/2)*scale];};
      ctx.fillStyle = side === 'before' ? '#619fc388' : '#71c5a288';
      for (const p of comparison[side]) {const [x,y] = pixel(p); ctx.fillRect(x,y,1.5,1.5);}
      const path = comparison['path_'+side]; ctx.strokeStyle = side === 'before' ? '#7dbafb' : '#8cf3bd';
      ctx.lineWidth=2; ctx.beginPath(); path.forEach((p,i) => {const [x,y]=pixel(p); if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.stroke();
      ctx.strokeStyle='#f2d582';ctx.setLineDash([5,4]);
      for(const loop of comparison.candidates || []) if(loop.reason==='ACCEPTED') {
        ctx.beginPath();ctx.moveTo(...pixel(path[loop.i]));ctx.lineTo(...pixel(path[loop.j]));ctx.stroke();
      }
      ctx.setLineDash([]);if(path.length){ctx.fillStyle='white';ctx.beginPath();ctx.arc(...pixel(path[0]),5,0,2*Math.PI);ctx.fill();}
    }
  }
  async function select(id) {
    const token = ++generation; job=null;comparison=null;buttons();
    for (const side of ['before','after']) { const c=$(side);c.getContext('2d').clearRect(0,0,c.width,c.height); }
    if (!id) return;
    const next = await api('sessions/'+id);
    const geometry = await api(`sessions/${id}/comparison`);
    if(token !== generation) return;
    job=next;comparison=geometry;
    for (const key of ['search_radius','min_separation','max_rmse','min_overlap','min_height','max_height']) {
      if (job.settings?.[key] !== undefined) $(key).value = String(job.settings[key]);
      $(key).disabled = job.saved || job.state === 'RUNNING';
    }
    show();draw();
  }
  async function refresh(selected) {
    const data=await api('sessions');$('sessions').replaceChildren(new Option('선택',''));
    for(const item of data.sessions) $('sessions').add(new Option(`${item.id.slice(0,8)} · ${item.keyframes} frames · ${states[item.state] || item.state}`,item.id));
    if(selected){$('sessions').value=selected;await select(selected);}
  }
  async function guard(action) {
    if(pending)return;pending=true;$('error').textContent='';buttons();
    try{await action();}catch(error){$('error').textContent=error.message;}finally{pending=false;buttons();}
  }
  $('file').onchange=()=>guard(async()=>{const file=$('file').files[0];if(!file)return;
    if(file.size>64*1024*1024)throw new Error('기록은 64 MiB 이하만 지원합니다.');
    const imported=await api('sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:file});await refresh(imported.id);});
  $('sessions').onchange=()=>guard(()=>select($('sessions').value));
  $('refresh').onclick=()=>guard(()=>refresh(job?.id));
  $('run').onclick=()=>guard(async()=>{const settings={};for(const key of ['search_radius','min_separation','max_rmse','min_overlap','min_height','max_height'])settings[key]=Number($(key).value);
    const id=job.id;await api(`sessions/${id}/optimize`,post({expected_revision:job.source_revision,settings}));await select(id);});
  $('cancel').onclick=()=>guard(async()=>{const id=job.id;await api(`sessions/${id}/cancel`,post({}));await select(id);});
  $('save').onclick=()=>guard(async()=>{await api(`sessions/${job.id}/save`,post({revision:job.revision}));await refresh(job.id);});
  $('view').onchange=draw;window.addEventListener('resize',draw);
  setInterval(async()=>{if(pending || job?.state!=='RUNNING')return;await guard(async()=>{const id=job.id;const next=await api('sessions/'+id);if(next.state!=='RUNNING')await select(id);else{job=next;show();}});},1000);
  guard(()=>refresh());
}
