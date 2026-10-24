import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function fixture(page, { points = [] } = {}) {
  const backend = await installDashboardBackend(page);
  const mapId='0123456789abcdef01234567', rev='a'.repeat(64), planId='f'.repeat(32), annRev='b'.repeat(64);
  const family={family_id:'1'.repeat(24),family_revision:'2'.repeat(64),source:{pcd_map_id:'3'.repeat(24),pcd_revision:'4'.repeat(64)},occupancy:{map_id:mapId,map_revision:rev}};
  const writes=[]; let plan=null;
  await page.route('**/api/v1/routes',r=>r.fulfill({json:{routes:[]}}));
  await page.route(`**/api/v1/saved-maps/${mapId}/data`,r=>r.fulfill({json:{map_id:mapId,revision:rev,kind:'occupancy2d',frame_id:'map',width:100,height:100,resolution:.1,origin:[2,-3,Math.PI/2],data_b64:Buffer.alloc(10000).toString('base64')}}));
  await page.route(`**/api/v1/saved-maps/${mapId}/family`,r=>r.fulfill({json:{map_id:mapId,map_revision:rev,families:[family]}}));
  await page.route(`**/api/v1/saved-maps/${mapId}/annotations`,r=>r.fulfill({json:{map_id:mapId,map_revision:rev,annotation_revision:annRev,points,polygons:[]}}));
  await page.route('**/api/v1/mission-runs',r=>r.fulfill({json:{runs:[]}}));
  await page.route('**/api/v1/mission-plans',r=>{
    if(r.request().method()==='GET') return r.fulfill({json:{definitions:plan?[plan]:[],context:{navigation_map:{id:mapId,revision:rev},pose_source:{source:'/amcl_pose',odometry_source:'/Odometry',readiness:'localized'},blocking_reasons:['RUNTIME_POLICY_NOT_ENFORCED']}}});
    const {request_id,...definition}=r.request().postDataJSON(); writes.push(definition); plan={id:planId,revision:'c'.repeat(64),definition}; return r.fulfill({status:201,json:{plan}});
  });
  await page.route(`**/api/v1/mission-plans/${planId}`,r=>r.fulfill({status:409,json:{detail:'DEFINITION_REVISION_CHANGED'}}));
  await page.route(`**/api/v1/mission-plans/${planId}/validate`,r=>r.fulfill({json:{status:'PASS',scope:'authoring',actual_nav2_run:false,validation:{violations:[]},execution_readiness:{blocking_reasons:['RUNTIME_POLICY_NOT_ENFORCED']}}}));
  await page.route(`**/api/v1/mission-plans/${planId}/plan-preview`,r=>r.fulfill({status:503,json:{detail:'NATIVE_PLANNER_RESOURCE_WINDOW_REQUIRED'}}));
  await page.goto('/#missions');
  const workspace=page.locator('.mr-workspace'); await expect(workspace).toBeVisible();
  await expect(workspace).toHaveAttribute('data-busy','false');
  await workspace.evaluate(element=>{ const evidence=document.createElement('p'); evidence.textContent='UI fixture / 주행 검증 아님'; evidence.dataset.uiEvidence='fixture'; evidence.style.cssText='grid-column:1/-1;font-weight:bold;color:#d03'; element.prepend(evidence); });
  await workspace.getByRole('button',{name:'지도 불러오기 / 새 미션',exact:true}).click();
  await expect(workspace.locator('svg image')).toHaveCount(1);
  return {backend,workspace,writes,mapId,rev,planId,annRev,family,getPlan:()=>plan};
}

