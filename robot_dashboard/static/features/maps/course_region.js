import {validateRegion} from '../map_editor3d/core.js';

export function coursePolygon(polygon) {
  if(!Array.isArray(polygon) || polygon.length>64 || polygon.some(p=>p.some(n=>Math.abs(n)>1000))) throw new Error('코스 경계는 ±1000m 이내, 3~64개 꼭짓점으로 지정하세요.');
  return validateRegion({kind:'localization',polygon,z_min:-1e6,z_max:1e6}).polygon.map(p=>[...p]);
}

// Deliberately a central-area proposal, not semantic wall/course segmentation.
export function proposeCourse(points) {
  const xs=[],ys=[], stride=Math.max(1,Math.ceil(points.length/3/20000));
  for(let i=0;i<points.length;i+=3*stride) if(Number.isFinite(points[i])&&Number.isFinite(points[i+1])) {xs.push(points[i]);ys.push(points[i+1]);}
  if(xs.length<4) throw new Error('지도 점군을 불러온 뒤 제안해 주세요.');
  xs.sort((a,b)=>a-b);ys.sort((a,b)=>a-b);
  const range=a=>{const lo=a[Math.floor((a.length-1)*.05)],hi=a[Math.floor((a.length-1)*.95)],inset=(hi-lo)*.25;return [lo+inset,hi-inset];};
  const [x0,x1]=range(xs),[y0,y1]=range(ys);
  return coursePolygon([[x0,y0],[x1,y0],[x1,y1],[x0,y1]]);
}

export class CourseDraft {
  constructor(){this.map=null;this.revision=0;this.polygon=[];this.active=null;this.weight=.25;this.pending=false;}
  setMap(map){
    const next=map&&{id:map.id,revision:map.revision,frame:map.frame};
    if(JSON.stringify(next)===JSON.stringify(this.map))return false;
    this.map=next;this.revision++;this.polygon=[];this.active=null;this.pending=false;return true;
  }
  edit(polygon,weight=this.weight){this.polygon=polygon.map(p=>[...p]);this.weight=weight;this.active=null;this.pending=true;this.revision++;}
  use(value){
    if(!this.map || value.map_id!==this.map.id || value.map_revision!==this.map.revision || value.map_frame!==this.map.frame
      || value.confirmed!==true || value.units!=='m' || !Number.isFinite(value.outside_weight) || value.outside_weight<.1 || value.outside_weight>1)throw new Error('지도와 저장 영역이 다릅니다. 경계를 다시 확인하세요.');
    this.polygon=coursePolygon(value.polygon);this.weight=value.outside_weight;
    this.active={...value,polygon:this.polygon.map(p=>[...p])};this.pending=false;this.revision++;
  }
  clear(){this.polygon=[];this.active=null;this.pending=false;this.revision++;}
  accepts(revision){return this.revision===revision;}
}

