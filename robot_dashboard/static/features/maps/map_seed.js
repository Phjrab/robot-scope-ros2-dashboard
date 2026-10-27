import { GlobalObservationController } from './global_observation_contract.js';
import { anchorSourceContract, sameAnchorSource } from './anchor_proposal.js';
import { ANCHOR_FIELDS, validAnchorPose } from './anchor_presets.js';
import { isRigidTransform } from '../experiments/recorded_report.js';

const radians = p => p && ({...p, roll:p.roll*Math.PI/180, pitch:p.pitch*Math.PI/180, yaw:p.yaw*Math.PI/180});
export const DEFAULT_SEED_BOUNDS = Object.freeze({xy_m:.75, yaw_deg:25, z_m:.3, tilt_deg:10});
export class MapSeedDraft {
  constructor() { this.revision=0; this.pose=null; this.direction=false; this.heightSource='approximate'; this.bounds={...DEFAULT_SEED_BOUNDS}; this.map=null; }
  setMap(map) {
    const next=map && {id:map.id,revision:map.revision,frame:map.frame};
    if(JSON.stringify(next)===JSON.stringify(this.map)) return false;
    this.map=next; this.pose=null; this.direction=false; this.revision++; return true;
  }
  edit(pose,{direction=true,heightSource=this.heightSource}={}) {
    this.pose=Object.fromEntries(ANCHOR_FIELDS.map(k=>[k,pose[k]]));
    this.direction=direction; this.heightSource=heightSource; this.revision++;
  }
  get valid() { return Boolean(this.map && this.direction && validAnchorPose(this.pose)); }
  request(inputs) {
    const source=anchorSourceContract(inputs);
    if(!this.valid || !source) throw new Error('초기 위치·방향과 신선한 FAST-LIO 입력이 필요합니다.');
    return {revision:this.revision,pose:{...this.pose},pose_reference:'FASTLIO_IMU',units:'metres_degrees',
      map_frame:this.map.frame,height_source:this.heightSource,bounds:{...this.bounds},source_contract:source};
  }
}
export function validSeedCandidate(value, draft, inputs, jobId) {
  return value?.schema==='robot-scope.anchor-proposal.v1' && value.search_mode==='seeded_local'
    && value.job_id===jobId && value.seed_revision===draft.revision
    && ['id','revision','frame'].every(k=>value.map?.[k]===draft.map?.[k])
    && sameAnchorSource(value.source_contract,anchorSourceContract(inputs))
    && value.pose_reference==='FASTLIO_IMU' && value.units==='metres_degrees' && validAnchorPose(value.pose)
    && isRigidTransform(value.T_map_odom) && typeof value.admissible==='boolean'
    && value.operational_application==='NOT_RUN' && value.absolute_accuracy_m===null
    && value.body_extrinsic_verified===false && value.approximate_only===true && value.requires_reanchor===true
    && typeof value.ambiguity_unresolved==='boolean' && Number.isFinite(value.runtime_ms) && value.runtime_ms>=0
    && (value.rmse_m===null || (Number.isFinite(value.rmse_m) && value.rmse_m>=0))
    && Number.isFinite(value.overlap) && value.overlap>=0 && value.overlap<=1
    && typeof value.capture_stamp_ns==='string' && /^[1-9][0-9]{0,19}$/.test(value.capture_stamp_ns)
    && typeof value.proposal_stamp_ns==='string' && /^[1-9][0-9]{0,19}$/.test(value.proposal_stamp_ns)
    && BigInt(value.proposal_stamp_ns)>=BigInt(value.capture_stamp_ns)
    && Number.isFinite(value.pose_age_s) && value.pose_age_s>=0 && value.pose_age_s<=1
    && ['xy_m','yaw_deg','z_m','tilt_deg'].every(k=>Number.isFinite(value.delta?.[k]) && value.delta[k]>=0
      && value.bounds?.[k]===draft.bounds[k] && (!value.admissible || value.delta[k]<=draft.bounds[k]+1e-8))
    && (!value.admissible || (value.reason==='CANDIDATE' && value.numerical?.status==='CANDIDATE'
      && value.numerical.metrics?.converged===true && value.rmse_m!==null && value.rmse_m<=.05 && value.overlap>=.6
      && value.numerical.metrics.geometry_min_max_eigen_ratio>=.002
      && value.numerical.metrics.matched_geometry_min_max_eigen_ratio>=.002));
}