test('MR map and list select visits, hold/confirmation persist, polling preserves focused input',async({page})=>{
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  const {workspace,writes,backend}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add');
  const canvas=workspace.locator('svg'); await canvas.click({position:{x:180,y:180}});
  await expect(workspace.locator('ol li')).toHaveCount(1);
  await workspace.getByLabel('방문 이름',{exact:true}).fill('긴 한글 점검 지점');
  await workspace.getByLabel('도착 후 대기(초)',{exact:true}).fill('3.5');
  await workspace.getByLabel('도착 후 운영자 확인',{exact:true}).check();
  const name=workspace.getByLabel('미션 이름',{exact:true}); await name.fill('입력 중인 미션');
  await expect(name).toBeFocused(); await expect(name).toHaveValue('입력 중인 미션');
  await workspace.getByRole('button',{name:'복제',exact:true}).click();
  await expect(workspace.locator('ol li')).toHaveCount(2);
  await workspace.getByRole('button',{name:'위로',exact:true}).click();
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  expect(writes[0].visits).toHaveLength(2);
  expect(writes[0].visits[0].hold_seconds).toBe(3.5);
  expect(writes[0].visits[0].after_arrival_confirmation).toBe(true);
  expect(writes[0].visits[0].visit_id).not.toBe(writes[0].visits[1].visit_id);
  await workspace.getByRole('button',{name:'작성 검사',exact:true}).click();
  await expect(workspace).toContainText('actual_nav2_run=false');
  await expect(workspace).toContainText('RUNTIME_POLICY_NOT_ENFORCED');
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
  expect(errors).toEqual([]);
});

test('MR failed CAS preserves draft, native unavailable stays explicit and no goal on reload',async({page})=>{
  const {workspace,writes,backend}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:200,y:200}});
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await workspace.getByRole('button',{name:'Nav2 계획 미리보기',exact:true}).click();
  await expect(workspace.getByRole('status')).toContainText('RESOURCE_WINDOW');
  await workspace.getByLabel('미션 이름',{exact:true}).fill('충돌 이후 보존');
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await expect(workspace.getByRole('status')).toContainText('DEFINITION_REVISION_CHANGED');
  await expect(workspace.getByLabel('미션 이름',{exact:true})).toHaveValue('충돌 이후 보존');
  expect(writes).toHaveLength(1); await page.reload();
  await expect(workspace.getByLabel('미션 이름',{exact:true})).toHaveValue('충돌 이후 보존');
  await expect(workspace.locator('ol li')).toHaveCount(1);
  await expect(workspace.locator('svg image')).toHaveCount(1);
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
});

test('MR edits made while save response is pending survive and remain dirty',async({page})=>{
  const {workspace,planId}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:180,y:180}});
  let release, submitted;
  await page.route('**/api/v1/mission-plans',async route=>{
    if(route.request().method()==='GET') return route.fallback();
    const {request_id,...definition}=route.request().postDataJSON(); submitted=definition;
    await new Promise(resolve=>{release=resolve;});
    await route.fulfill({status:201,json:{plan:{id:planId,revision:'d'.repeat(64),definition}}});
  });
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await expect.poll(()=>Boolean(release)).toBe(true);
  await workspace.getByLabel('미션 이름',{exact:true}).fill('저장 대기 중 새 이름');
  await workspace.getByLabel('도착 후 대기(초)',{exact:true}).fill('7.5');
  release();
  await expect(workspace.getByRole('status')).toContainText('저장 중 입력한 변경');
  await expect(workspace.getByLabel('미션 이름',{exact:true})).toHaveValue('저장 대기 중 새 이름');
  await expect(workspace.getByLabel('도착 후 대기(초)',{exact:true})).toHaveValue('7.5');
  await expect(workspace.getByRole('button',{name:'Nav2 계획 미리보기',exact:true})).toBeDisabled();
  expect(submitted.label).not.toBe('저장 대기 중 새 이름');
});

test('MR annotation heading is a per-visit override and stale annotations require explicit reconnect',async({page})=>{
  const points=[{id:'1'.repeat(24),type:'HOME',name:'출발',pose:{x:0,y:0,yaw:.4}},{id:'2'.repeat(24),type:'POI',name:'다음',pose:{x:0,y:2,yaw:0}}];
  const {workspace,writes,mapId,rev}=await fixture(page,{points});
  await workspace.getByRole('button',{name:'주석을 방문으로 추가',exact:true}).click();
  await workspace.getByLabel('지도 주석 방문',{exact:true}).selectOption(points[1].id);
  await workspace.getByRole('button',{name:'주석을 방문으로 추가',exact:true}).click();
  await workspace.locator('ol li button').first().click();
  await workspace.getByRole('button',{name:'다음 구간 방향으로 설정',exact:true}).click();
  await expect(workspace.getByLabel('방향(°)',{exact:true})).toHaveValue('90');
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  expect(writes[0].visits[0].heading_yaw).toBeCloseTo(Math.PI/2); expect(points[0].pose.yaw).toBe(.4);
  await page.route(`**/api/v1/saved-maps/${mapId}/annotations`,r=>r.fulfill({json:{map_id:mapId,map_revision:rev,annotation_revision:'e'.repeat(64),points,polygons:[]}}));
  await workspace.getByRole('button',{name:'미션 불러오기',exact:true}).click();
  await expect(workspace.getByRole('status')).toContainText('STALE_ANNOTATION_REVISION');
  await expect(workspace.locator('svg [data-visit]')).toHaveCount(0);
  await expect(workspace.getByRole('button',{name:'새 실행 만들기',exact:true})).toBeDisabled();
  page.once('dialog',dialog=>dialog.accept());
  await workspace.getByRole('button',{name:'현재 지도 버전에 초안 연결',exact:true}).click();
  await expect(workspace.locator('svg [data-visit]')).toHaveCount(2);
  await expect(workspace.getByRole('status')).toContainText('새 초안');
});