export function initializeCourseRegion({host,scene,changed,beforeEdit}) {
  const draft=new CourseDraft(),panel=document.createElement('details');panel.id='mapCourse';panel.open=true;
  panel.innerHTML=`<summary>코스 영역 · 지도에 저장</summary>
    <p>경계 안의 점을 우선해 초기 정합합니다. 경계는 모든 높이에 적용되며 벽을 자동 분류하지 않습니다. 기존 전체 점군 품질 검사는 유지합니다.</p>
    <div class="saved-live-actions"><button type="button" id="mapCourseSuggest">중앙 영역 자동 제안</button><button type="button" id="mapCourseDraw">코스 경계 직접 표시</button><button type="button" id="mapCourseUndo">마지막 점 취소</button><button type="button" id="mapCourseFinish">경계 표시 완료</button><button type="button" id="mapCourseCancel">편집 취소 / Esc</button></div>
    <label>주변 점 비중 (코스 안 100%) <select id="mapCourseWeight"><option value="0.25">25% · 초기 설정</option><option value="0.5">50%</option><option value="1">100% · 동일 비중</option></select></label>
    <label>영역 이름 <input id="mapCourseName" maxlength="64" value="코스 영역"></label>
    <button type="button" id="mapCourseSave">영역 확인·저장</button>
    <label>이 지도에 저장된 영역 <select id="mapCourseSaved"><option value="">사용 안 함</option></select></label>
    <button type="button" id="mapCourseReload">저장 영역 다시 불러오기</button>
    <p id="mapCourseStatus" role="status"></p>`;
  host.append(panel);
  const el=name=>panel.querySelector('#mapCourse'+name);
  let drawing=false,visible=true,view=null,backup=null,busy=false,disposed=false,presets=[],message='',loadToken=0,ownedPointer=null;
  function preview(){scene.setCourseRegionPreview(visible&&draft.map?{frameId:draft.map.frame,polygon:draft.polygon,confirmed:!!draft.active}:null);}
  function draw(){
    if(disposed)return;
    for(const name of ['Suggest','Draw','Weight','Reload','Saved'])el(name).disabled=!draft.map||busy;
    el('Undo').disabled=!drawing||!draft.polygon.length;el('Finish').disabled=!drawing||draft.polygon.length<3;
    el('Cancel').disabled=!draft.pending&&!drawing;
    el('Save').disabled=!draft.map||!draft.pending||draft.polygon.length<3||drawing||busy;
    if(![...el('Weight').options].some(o=>o.value===String(draft.weight)))el('Weight').add(new Option(`${draft.weight*100}%`,String(draft.weight)));
    el('Weight').value=String(draft.weight);
    el('Status').textContent=message || (draft.active?`저장된 코스 영역 사용 · ${draft.polygon.length}개 꼭짓점 · 코스 100% / 주변 ${draft.weight*100}% · 같은 지도에서 다시 불러옵니다.`:draft.pending?`미확인 영역 · ${draft.polygon.length}개 꼭짓점 · 확인·저장 전에는 정합을 시작하지 않습니다.`:'코스 영역 없음 · 전체 대응점 동일 비중');
    preview();
  }
  function notify(){changed(draft.active,draft.pending);draw();}
  function stop(){
    if(!drawing)return;drawing=false;ownedPointer=null;
    if(view){scene.setCameraMode(view.mode);scene.camera={...view.camera,target:[...view.camera.target]};scene.canvas.style.cursor=view.cursor;scene._invalidateStatic();scene.render();}view=null;
  }
  function remember(){if(!draft.pending)backup=draft.active&&structuredClone(draft.active);}
  function cancel(){stop();if(backup)draft.use(backup);else draft.clear();backup=null;message='';notify();}
  function edit(polygon){draft.edit(polygon);message='';notify();}
  el('Suggest').onclick=()=>{beforeEdit();stop();remember();try{edit(proposeCourse(scene.cloud.points));message='중앙 사각형 초안입니다. 경계 자동 인식이 아니므로 확인하거나 직접 다시 그려 주세요.';}catch(e){message=e.message;}draw();};
  el('Draw').onclick=()=>{
    beforeEdit();remember();if(!drawing)view={camera:{...scene.camera,target:[...scene.camera.target]},mode:scene.cameraMode,cursor:scene.canvas.style.cursor};
    drawing=true;scene.setCameraMode('world');scene.topView();scene.canvas.style.cursor='crosshair';edit([]);
    message='코스 둘레를 순서대로 클릭한 뒤 ‘경계 표시 완료’를 누르세요. 휠: 확대 · Shift/우클릭: 이동';draw();scene.canvas.scrollIntoView({block:'center',behavior:'smooth'});
  };
  el('Undo').onclick=()=>edit(draft.polygon.slice(0,-1));
  el('Finish').onclick=()=>{try{draft.polygon=coursePolygon(draft.polygon);stop();message='경계를 확인한 뒤 이름을 입력하고 저장하세요.';}catch(e){message=e.message;}draw();};
  el('Cancel').onclick=cancel;
  el('Weight').onchange=()=>{remember();draft.edit(draft.polygon,Number(el('Weight').value));message='비중 변경 · 영역 확인·저장 후 사용합니다.';notify();};
  function options(){el('Saved').replaceChildren(new Option('사용 안 함',''));for(const p of presets)el('Saved').add(new Option(p.label,p.id));}
  async function load(){
    if(!draft.map)return;const revision=draft.revision,token=++loadToken,map={...draft.map};
    try{
      const response=await fetch(`/api/v1/observations/course-regions/${map.id}`,{cache:'no-store',signal:AbortSignal.timeout(10000)}),data=await response.json();
      if(disposed||token!==loadToken||!draft.accepts(revision))return;
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${response.status}`);
      if(data.map?.map_id!==map.id||data.map?.map_revision!==map.revision||data.map?.map_frame!==map.frame)throw new Error('지도 좌표가 변경됐습니다. 지도를 다시 선택하세요.');
      presets=data.presets;options();
      const latest=presets.at(-1);if(latest){draft.use(latest.values);el('Saved').value=latest.id;message='';notify();}
      else{message=data.incompatible_count?'이전 지도 좌표의 저장 영역은 적용하지 않았습니다. 현재 지도에 경계를 다시 표시하세요.':'';draw();}
    }catch(e){if(token===loadToken&&draft.accepts(revision)){message=`저장 영역을 불러오지 못했습니다: ${e.message}`;draw();}}
  }
  el('Reload').onclick=()=>{if(draft.pending){message='편집을 저장하거나 취소한 뒤 다시 불러오세요.';draw();}else void load();};
  el('Saved').onchange=()=>{
    beforeEdit();stop();backup=null;const value=presets.find(p=>p.id===el('Saved').value);
    try{if(value)draft.use(value.values);else draft.clear();message='';notify();}catch(e){message=e.message;draw();}
  };
  el('Save').onclick=async()=>{
    let polygon;try{polygon=coursePolygon(draft.polygon);}catch(e){message=e.message;draw();return;}
    const revision=draft.revision,map={...draft.map};busy=true;draw();
    try{
      const response=await fetch(`/api/v1/observations/course-regions/${map.id}`,{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(10000),
        body:JSON.stringify({name:el('Name').value,map_revision:map.revision,map_frame:map.frame,polygon,outside_weight:draft.weight,confirmed:true})});
      const data=await response.json();if(disposed||!draft.accepts(revision))return;
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${response.status}`);
      draft.use(data.preset.values);presets.push(data.preset);options();el('Saved').value=data.preset.id;backup=null;message='';notify();
    }catch(e){if(draft.accepts(revision)){message=`저장 확인 실패: ${e.message} · 응답이 끊겼다면 편집 취소 후 다시 불러와 확인하세요.`;}}
    finally{busy=false;draw();}
  };
  const down=e=>{if(!drawing||e.button!==0||e.shiftKey||e.ctrlKey||e.metaKey||e.altKey)return;
    e.preventDefault();e.stopImmediatePropagation();ownedPointer=e.pointerId;if(draft.polygon.length>=64)return;
    const p=scene.screenToMapPlane(e.clientX,e.clientY,scene.options.groundZ||0);if(p)edit([...draft.polygon,p.slice(0,2)]);
  };
  const block=e=>{if(drawing&&(e.type==='dblclick'||e.pointerId===ownedPointer)){e.preventDefault();e.stopImmediatePropagation();ownedPointer=null;}};
  const key=e=>{if(drawing&&e.key==='Escape'){e.preventDefault();cancel();}};
  for(const [name,fn] of [['pointerdown',down],['pointerup',block],['dblclick',block]])scene.canvas.addEventListener(name,fn,true);
  document.addEventListener('keydown',key);
  return {
    render(map,show){visible=show;if(draft.setMap(map)){stop();backup=null;presets=[];options();message='';notify();void load();}if(!visible)stop();draw();},
    stop, get pending(){return draft.pending;},
    destroy(){disposed=true;loadToken++;stop();document.removeEventListener('keydown',key);
      for(const [name,fn] of [['pointerdown',down],['pointerup',block],['dblclick',block]])scene.canvas.removeEventListener(name,fn,true);
      scene.setCourseRegionPreview(null);panel.remove();},
  };
}