export function initializeMapSeed({host,scene,getState,getInputs,readPose,writePose,apply,edited}) {
  const draft=new MapSeedDraft(), panel=document.createElement('div'); panel.className='map-seed'; panel.id='mapSeed';
  panel.innerHTML=`<strong>지도에서 초기 위치·방향 지정</strong>
    <p>초기값(주황) → 주변 정합 후보(파랑) → 명시적으로 적용. 현재 관측 위치는 적용 전까지 유지합니다.</p>
    <div class="saved-live-actions"><button id="mapSeedPlace" type="button">지도에서 초기 위치 지정</button><button id="mapSeedAgain" type="button" disabled>다시 지정</button><button id="mapSeedCancel" type="button" disabled>취소 / Esc</button><button id="mapSeedKeepYaw" type="button" disabled>기존 방향 유지</button></div>
    <p id="mapSeedSummary" role="status"></p>
    <p>XY 작업 평면에 투영합니다. 바닥 높이를 IMU 높이로 사용하지 않습니다. 실루엣은 IMU=본체 근사이며 실제 로봇 이동 명령이 아닙니다.</p>
    <div class="saved-live-actions"><button id="mapSeedSearch" type="button" disabled>이 주변에서 자동 정합</button><button id="mapSeedRetry" type="button" hidden>같은 요청 재확인</button><button id="mapSeedWiden" type="button">범위 넓히기</button><button id="mapSeedStop" type="button" disabled>정합 취소</button></div>
    <small>정지한 현재 위치의 초기값으로 계산합니다. 단일 초기값 지역 보정이며 다른 장소의 모호함은 검증되지 않습니다.</small>
    <details id="mapSeedBounds"><summary>탐색 범위 조정</summary>${[['xy_m','위치 반경 (m)',.1,3,.1],['yaw_deg','방향 ± (°)',1,90,1],['z_m','높이 ± (m)',.01,1,.01],['tilt_deg','기울기 ± (°)',1,30,1]].map(([k,label,min,max,step])=>`<label>${label}<input data-seed-bound="${k}" type="number" min="${min}" max="${max}" step="${step}" value="${draft.bounds[k]}"></label>`).join('')}</details>
    <p id="mapSeedResult" role="status">정합 후보 없음</p><button id="mapSeedApply" type="button" disabled>제안 위치로 적용</button>`;
  host.prepend(panel);
  const el=id=>panel.querySelector('#mapSeed'+id);
  let candidate=null, loading=false, loadedJob=null, message='', token=0, placing=false, phase='position', drag=null,
    view=null, backup=null, sourceKey='', visible=true, disposed=false, boundsValid=true, applied=false;
  const controller=new GlobalObservationController({inputKind:'fastlio_imu', getProvenanceMode:()=>getInputs().mode,
    getRequestOptions:()=>({search_mode:'seeded_local',seed:draft.valid?draft.request(getInputs()):null}),changed:draw});
  // Snapshot must remain usable while sensors are offline; request() runs only at start.
  controller.getRequestOptions=()=>({search_mode:'seeded_local',seed:draft.valid && anchorSourceContract(getInputs())?draft.request(getInputs()):null});
  function invalidate() { token++; candidate=null; applied=false; loadedJob=null; controller.invalidate('SEED_CHANGED'); }
  function update(pose, options={}, notify=true) {
    draft.edit(pose,options); message=''; invalidate(); writePose(draft.pose); if(notify) edited(); draw();
  }
  function endPlacement(restore=false) {
    if(!placing) return;
    placing=false;
    if(drag && scene.canvas.hasPointerCapture?.(drag.id)) scene.canvas.releasePointerCapture(drag.id);
    drag=null; scene.canvas.style.cursor=view?.cursor || 'grab';
    if(view) { scene.setCameraMode(view.mode); scene.camera={...view.camera,target:[...view.camera.target]}; scene._invalidateStatic(); scene.render(); }
    view=null;
    if(restore && backup?.pose) update(backup.pose,{direction:backup.direction,heightSource:backup.heightSource});
    else if(restore) { draft.pose=null; draft.direction=false; draft.revision++; invalidate(); writePose(backup.values); }
    if(restore) message='배치를 취소했습니다. 이전 초기값과 현재 관측은 유지합니다.';
    draw();
  }
  function place() {
    if(!draft.map) return;
    if(!placing) {
      backup={pose:draft.pose && {...draft.pose},values:readPose(),direction:draft.direction,heightSource:draft.heightSource};
      view={camera:{...scene.camera,target:[...scene.camera.target]},mode:scene.cameraMode,cursor:scene.canvas.style.cursor};
      scene.setCameraMode('world'); scene.topView(); placing=true;
    }
    phase='position'; message='지도 클릭 후 방향을 드래그하거나 두 번째로 클릭하세요. 휠: 확대 · Shift/우클릭: 이동';
    scene.canvas.style.cursor='crosshair'; scene.canvas.scrollIntoView({block:'center',behavior:'smooth'}); draw();
  }
  function preview() {
    scene.setInitializationPreview(visible?{frameId:draft.map?.frame,draft:validAnchorPose(draft.pose)?radians(draft.pose):null,
      candidate:radians(candidate?.pose),applied,radius:draft.bounds.xy_m,yawRange:draft.bounds.yaw_deg}:null);
  }
  function draw() {
    if(disposed) return;
    const state=controller.snapshot(), live=getState();
    if(candidate && state.record?.job_id!==candidate.job_id) {candidate=null;applied=false;}
    el('Place').disabled=!draft.map; el('Again').disabled=!placing; el('Cancel').disabled=!placing;
    el('KeepYaw').disabled=!placing || !draft.pose || !(backup?.direction);
    el('Search').disabled=!draft.valid || !boundsValid || !live.canAnchor || !anchorSourceContract(getInputs()) || !state.canStart || loading;
    el('Retry').hidden=!state.canRetry; el('Retry').disabled=!draft.valid || !boundsValid || !live.canAnchor || loading;
    el('Stop').disabled=!state.canCancel; el('Apply').disabled=!candidate?.admissible || !live.canAnchor || loading || state.busy;
    const p=draft.pose;
    el('Summary').textContent=p?`사용자 초기값: X ${p.x.toFixed(2)} · Y ${p.y.toFixed(2)} · Z ${p.z.toFixed(2)} m · 방향 ${p.yaw.toFixed(1)}°${draft.direction?'':' · 방향 지정 대기'} · ${draft.heightSource==='approximate'?'높이·자세 근사':'기존 높이·자세 보존'} · 반경 ${draft.bounds.xy_m}m / ±${draft.bounds.yaw_deg}°${placing?' · '+message:''}`:'지도에서 위치와 방향을 지정하세요. 센서 없이도 초안을 만들 수 있습니다.';
    const result=state.record?.result?.observation;
    el('Result').textContent=candidate
      ? `${candidate.admissible?(applied?'제안 위치를 관측 기준점으로 적용했습니다':'정합 후보 · 미적용'):'적용 불가 · '+candidate.reason} | 초기값 대비 ${candidate.delta.xy_m.toFixed(3)}m / ${candidate.delta.yaw_deg.toFixed(1)}° · Z ${candidate.delta.z_m.toFixed(3)}m | RMSE ${candidate.rmse_m==null?'미제공':candidate.rmse_m.toFixed(3)+'m'} · overlap ${(candidate.overlap*100).toFixed(1)}% · ${(candidate.runtime_ms/1000).toFixed(2)}초 · 다른 장소 모호함 미검증${candidate.admissible?'':' · 초기값을 다시 지정하거나 범위를 넓혀 주세요. 지도 전체 탐색도 직접 선택할 수 있습니다.'}`
      : message && !placing?message:state.error || (state.busy?'지정한 주변 정합 중 · 현재 관측 유지':result?.reason || state.job?.reason || '정합 후보 없음');
    preview();
    if(state.record && loadedJob!==state.record.job_id && !loading) void loadCandidate(false);
  }
  async function loadCandidate(applying) {
    const job=controller.snapshot().record?.job_id;
    if(!job || loading) return;
    const current=token, revision=draft.revision; loading=true; loadedJob=job; draw();
    try {
      const response=await fetch(`/api/v1/observations/global-jobs/${job}/anchor-proposal`,{cache:'no-store',signal:AbortSignal.timeout(10000)});
      const value=await response.json();
      if(current!==token || revision!==draft.revision || disposed) return;
      if(!response.ok) throw new Error(typeof value.detail==='string'?value.detail:`HTTP ${response.status}`);
      if(!validSeedCandidate(value,draft,getInputs(),job)) throw new Error('지도·초기값·출처가 변경됐습니다. 다시 정합하세요.');
      candidate=value;
      if(applying) {
        if(!value.admissible || !getState().canAnchor) throw new Error('이 후보는 적용할 수 없습니다.');
        apply(value); applied=true; message='제안 위치를 관측 기준점으로 적용했습니다.';
      }
    } catch(error) { if(current===token) {candidate=null; message=error.message;} }
    finally {loading=false; draw();}
  }
  function point(event) { return scene.screenToMapPlane(event.clientX,event.clientY,scene.options.groundZ || 0); }
  function hit(pose,event,offset=0) {
    if(!pose) return false;
    const p=scene._project([pose.x+offset*Math.cos(pose.yaw*Math.PI/180),pose.y+offset*Math.sin(pose.yaw*Math.PI/180),pose.z]);
    const r=scene.canvas.getBoundingClientRect();
    return p && Math.hypot((event.clientX-r.left)*scene.width/r.width-p.x,(event.clientY-r.top)*scene.height/r.height-p.y)<18;
  }
  function yawAt(p) {
    const a=draft.pose;
    if(Math.hypot(p[0]-a.x,p[1]-a.y)<.05) return;
    update({...a,yaw:Math.atan2(p[1]-a.y,p[0]-a.x)*180/Math.PI},{direction:true});
  }
  const down=event=>{
    if(!placing || event.button!==0 || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    const p=point(event); if(!p) return;
    event.preventDefault(); event.stopImmediatePropagation(); scene.canvas.setPointerCapture?.(event.pointerId);
    let mode=phase==='direction'?'yaw':hit(draft.pose,event,.9)?'yaw':hit(draft.pose,event)?'move':'place';
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,mode};
    if(mode==='yaw') yawAt(p);
    else if(mode==='move') update({...draft.pose,x:p[0],y:p[1]},{direction:draft.direction});
    else {
      const state=getState(), active=state.pose_reference==='FASTLIO_IMU'?state.pose:null, saved=readPose();
      const base=draft.pose || (active?{...active,roll:active.roll*180/Math.PI,pitch:active.pitch*180/Math.PI,yaw:active.yaw*180/Math.PI}:validAnchorPose(saved)?saved:{x:0,y:0,z:0,roll:0,pitch:0,yaw:0});
      update({...base,x:p[0],y:p[1]},{direction:false,heightSource:draft.pose?draft.heightSource:active?'active_imu':'approximate'});
    }
  };
  const move=event=>{
    if(!drag || drag.id!==event.pointerId) return;
    event.preventDefault();event.stopImmediatePropagation(); const p=point(event);if(!p)return;
    if(drag.mode==='move') update({...draft.pose,x:p[0],y:p[1]},{direction:draft.direction});
    else if(drag.mode==='yaw' || Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>=6) yawAt(p);
  };
  const up=event=>{
    if(!drag || drag.id!==event.pointerId)return;
    event.preventDefault();event.stopImmediatePropagation();scene.canvas.releasePointerCapture?.(event.pointerId);
    drag=null;phase=draft.direction?'position':'direction';
    message=draft.direction?'위치를 다시 클릭하거나 모델·방향 끝 핸들을 드래그해 수정하세요.':'두 번째 클릭으로 방향을 정하세요.';draw();
  };
  const cancelPointer=e=>{if(drag){up(e);endPlacement(true);}};
  const key=e=>{if(placing && e.key==='Escape'){e.preventDefault();endPlacement(true);}};
  const double=e=>{if(placing){e.preventDefault();e.stopImmediatePropagation();}};
  for(const [name,fn] of [['pointerdown',down],['pointermove',move],['pointerup',up],['pointercancel',cancelPointer],['dblclick',double]]) scene.canvas.addEventListener(name,fn,true);
  document.addEventListener('keydown',key);
  el('Place').onclick=place;el('Again').onclick=place;el('Cancel').onclick=()=>endPlacement(true);
  el('KeepYaw').onclick=()=>{if(draft.pose && backup?.direction){update({...draft.pose,yaw:backup.pose.yaw});phase='position';}};
  el('Search').onclick=el('Retry').onclick=async()=>{endPlacement();message='';await controller.start();draw();};
  el('Stop').onclick=()=>{token++;candidate=null;message='정합 취소 · 초기값과 현재 관측 유지';void controller.cancel();};
  el('Apply').onclick=()=>void loadCandidate(true);
  function changeBounds() {
    boundsValid=false; draft.revision++; invalidate();
    const next={};for(const input of panel.querySelectorAll('[data-seed-bound]')) {
      const n=Number(input.value);if(!input.value.trim()||!Number.isFinite(n)||n<Number(input.min)||n>Number(input.max)){message='탐색 범위의 유효한 값을 입력하세요.';draw();return;}
      next[input.dataset.seedBound]=n;
    }
    draft.bounds=next;boundsValid=true;message='';draw();
  }
  for(const input of panel.querySelectorAll('[data-seed-bound]')) input.addEventListener('input',changeBounds);
  el('Widen').onclick=()=>{for(const input of panel.querySelectorAll('[data-seed-bound]')) input.value=String(Math.min(Number(input.max),Number(input.value)*2));changeBounds();};
  const timer=setInterval(()=>{if(visible)void controller.poll();},1000);
  return {
    edit:(pose,source='manual')=>update(pose,{heightSource:source},false),
    render:show=>{
      visible=show;const state=getState();controller.setMap(state.map && {...state.map,kind:'pointcloud3d',frame_id:state.map.frame},null);
      if(draft.setMap(state.map)){endPlacement();invalidate();}
      const source=JSON.stringify(anchorSourceContract(getInputs()));
      if(sourceKey && source!==sourceKey){invalidate();message='출처 변경 · 위치 초안은 보존했습니다. 정지한 현재 위치에서 다시 정합하세요.';}
      sourceKey=source;
      if(!visible)endPlacement();draw();
    },
    invalidateSource:()=>{invalidate();endPlacement();},
    destroy:()=>{disposed=true;endPlacement();clearInterval(timer);controller.destroy();scene.setInitializationPreview(null);
      document.removeEventListener('keydown',key);
      for(const [name,fn] of [['pointerdown',down],['pointermove',move],['pointerup',up],['pointercancel',cancelPointer],['dblclick',double]]) scene.canvas.removeEventListener(name,fn,true);
      panel.remove();},
    snapshot:()=>({revision:draft.revision,pose:draft.pose,candidate,placing}),
  };
}