test('MR selected run receives observed trajectory through shared polling and distinguishes dispatch plan',async({page})=>{
  const {workspace,backend,planId,getPlan,mapId,rev,annRev}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:180,y:180}});
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  const id='9'.repeat(32), definition=getPlan().definition;
  const mission={id,label:'관측 실행',state:'ready',phase:'',map_id:mapId,map_revision:rev,annotation_revision:annRev,current_index:0,completed_count:0,hold_remaining:0,waypoints:definition.visits.map(v=>({...v,status:'pending'})),logs:[]};
  const run={id,definition,trajectory:[],preview:null,live_plan:{status:'unavailable',reason:'NAV2_RUNTIME_PATH_WITH_PROVENANCE_UNAVAILABLE'}};
  const result=()=>({run,mission});
  await page.route(`**/api/v1/mission-plans/${planId}/runs`,route=>{backend.state.missions=[mission]; return route.fulfill({status:201,json:result()});});
  await page.route(`**/api/v1/mission-runs/${id}`,route=>route.fulfill({json:result()}));
  await page.route('**/api/v1/mission-runs',route=>route.fulfill({json:{runs:[result()]}}));
  await workspace.getByRole('button',{name:'새 실행 만들기',exact:true}).click();
  await expect(workspace).toContainText('관측 실행');
  run.trajectory=[{x:0,y:0,yaw:0,epoch:'one'},{x:0,y:1,yaw:0,epoch:'one'}];
  run.preview={actual_nav2_run:true,scope:'dispatch_preflight',legs:[{poses:[{x:0,y:0,yaw:0},{x:0,y:1,yaw:0}]}]};
  await expect(workspace.locator('svg [data-evidence="observed_trajectory"]')).toHaveCount(1);
  await workspace.getByRole('button',{name:'실행',exact:true}).click();
  await expect(workspace.locator('svg [data-evidence="dispatch_preflight"]')).toHaveCount(1);
  await expect(workspace.locator('svg [data-evidence="native_preview"]')).toHaveCount(0);
  expect(backend.mutations(`/api/v1/missions/${id}/start`)).toHaveLength(0);
  Object.assign(mission,{state:'running',phase:'navigating',ownership_active:true});
  await expect(workspace.getByRole('button',{name:'일시정지',exact:true})).toBeEnabled();
  let releasePreview, signalPreview, pauses=0;
  const previewHeld=new Promise(resolve=>{releasePreview=resolve;});
  const previewStarted=new Promise(resolve=>{signalPreview=resolve;});
  await page.route(`**/api/v1/mission-plans/${planId}/plan-preview`,async route=>{signalPreview(); await previewHeld; await route.fulfill({status:503,json:{detail:'SYNTHETIC_PLANNER_UNAVAILABLE'}});});
  await page.route(`**/api/v1/mission-runs/${id}/pause`,route=>{pauses++; mission.state='paused'; mission.phase='navigating'; return route.fulfill({json:result()});});
  await workspace.getByRole('button',{name:'Nav2 계획 미리보기',exact:true}).click();
  await previewStarted;
  await expect(workspace.getByRole('button',{name:'일시정지',exact:true})).toBeEnabled();
  await workspace.getByRole('button',{name:'일시정지',exact:true}).click();
  await expect.poll(()=>pauses).toBe(1);
  releasePreview();
});

