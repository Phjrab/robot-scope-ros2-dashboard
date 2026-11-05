import {createSession} from './session.js';
import {SCHEMA,sourceDescriptor,boundedPreview,pinsEqual,pin,clone,validateCorrespondences} from './contract.js';
import {createOverlay,COLORS,drawDerived} from './overlay.js';
export {createHttpPorts} from './contract.js';
export {createRobotSceneRenderer} from './overlay.js';

export function mount(host,{catalogue,jobs,renderer,readOnly=false,onReview=()=>{},confirmDiscard=()=>globalThis.confirm('Discard the current UI draft and proposal? Original maps are preserved.'),pollMs=350}={}) {
  if(!host||!catalogue?.list||!catalogue?.preview||!jobs?.start)throw new TypeError('Host, catalogue and jobs ports required.');
  const doc=host.ownerDocument,win=doc.defaultView,session=createSession();
  let entries=[],previews=new Map(),visibility={},dirty=false,destroyed=false,active=null,timer=null,loadGeneration=0,previewGeneration=0,busy=false;
  let savedStorage='',message='Loading local catalogue…',savedMap=null,viewMode='both',drag=null,previewError=false,catalogueLoaded=false;
  const root=doc.createElement('section');root.className='mmf';root.setAttribute('aria-label','Multi-map fusion review');host.append(root);
  root.innerHTML=`<header class="mmf-header"><div><small>Multimap Fusion</small><h2>지도 정합 작업</h2><p>새 리뷰 PCD를 저장하고 결과를 확인합니다.</p></div><span class="mmf-badge">샘플 미리보기</span></header>
    <div class="mmf-layout"><aside class="mmf-card"><h3>지도 선택</h3><button type="button" data-action="reload">목록 새로고침 / Retry</button><div data-slot="catalogue"></div><p data-slot="empty"></p>
    <h3>기준 지도와 표시</h3><label>기준 지도 <select data-field="anchor" aria-label="Anchor map"></select></label><div data-slot="layers"></div><p class="mmf-note">원점은 지도 수집 세션마다 다릅니다. 표시 범위는 샘플 기준입니다.</p></aside>
    <main><section class="mmf-card"><div class="mmf-toolbar"><h3>XY 비교 · m</h3><select data-field="view" aria-label="Overlay comparison"><option value="both">정합 전·후 함께</option><option value="before">정합 전</option><option value="after">정합 후</option></select><label>화면 회전 <input data-field="rotation" aria-label="View rotation rad" type="number" step="0.1" value="0"></label></div>
    <canvas data-canvas="xy" tabindex="0" aria-label="XY manual assist. Drag to translate; yaw handle at upper right. Arrow keys translate; Q/E rotate."></canvas>
    <p class="mmf-note">□ 수동 prior / ■ solved · XY drag · 오른쪽 위 yaw handle · 방향키 0.1 m · Q/E 0.05 rad. 대응점은 실제 샘플 XYZ 또는 명시적 XYZ 입력만 사용합니다.</p>
    <div class="mmf-toolbar"><label>수동 보조 대상 <select data-field="target" aria-label="Manual source"></select></label><select data-field="tool" aria-label="Assist tool"><option value="drag">XY 이동·Yaw 회전</option><option value="source">대상 지도 XYZ 선택</option><option value="anchor">기준 지도 XYZ 선택</option></select><button type="button" data-action="undo">초안 되돌리기</button><button type="button" data-action="redo">초안 다시 실행</button><button type="button" data-action="reset">초안 초기화</button></div>
    <div class="mmf-pose" data-slot="pose"></div><details><summary>XYZ 대응점 입력 · m</summary><p>같은 물리적 지점의 원본 XYZ를 양쪽 지도에서 선택하거나 입력하세요. 일직선이 아닌 3쌍 이상이 필요합니다.</p><div class="mmf-pairs"><label>대상 지도 XYZ <input data-field="sourceXYZ" aria-label="Source XYZ" value="0,0,0"></label><label>기준 지도 XYZ <input data-field="anchorXYZ" aria-label="Anchor XYZ" value="0,0,0"></label><button type="button" data-action="pair">XYZ 쌍 추가</button><button type="button" data-action="clearPairs">쌍 지우기</button></div><ol data-slot="pairs"></ol></details></section>
    <section class="mmf-card"><div class="mmf-toolbar"><h3>자동 정합과 후보 검토</h3><button type="button" data-action="start">자동 정합 시작 / Retry</button><button type="button" data-action="cancel">계산 취소</button></div><progress max="100" value="0" aria-label="Job progress"></progress><p role="status" aria-live="polite" data-slot="status"></p><p data-slot="identity" class="mmf-note"></p><ul data-slot="warnings" class="mmf-warnings"></ul><div data-slot="diagnostics"></div>
    <div class="mmf-compare"><figure><figcaption>3D 비교 · 샘플 미리보기 · 높이별 색상</figcaption><canvas data-canvas="scene" aria-label="Merged 3D candidate"></canvas></figure><figure><figcaption>2D 변환 후보 · 회색은 미확인 영역</figcaption><canvas data-canvas="grid" width="360" height="200" aria-label="Derived 2D candidate"></canvas><small data-slot="gridNote">자료 없음 · 빈 점 영역을 free로 만들지 않습니다.</small></figure></div>
    <label class="mmf-ack"><input type="checkbox" data-field="ack">경고·모호성·연결 상태를 검토했습니다. 후보 수락은 운영 적용이 아닙니다.</label><div class="mmf-toolbar"><button type="button" data-action="accept">후보 수락</button><label>새 PCD 이름 <input data-field="name" aria-label="New PCD name" maxlength="64" placeholder="new_fused_map"></label><button type="button" data-action="save">새 PCD 저장</button></div><p data-slot="saved"></p></section></main></div>`;
  const $=s=>root.querySelector(s),field=n=>$(`[data-field="${n}"]`),slot=n=>$(`[data-slot="${n}"]`),button=n=>$(`[data-action="${n}"]`),canvas=$('[data-canvas="xy"]'),overlay=createOverlay(canvas);
  const scene=renderer?.({canvas:$('[data-canvas="scene"]')});
  const listen=(node,type,fn)=>node.addEventListener(type,fn,{signal:abort.signal});
  const abort=new win.AbortController();
  function el(tag,text){const e=doc.createElement(tag);if(text!=null)e.textContent=text;return e;}
  function failureMessage(error) {
    const guidance = {401:'로그인이 필요합니다.',403:'현재 권한으로 실행할 수 없습니다.',
      409:'지도 정보가 변경되었습니다. 최신 자료를 다시 선택하세요.',
      503:'UNAVAILABLE · 검토용 지도 제공자가 미연결입니다. 관리자에게 입력 구성을 확인하세요.'};
    return [guidance[error.status],error.message].filter(Boolean).join(' ');
  }
  function run(fn){return async()=>{try{await fn();}catch(e){message=failureMessage(e);}if(!destroyed)refresh();};}
  const modified=()=>{dirty=true;field('ack').checked=false;};
  function chosen(){return session.snapshot().draft.sources;}
  function targets(select,ss,current){select.replaceChildren(...ss.map(s=>{const o=el('option',s.name);o.value=s.id;return o;}));if(ss.some(s=>s.id===current))select.value=current;}
  function renderCatalogue(){
    slot('catalogue').replaceChildren();const ids=chosen().map(s=>s.id);
    for(const s of entries){const label=el('label');label.className='mmf-source';const check=el('input');check.type='checkbox';check.dataset.source=s.id;check.checked=ids.includes(s.id);check.setAttribute('aria-label',`Select ${s.name}`);
      check.disabled=busy;label.append(check);const text=el('span');text.append(el('strong',s.name),el('small',`${s.session_id ?? '세션 미확인'} · rev ${s.revision} · ${s.point_count.toLocaleString()} pts · m`),el('small',`${s.wire_descriptor?.evidence_kind ?? '출처 미확인'} · SHA-256 ${s.sha256}`),el('small',`${s.id} · frame ${s.frame_id}${s.ancestors.length?' · merged ancestors '+s.ancestors.join(', '):''}`));label.append(text);slot('catalogue').append(label);}
    slot('empty').textContent=entries.length||!catalogueLoaded?'':'조회된 3D 지도가 없습니다. 관리자에게 검토용 지도 사본 등록을 요청하세요.';
  }
  function renderLayers(snapshot){
    slot('layers').replaceChildren();
    snapshot.draft.sources.forEach((s,i)=>{const row=el('div');row.className='mmf-layer';row.style.borderLeftColor=COLORS[i];const toggle=el('input');toggle.type='checkbox';toggle.checked=!visibility[s.id]?.hidden;toggle.dataset.visible=s.id;toggle.setAttribute('aria-label',`Show ${s.name}`);
      const opacity=el('input');opacity.type='range';opacity.min='0.1';opacity.max='1';opacity.step='0.1';opacity.value=visibility[s.id]?.opacity??0.8;opacity.dataset.opacity=s.id;opacity.setAttribute('aria-label',`Opacity ${s.name}`);
      row.append(toggle,el('span',s.name),opacity,el('small',overlay.extent(s.id)));slot('layers').append(row);});
  }
  function draw(){
    if(destroyed)return;
    const s=session.snapshot();
    const draft=drag?.next?{...s.draft,priors:{...s.draft.priors,[drag.id]:{...drag.pose,...drag.next}}}:s.draft;
    overlay.draw({draft,previews,proposal:s.proposal,visibility,mode:viewMode,light:doc.documentElement.dataset.theme==='light',rotation:Number(field('rotation').value)||0});
    scene?.render({points:overlay.points3d(),revision:s.revision,mode:viewMode});
    const valid=drawDerived($('[data-canvas="grid"]'),s.proposal?.derived_2d,doc.documentElement.dataset.theme==='light');
    slot('gridNote').textContent=valid?'Server-derived candidate only · gray unknown / pale free / dark occupied · 운영 미적용':'자료 없음 / unsupported · 빈 점 영역은 unknown입니다.';
  }
  function refresh(){
    if(destroyed)return;
    const s=session.snapshot(),target=field('target').value;
    targets(field('anchor'),s.draft.sources,s.draft.anchor);targets(field('target'),s.draft.sources.filter(v=>v.id!==s.draft.anchor),target);
    for(const input of slot('pose').querySelectorAll('input')){input.value=s.draft.priors[field('target').value]?.[input.dataset.pose]??0;input.disabled=busy||!field('target').value;}
    field('anchor').disabled=busy;field('target').disabled=busy;field('name').disabled=readOnly||busy;field('ack').disabled=readOnly;
    for(const name of ['pair','clearPairs','reset'])button(name).disabled=busy;
    button('undo').disabled=!s.canUndo||busy;button('redo').disabled=!s.canRedo||busy;
    button('start').disabled=readOnly||s.draft.sources.length<2||busy||!!active||previewError;
    button('cancel').disabled=readOnly||!active;button('accept').disabled=readOnly||!jobs.accept||s.status!=='SOLVED_CANDIDATE'||!field('ack').checked||busy||s.proposal?.connected_components?.length!==1;
    button('save').disabled=readOnly||!jobs.save||s.status!=='ACCEPTED'||busy||!field('name').value.trim();
    slot('status').textContent=`${s.status} · ${message}`;slot('status').dataset.state=s.status;
    slot('identity').textContent=`UI draft rev ${s.revision} · proposal ${s.proposal?`${s.proposal.proposal_id}@${s.proposal.proposal_revision}`:'none'} · stale responses ignored ${s.stale} · undo/redo restores draft only; proposal requires recompute`;
    slot('warnings').replaceChildren(...[...s.warnings,...(s.proposal?.warnings||[])].map(w=>el('li',w)));
    const metrics=s.proposal?.metrics;
    slot('diagnostics').replaceChildren();
    if(s.proposal){slot('diagnostics').append(el('p',`Components: ${s.proposal.connected_components.map(c=>c.join(' + ')).join(' | ')} · accepted edges ${s.proposal.accepted_edges.length} / rejected edges ${s.proposal.rejected_edges.length}`));
      const table=el('table');const header=el('tr');['지도 쌍','겹침률','거리 / RMSE (m)','검토 사항'].forEach(v=>header.append(el('th',v)));table.append(header);
      for(const row of (metrics?.pairwise||[]).slice(0,64)){const tr=el('tr');[row.pair?.join(' ↔ '),row.overlap, row.distance_p95_m!=null?`${Number(row.distance_p95_m).toFixed(4)} p95 / ${Number(row.rmse_m).toFixed(4)} RMSE`:row.rmse_m,row.warning||'검토 필요'].forEach(v=>tr.append(el('td',String(v??'unavailable'))));table.append(tr);}slot('diagnostics').append(table,el('small','Heatmap: '+(s.proposal.heatmap?.length?'provider residual samples':'not supplied')+' · Low RMSE alone is not acceptance.'));}
    slot('pairs').replaceChildren(...s.draft.correspondences.map((p,i)=>el('li',`${i+1}. ${p.source_id}: [${p.source_xyz}] ↔ [${p.anchor_xyz}] (${p.provenance})`)));
    if(s.draft.correspondences.length){try{validateCorrespondences(s.draft.correspondences).forEach(w=>slot('pairs').append(el('li',w)));}catch(e){slot('pairs').append(el('li',e.message));}}
    slot('saved').textContent=savedMap?`새 identity 확인: ${savedMap.id} · ${savedStorage} · rev ${savedMap.revision} · SHA-256 ${savedMap.sha256} · 원본 유지 · 운영 미적용`:'';
    draw();renderLayers(s);renderCatalogue();
  }
  for(const [key,label] of [['x','X m'],['y','Y m'],['yaw','Yaw rad'],['z','Z m (advanced)'],['roll','Roll rad (advanced)'],['pitch','Pitch rad (advanced)']]){
    const wrap=el('label',label),input=el('input');input.type='number';input.step='0.05';input.value='0';input.dataset.pose=key;input.setAttribute('aria-label',label);wrap.append(input);slot('pose').append(wrap);
    listen(input,'change',run(()=>{if(!input.value.trim())throw new Error('Finite pose value required.');session.prior(field('target').value,{[key]:Number(input.value)});modified();message='Manual prior changed; solve a new proposal.';}));
  }
  async function loadCatalogue(){
    const generation=++loadGeneration;busy=true;catalogueLoaded=false;refresh();
    try {const result=await catalogue.list();if(destroyed||generation!==loadGeneration)return;
      if(result?.schema!==SCHEMA||!Array.isArray(result.sources)||result.sources.length>1000)throw new Error('Unsupported catalogue schema.');
      const next=result.sources.map(sourceDescriptor);if(new Set(next.map(s=>s.id)).size!==next.length)throw new Error('Duplicate catalogue ID.');
      const changed=chosen().some(s=>!next.some(n=>pinsEqual(pin(n),pin(s))));
      if(changed){session.select([]);previews.clear();previewGeneration++;dirty=false;message='Source revision changed / removed. Draft invalidated; reselect pinned sources.';}else message='Catalogue ready · 지도 2개 이상을 선택하세요.';
      entries=next;catalogueLoaded=true;
    }finally{if(generation===loadGeneration){busy=false;if(!destroyed)refresh();}}
  }
  async function loadPreviews(){
    const generation=++previewGeneration,sources=chosen();previews.clear();previewError=false;message='Loading sampled previews…';refresh();
    const results=await Promise.allSettled(sources.map(async s=>[s.id,boundedPreview(await catalogue.preview(clone(s)),s)]));
    if(destroyed||generation!==previewGeneration)return;
    for(const r of results){if(r.status==='fulfilled')previews.set(...r.value);else {previewError=true;message=r.reason.message;}}
    if(!previewError)message='Sampled previews ready · 미리보기가 준비되었습니다. 기준 지도와 정합 전 위치를 확인하세요.';refresh();
  }
  async function consume(ticket,response){
    if(destroyed)return;
    const applied=session.receive(ticket,response);
    if(!applied){message='Late job response ignored; newest manual draft preserved.';active=null;clearTimeout(timer);refresh();return;}
    if(response.state==='RUNNING'){
      $('progress').value=Math.min(100,Math.max(0,Number(response.progress)||0));message=response.message||'Server job running…';
      timer=setTimeout(()=>run(async()=>{try{const next=await jobs.get(response.job_id);if(active?.ticket.nonce===ticket.nonce)await consume(ticket,next);}catch(e){if(active?.ticket.nonce===ticket.nonce){active=null;session.fail();}throw e;}})(),pollMs);
    }else {active=null;clearTimeout(timer);$('progress').value=response.state==='SOLVED_CANDIDATE'?100:0;message=response.reason||'Candidate requires explicit review; warnings remain visible.';}
    refresh();
  }
  listen(slot('catalogue'),'change',run(async()=>{
    const ids=[...slot('catalogue').querySelectorAll('input:checked')].map(e=>e.dataset.source);
    if(dirty&&!await confirmDiscard()){message='Selection unchanged; current draft retained.';return;}
    session.select(entries.filter(s=>ids.includes(s.id)));dirty=false;savedMap=null;field('ack').checked=false;await loadPreviews();
  }));
  listen(field('anchor'),'change',run(()=>{session.anchor(field('anchor').value);modified();}));
  listen(field('target'),'change',()=>refresh());
  listen(slot('layers'),'change',run(()=>{for(const e of slot('layers').querySelectorAll('input')){const id=e.dataset.visible||e.dataset.opacity;visibility[id]||={};if(e.dataset.visible)visibility[id].hidden=!e.checked;else visibility[id].opacity=Number(e.value);}draw();}));
  for(const k of ['view','rotation'])listen(field(k),'change',run(()=>{viewMode=field('view').value;draw();}));
  listen(field('ack'),'change',()=>refresh());listen(field('name'),'input',()=>{button('save').disabled=readOnly||session.snapshot().status!=='ACCEPTED'||busy||!field('name').value.trim();});
  const actions={reload:async()=>{await loadCatalogue();if(chosen().length)await loadPreviews();},
    undo:async()=>{const before=JSON.stringify(chosen());session.undo();modified();if(before!==JSON.stringify(chosen()))await loadPreviews();},redo:async()=>{const before=JSON.stringify(chosen());session.redo();modified();if(before!==JSON.stringify(chosen()))await loadPreviews();},reset:()=>{session.reset();modified();},
    pair:()=>{const xyz=n=>field(n).value.split(',').map(Number);session.addPair(field('target').value,xyz('sourceXYZ'),xyz('anchorXYZ'),'explicit-or-sampled-XYZ');modified();},
    clearPairs:()=>{session.clearPairs();modified();},
    start:async()=>{
      const {token,request}=session.begin();modified();active={ticket:token,id:null};message='Submitting pinned source descriptors; no preview arrays…';refresh();
      try {const current=active;const response=await jobs.start(request);if(current.cancelWhenStarted)await jobs.cancel(response.job_id);if(active?.ticket.nonce===token.nonce){active.id=response.job_id;await consume(token,response);}}
      catch(e){if(active?.ticket.nonce===token.nonce){active=null;session.fail();}throw e;}
    },
    cancel:async()=>{const old=active;active=null;clearTimeout(timer);session.cancel();message='Cancelled locally; late responses cannot alter this draft.';refresh();if(old?.id)await jobs.cancel(old.id);else if(old)old.cancelWhenStarted=true;},
    accept:async()=>{const request=session.reviewRequest();busy=true;refresh();try{const result=await jobs.accept(request);session.reviewed(request,result);await onReview(clone(result));message='후보를 수락했습니다. 새 이름을 입력하고 새 PCD 저장을 눌러 주세요.';}finally{busy=false;}},
    save:async()=>{const request=session.saveRequest(field('name').value.trim());busy=true;refresh();try{const result=await jobs.save(request);savedMap=session.saved(request,result);savedStorage=result.storage==='offline BundleStore'?'offline BundleStore':'';dirty=false;message='New PCD identity verified; refreshing catalogue.';
      try{await loadCatalogue();if(!entries.some(s=>pinsEqual(pin(s),pin(savedMap))))message='Saved identity verified; catalogue has not returned it yet. Retry refresh.';else message='Saved and listed · 새 리뷰 PCD 저장·재조회 완료. 사본 ID·revision·SHA를 확인하세요.';}catch(e){message=`Saved ${savedMap.id}; catalogue refresh failed: ${e.message}`;}
    }finally{busy=false;}}
  };
  for(const [name,fn]of Object.entries(actions))listen(button(name),'click',run(fn));
  const local=e=>{const r=canvas.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
  listen(canvas,'pointerdown',e=>{
    if(busy||e.button!==0||!field('target').value)return;const [x,y]=local(e);
    if(field('tool').value!=='drag'){
      const id=field('tool').value==='anchor'?session.snapshot().draft.anchor:field('target').value,p=overlay.pick(x,y,id);
      if(p){field(field('tool').value==='anchor'?'anchorXYZ':'sourceXYZ').value=p.join(',');message=`Selected actual sample XYZ from ${id}: ${p.join(', ')}`;}else message='No sampled XYZ at this pixel; enter explicit XYZ.';refresh();return;
    }
    canvas.setPointerCapture(e.pointerId);drag={x,y,id:field('target').value,pose:session.snapshot().draft.priors[field('target').value],yaw:x>canvas.clientWidth-64&&y<80,delta:overlay.delta(1,0),deltaY:overlay.delta(0,1)};canvas.focus();
  });
  listen(canvas,'pointermove',e=>{
    if(!drag)return;const [x,y]=local(e),dx=x-drag.x,dy=y-drag.y;
    // Draft mutation happens on release. The in-progress gesture invalidates pending jobs immediately.
    if(!drag.invalidated){session.invalidate();modified();drag.invalidated=true;}
    drag.next=drag.yaw?{yaw:drag.pose.yaw+dx*0.01}:{x:drag.pose.x+drag.delta[0]*dx+drag.deltaY[0]*dy,y:drag.pose.y+drag.delta[1]*dx+drag.deltaY[1]*dy};
    message=`Manual ${drag.yaw?'yaw':'XY'} gesture · release to apply`;slot('status').textContent=message;draw();
  });
  function finish(e){if(!drag)return;try{if(drag.next){session.prior(drag.id,drag.next);modified();message='Manual prior updated; pending proposal is stale.';}}catch(err){message=err.message;}drag=null;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);refresh();}
  listen(canvas,'pointerup',finish);listen(canvas,'pointercancel',()=>{drag=null;refresh();});
  listen(canvas,'keydown',e=>{
    const delta={ArrowLeft:{x:-.1},ArrowRight:{x:.1},ArrowUp:{y:.1},ArrowDown:{y:-.1},q:{yaw:-.05},e:{yaw:.05}}[e.key];if(busy||!delta||!field('target').value)return;e.preventDefault();
    try{const id=field('target').value,p=session.snapshot().draft.priors[id],next={};for(const[k,v]of Object.entries(delta))next[k]=p[k]+v;session.prior(id,next);modified();message='Keyboard manual prior updated.';}catch(err){message=err.message;}refresh();
  });
  const resize=new win.ResizeObserver(()=>{draw();scene?.resize();});resize.observe(canvas);
  const theme=new win.MutationObserver(()=>draw());theme.observe(doc.documentElement,{attributes:true,attributeFilter:['data-theme']});
  const ready=loadCatalogue().catch(e=>{message=failureMessage(e);refresh();});refresh();
  return {ready,snapshot:()=>session.snapshot(),refresh:()=>run(actions.reload)(),
    destroy(){destroyed=true;loadGeneration++;previewGeneration++;clearTimeout(timer);session.cancel();abort.abort();resize.disconnect();theme.disconnect();scene?.destroy();root.remove();}};
}
