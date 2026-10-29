import {createReplay,parseReview,frameAt,replayPacket,compareRuns,MAX_BYTES} from './replay.js';
export function mountRunReview(host, {scene, mountScene, adaptScene, clearScene=()=>{}}) {
  const doc=host.ownerDocument;
  const make=(tag,text='',cls='')=>{const el=doc.createElement(tag);el.textContent=text;el.className=cls;return el;};
  const root=make('section','','rr-root');
  const banner=make('div','REPLAY / 읽기 전용 · 로봇 제어 연결 없음','rr-banner');
  const title=make('h1','시험 기록 검토');
  const note=make('p','저장된 목표와 관측을 원래 시각으로 검토합니다. 미관측 사건은 성공이나 정지로 추정하지 않습니다.','rr-note');
  const inputs=make('div','','rr-inputs'), status=make('p','로컬 review.private.json을 선택하세요. 합성 예제 생성법은 HANDOFF에 있습니다.');
  const overview=make('pre','','rr-overview'), toolbar=make('div','','rr-toolbar');
  const play=make('button','재생'), pause=make('button','일시정지'), back=make('button','← 이전'), next=make('button','한 단계 →');
  const speed=make('select');speed.setAttribute('aria-label','재생 속도');
  for (const v of [.25,.5,1,2,4,-1]) {const o=make('option',v===-1?'역방향 1×':`${v}×`);o.value=v;speed.append(o);}speed.value='1';
  const seek=make('input');seek.type='range';seek.min='0';seek.max='0';seek.step='1';seek.value='0';seek.setAttribute('aria-label','재생 위치');
  const clock=make('output','REPLAY 0.000 s');
  toolbar.append(play,pause,back,next,speed,seek,clock);
  const columns=make('div','','rr-columns'), left=make('section'), right=make('section');
  const table=make('div','','rr-events');table.setAttribute('aria-label','이벤트 타임라인');
  const detail=make('pre','','rr-detail');detail.setAttribute('aria-label','원본 시각과 관측값');
  const precision=make('pre','','rr-precision'), comparison=make('div','','rr-comparison'), c3host=make('div','','rr-c3');
  left.append(make('h2','타임라인'),table);right.append(make('h2','선택 관측'),detail,make('h2','목표 정밀도 · 결과와 별도'),precision);
  columns.append(left,right);root.append(banner,title,note,inputs,status,overview,toolbar,columns,comparison,c3host);host.append(root);
  let runs=[null,null], replay=null, mounted=null, context=null, activeFrame=null, elapsed=0, generation=[0,0], disposed=false, pageStart=0;
  const unlisten=[];
  const on=(el,event,fn)=>{el.addEventListener(event,fn);unlisten.push(()=>el.removeEventListener(event,fn));};
  for (let i=0;i<2;i++) {
    const label=make('label',`실행 ${i?'B · 비교':'A · 재생'} `),input=make('input');input.type='file';input.accept='.json';input.dataset.run=String(i);label.append(input);inputs.append(label);
    on(input,'change',async()=>{
      const mine=++generation[i];clear(i);
      try {const f=input.files?.[0];if(!f)return;if(f.size>MAX_BYTES)throw new Error('64 MiB 제한');const raw=await f.text();if(mine!==generation[i]||disposed)return;load(parseReview(raw),i);}
      catch(e){if(mine===generation[i])status.textContent=`입력 차단 · ${e.message}`;}
    });
  }
  function resetScene() {mounted?.destroy();mounted=null;activeFrame=null;clearScene();}
  function clear(i) {runs[i]=null;if(i===0){replay?.pause();replay=null;resetScene();table.replaceChildren();detail.textContent='';precision.textContent='';overview.textContent='';}comparison.replaceChildren();}
  function showComparison() {
    comparison.replaceChildren();if(!runs[0]||!runs[1])return;
    const c=compareRuns(...runs);comparison.append(make('h2',c.classification));
    const rows=make('table');
    const tr=(...values)=>{const r=make('tr');for(const v of values)r.append(make('td',typeof v==='string'?v:JSON.stringify(v)));rows.append(r);};
    tr('조건 / 관측','실행 A','실행 B');
    for(const k of ['code_sha','parameters_revision','parameters_digest','map_id','map_revision','goal_id','data_kind','source_id'])tr(`${c.differences.includes(k)?'△ ':''}${k}`,runs[0].provenance[k]??'미관측',runs[1].provenance[k]??'미관측');
    for(const k of ['requested','result','near_result','after_stop','native_report_final'])tr(k,runs[0].precision[k]??'미관측',runs[1].precision[k]??'미관측');
    for(const k of ['recovery','cancel','stale','reconnect','command_zero','bridge_ack','measured_stop','contact'])tr(k,...runs.map(r=>r.observations[k]));
    tr('입력 공백 / 누락 / 수신 age',...runs.map(r=>r.quality));comparison.append(rows,make('p','오차 감소율을 알고리즘 개선율로 계산하지 않습니다. 관측 간격은 센서 상실·처리 지연과 다릅니다.'));
  }
  function update(state, reset) {
    if(disposed || !runs[0])return;
    const run=runs[0], event=run.events[state.index];elapsed=Number(BigInt(state.playhead))/1e6;
    seek.value=String(Math.round(elapsed));clock.textContent=`REPLAY ${(elapsed/1000).toFixed(3)} s · ${state.playing?'재생 중':'PAUSED'} · ${state.speed}×`;
    detail.textContent=JSON.stringify(event,null,2);
    if(state.index<pageStart || state.index>=pageStart+100)renderTable(Math.floor(state.index/100)*100);
    for (const button of table.querySelectorAll('button'))button.setAttribute('aria-current',String(Number(button.dataset.index)===state.index));
    const frame=frameAt(run,state);
    if(reset || frame?.context && JSON.stringify(frame.context)!==JSON.stringify(context))resetScene();
    if(!frame){if(mounted)resetScene();return;}
    if(!mounted) {
      context=frame.context;
      scene.focusSnapshot?.(frame.packet);
      let receiver;
      mounted=mountScene(c3host,{scene,getMap:()=>context,clock:()=>elapsed,
        subscribe:fn=>{receiver=fn;return()=>{receiver=null;};}});
      mounted.deliver=value=>receiver?.(value);
    }
    if(frame!==activeFrame || reset) {
      const result=replayPacket(frame,state,adaptScene);
      if(!result.packet){resetScene();status.textContent=`장면 차단 · ${result.reason}`;return;}
      activeFrame=frame;mounted.deliver(result.packet);
    }
  }
  function load(run,i=0) {
    clear(i);runs[i]=run;status.textContent=`실행 ${i?'B':'A'} · ${run.provenance.data_kind} · REPLAY · ${run.events.length}개 이벤트`;
    if(i===0) {
      overview.textContent=JSON.stringify(run.provenance,null,2);
      precision.textContent=JSON.stringify({note:'결과 수신 부근 / 측정 정지 후 표본. ZERO ≠ ACK ≠ 측정 정지 ≠ 접촉.',...run.precision,observations:run.observations},null,2);
      replay=createReplay(run,update);seek.max=String(Math.ceil(Number(BigInt(replay.state().end))/1e6));
      renderTable(0);replay.seek('0');
    }
    showComparison();
  }
  function renderTable(start) {
    table.replaceChildren();pageStart=start;const run=runs[0];
    if(start>0){const b=make('button','이전 100개');b.dataset.page=String(Math.max(0,start-100));table.append(b);}
    for(const e of run.events.slice(start,start+100)) {
      const button=make('button',`${(Number(BigInt(e.replay_ns))/1e9).toFixed(3)} s  ${e.kind} · ${e.time.value??'시각 미관측'}`);
      button.dataset.index=String(e.index);table.append(button);
    }
    if(run.events.length>start+100){const b=make('button','다음 100개');b.dataset.page=String(start+100);table.append(b);}
  }
  on(table,'click',event=>{const button=event.target.closest('button');if(!button)return;if(button.dataset.page!==undefined)renderTable(Number(button.dataset.page));else if(button.dataset.index!==undefined){replay.pause();replay.seek(runs[0].events[Number(button.dataset.index)].replay_ns);}});
  on(play,'click',()=>replay?.play());on(pause,'click',()=>replay?.pause());on(next,'click',()=>replay?.step());on(back,'click',()=>replay?.step(-1));
  on(speed,'change',()=>replay?.speed(Number(speed.value)));on(seek,'input',()=>{replay?.pause();replay?.seek(String(Math.round(Number(seek.value)*1e6)));});
  let last=performance.now();const timer=setInterval(()=>{const now=performance.now();replay?.tick(Math.min(1000,now-last));last=now;},30);
  return {load:(run,i=0)=>{generation[i]++;load(parseReview(JSON.stringify(run)),i);},get replay(){return replay;},get sceneFeature(){return mounted;},
    destroy(){disposed=true;generation=generation.map(g=>g+1);clearInterval(timer);unlisten.splice(0).forEach(f=>f());resetScene();root.remove();}};
}