test('MR authored connector violations remain visible even when endpoints pass',async({page})=>{
  const {workspace,planId}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:180,y:180}});
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await page.route(`**/api/v1/mission-plans/${planId}/validate`,route=>route.fulfill({json:{status:'PASS',scope:'authoring',actual_nav2_run:false,validation:{violations:[],connector_validation:{valid:false,violations:[{kind:'OCCUPIED',violation_code:'OCCUPIED',severity:'warning',remedy:'실제 Nav2 계획을 검사하세요.',x:0,y:0}]}}}}));
  await workspace.getByRole('button',{name:'작성 검사',exact:true}).click();
  await expect(workspace).toContainText('작성 연결선 경고');
  await expect(workspace.getByRole('button',{name:/작성 연결선.*OCCUPIED/})).toBeVisible();
});

test('MR blank/out-of-range numeric fields preserve their old value and block save; keyboard moves the visit',async({page})=>{
  const {workspace,writes}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:180,y:180}});
  const x=workspace.getByLabel('x(m)',{exact:true}), initial=Number(await x.inputValue());
  await x.fill(''); await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await expect(workspace.getByRole('status')).toContainText('숫자 입력'); expect(writes).toHaveLength(0);
  await x.fill('10001'); await workspace.getByRole('button',{name:'미션 저장',exact:true}).click(); expect(writes).toHaveLength(0);
  await x.fill(String(initial)); await workspace.getByLabel('도착 후 대기(초)',{exact:true}).fill('301');
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click(); expect(writes).toHaveLength(0);
  await workspace.getByLabel('도착 후 대기(초)',{exact:true}).fill('0');
  await workspace.locator('svg').focus(); await workspace.locator('svg').press('ArrowRight');
  await expect(workspace.locator('svg')).toBeFocused();
  expect(Number(await x.inputValue())).toBeCloseTo(initial+.05);
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click(); await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0].visits[0].pose.x).toBeCloseTo(initial+.05);
});

test('MR disconnect marks state stale and hides operational pose while preserving focused draft',async({page})=>{
  const {workspace,mapId,rev,getPlan}=await fixture(page);
  await page.route('**/api/v1/mission-plans',route=>route.request().method()==='GET'?route.fulfill({json:{definitions:getPlan()?[getPlan()]:[],context:{navigation_map:{id:mapId,revision:rev},navigation_context_revision:'context-one',pose_source:{source:'/amcl_pose',readiness:'localized'},operational_pose:{x:0,y:0,yaw:0},blocking_reasons:[]}}}):route.fallback());
  await expect(workspace.locator('[data-evidence="operational_pose"]')).toHaveCount(1);
  const name=workspace.getByLabel('미션 이름',{exact:true}); await name.fill('연결 끊겨도 보존');
  await page.route('**/api/v1/mission-plans',route=>route.request().method()==='GET'?route.abort('failed'):route.fallback());
  await expect(workspace.locator('[data-connection-status]')).toHaveAttribute('data-connection-status','stale');
  await expect(workspace.locator('[data-evidence="operational_pose"]')).toHaveCount(0);
  await expect(name).toHaveValue('연결 끊겨도 보존'); await expect(name).toBeFocused();
});

test('MR history on another map preserves dirty editor and restores its original map',async({page})=>{
  const {workspace,backend,mapId}=await fixture(page);
  await workspace.getByLabel('지도 도구',{exact:true}).selectOption('add'); await workspace.locator('svg').click({position:{x:180,y:180}});
  await workspace.getByLabel('미션 이름',{exact:true}).fill('보존할 편집');
  const other='b'.repeat(24), revision='d'.repeat(64), ann='e'.repeat(64), id='9'.repeat(32), visit={visit_id:'8'.repeat(32),label:'이력 지점',kind:'STOP',target:'mission_local_pose',pose:{x:1,y:1,yaw:0},hold_seconds:0};
  const family={family_id:'a'.repeat(24),family_revision:'f'.repeat(64),pcd_map_id:'c'.repeat(24),pcd_revision:'1'.repeat(64),occupancy_map_id:other,occupancy_revision:revision};
  const definition={label:'다른 지도 이력',map_family:family,annotation_revision:ann,mode:'FLEXIBLE',route_ref:null,visits:[visit]};
  const mission={id,label:definition.label,state:'failed',outcome:'interrupted',phase:'interrupted',current_index:0,completed_count:0,waypoints:[{...visit,status:'pending',attempts:1}],logs:[]}, run={id,definition,definition_revision:'2'.repeat(64),trajectory:[]};
  const comparisonRun={...run,id:'8'.repeat(32),definition_revision:'3'.repeat(64),trajectory:[{x:1,y:1,epoch:'compare'},{x:1,y:2,epoch:'compare'}]};
  const comparisonMission={...mission,id:comparisonRun.id,outcome:'completed_with_skips',waypoints:[{...visit,status:'skipped',attempts:2}]};
  backend.state.missions=[mission,comparisonMission];
  await page.route(`**/api/v1/saved-maps/${other}/data`,r=>r.fulfill({json:{map_id:other,revision,kind:'occupancy2d',frame_id:'map',width:100,height:100,resolution:.1,origin:[0,0,0],data_b64:Buffer.alloc(10000).toString('base64')}}));
  await page.route(`**/api/v1/saved-maps/${other}/annotations`,r=>r.fulfill({json:{map_id:other,map_revision:revision,annotation_revision:ann,points:[],polygons:[]}}));
  await page.route(`**/api/v1/saved-maps/${other}/family`,r=>r.fulfill({json:{map_id:other,map_revision:revision,families:[{family_id:family.family_id,family_revision:family.family_revision,source:{pcd_map_id:family.pcd_map_id,pcd_revision:family.pcd_revision},occupancy:{map_id:other,map_revision:revision}}]}}));
  await page.route('**/api/v1/mission-runs',r=>r.fulfill({json:{runs:[{run,mission},{run:comparisonRun,mission:comparisonMission}]}}));
  await page.route(`**/api/v1/mission-runs/${id}`,r=>r.fulfill({json:{run,mission}}));
  await page.route(`**/api/v1/mission-runs/${comparisonRun.id}`,r=>r.fulfill({json:{run:comparisonRun,mission:comparisonMission}}));
  await workspace.getByRole('button',{name:'목록 새로고침',exact:true}).click(); await expect(workspace).toHaveAttribute('data-busy','false');
  await workspace.getByLabel('실행 이력',{exact:true}).selectOption(id);
  await expect(workspace.locator('svg')).toHaveAttribute('data-map-id',other);
  await expect(workspace.getByRole('button',{name:'현재 방문 재시도',exact:true})).toBeDisabled();
  await expect(workspace.getByRole('button',{name:'방문 건너뛰기',exact:true})).toBeDisabled();
  await workspace.getByLabel('비교 실행 이력',{exact:true}).selectOption(comparisonRun.id);
  await expect(workspace.locator('[data-comparison-summary]')).toContainText('completed_with_skips');
  await expect(workspace.locator('[data-comparison-summary]')).toContainText(comparisonRun.definition_revision);
  await expect(workspace.locator('[data-evidence="comparison_trajectory"]')).toHaveCount(1);
  await workspace.getByRole('button',{name:'편집',exact:true}).click();
  await expect(workspace.locator('svg')).toHaveAttribute('data-map-id',mapId);
  await expect(workspace.getByLabel('미션 이름',{exact:true})).toHaveValue('보존할 편집'); await expect(workspace.locator('ol li')).toHaveCount(1);
});

test('MR E1 geometry, planner evidence and light theme remain separate from the mapping page',async({page},testInfo)=>{
  const {workspace,backend,mapId,rev,annRev,family,planId}=await fixture(page);
  const routeId='6'.repeat(32), routeRevision='7'.repeat(64);
  const pins={family_id:family.family_id,family_revision:family.family_revision,pcd_map_id:family.source.pcd_map_id,pcd_revision:family.source.pcd_revision,occupancy_map_id:mapId,occupancy_revision:rev};
  const poses=[{x:0,y:0,yaw:0},{x:0,y:2,yaw:Math.PI/2}];
  const definition={label:'E1 fixture',map_family:pins,annotation_revision:annRev,mode:'FLEXIBLE',route_ref:{route_id:routeId,revision:routeRevision},visits:poses.map((pose,i)=>({visit_id:String(i+1).repeat(32),label:`정지 ${i+1}`,kind:'STOP',target:'mission_local_pose',pose,heading_yaw:null,hold_seconds:i,requires_operator_confirmation:false,after_arrival_confirmation:false,arrival_tolerance:null,speed:'DEFAULT',action:'none'}))};
  await page.route('**/api/v1/routes',r=>r.fulfill({json:{routes:[{route_id:routeId,label:'E1 fixture'}]}}));
  await page.route(`**/api/v1/routes/${routeId}`,r=>r.fulfill({json:{route:{revision:routeRevision,map_family:pins,poses}}}));
  await page.route(`**/api/v1/mission-route-drafts/${routeId}`,r=>r.fulfill({json:{draft:definition,notice:'원본 geometry 보존 · STOP 후보 검토 · 이동 없음'}}));
  await page.route(`**/api/v1/mission-plans/${planId}/compile`,r=>r.fulfill({json:{validation:{status:'PASS',scope:'authoring',actual_nav2_run:false},compiled:{start_sent:false}}}));
  await page.route(`**/api/v1/mission-plans/${planId}/plan-preview`,r=>r.fulfill({json:{status:'PASS',scope:'synthetic_ui_fixture',actual_nav2_run:true,legs:[{poses}],zone_support:{KEEP_OUT:{authoring:'checked',planning:'checked_on_result',runtime:'unavailable'}}}}));
  await workspace.getByRole('button',{name:'목록 새로고침',exact:true}).click(); await expect(workspace).toHaveAttribute('data-busy','false');
  page.once('dialog',d=>d.accept()); await workspace.getByRole('button',{name:'E1 → 미션 초안',exact:true}).click();
  await expect(workspace.locator('[data-evidence="authored_e1_geometry"]')).toHaveCount(1);
  await workspace.getByRole('button',{name:'미션 저장',exact:true}).click();
  await workspace.getByRole('button',{name:'FLEXIBLE compile',exact:true}).click(); await expect(workspace.getByRole('status')).toContainText('이동 명령 없음');
  await workspace.getByRole('button',{name:'Nav2 계획 미리보기',exact:true}).click();
  await expect(workspace.locator('[data-evidence="fixture_preview"]')).toHaveCount(1);
  await expect(workspace).toContainText('KEEP_OUT · 작성 checked · 계획 checked_on_result · 실행 unavailable');
  await page.locator('#themeToggle').click(); await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await testInfo.attach('mission-route-light-synthetic',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
  await page.locator('[data-nav="mapping"]').click(); await expect(workspace).toBeHidden(); await expect(page.locator('#mappingStartButton')).toBeVisible();
});

test('MR 200 percent CSS zoom layout keeps keyboard focus and STOP link accessible',async({page},testInfo)=>{
  await page.setViewportSize({width:1440,height:900}); const {workspace}=await fixture(page);
  await page.evaluate(()=>{document.documentElement.style.zoom='2';});
  await workspace.getByRole('link',{name:'공통 STOP으로 이동'}).focus();
  await expect(workspace.getByRole('link',{name:'공통 STOP으로 이동'})).toBeFocused();
  await expect(workspace.getByRole('link',{name:'공통 STOP으로 이동'})).toBeInViewport();
  await testInfo.attach('mission-route-200-percent-css-zoom-fixture',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
});

for(const size of [{width:1440,height:900},{width:1280,height:800},{width:1024,height:768},{width:768,height:1024},{width:390,height:844}]) test(`MR responsive ${size.width}x${size.height} · synthetic UI fixture`,async({page},testInfo)=>{
  await page.setViewportSize(size); const {workspace}=await fixture(page);
  if(size.width<=780) await workspace.getByRole('button',{name:'방문 목록',exact:true}).click();
  const box=await workspace.boundingBox(); expect(box.width).toBeLessThanOrEqual(size.width);
  await expect(workspace.locator('svg')).toBeVisible();
  await expect(workspace.getByRole('link',{name:'공통 STOP으로 이동'})).toBeVisible();
  if(size.width<=780){ await expect(workspace.locator('.mr-inspector')).toBeHidden(); await workspace.getByRole('button',{name:'방문 설정',exact:true}).click(); await expect(workspace.locator('.mr-inspector')).toBeVisible(); await expect(workspace.locator('aside').first()).toBeHidden(); }
  await testInfo.attach(`mission-route-${size.width}x${size.height}-synthetic`,{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
});
