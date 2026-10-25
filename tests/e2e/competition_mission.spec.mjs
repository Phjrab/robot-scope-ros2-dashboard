import {expect, test} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
import {installDashboardBackend} from './dashboard_backend.mjs';

test('stored RGB inspector is server-owned, retains diagnostics and cannot provide motion facts', async ({page}, info) => {
  await installDashboardBackend(page);
  await page.route(/\/__fixture\//, route => route.continue());
  await page.goto('/?rgb_review=1#missions');
  const review = page.locator('[data-rgb-review]');
  await expect(review).toHaveAttribute('data-state', 'COMPLETE');
  await expect(review).toContainText('SYNTHETIC_RGB_REVIEW');
  await expect(review).toContainText('detection-only');
  await expect(review).toContainText('raw GREEN');
  await expect(review).toContainText('출발 허가 없음');
  await expect(review).toContainText('false GREEN 3개');
  await expect.poll(() => review.locator('img').evaluateAll(images => images.every(img => img.complete && img.naturalWidth > 0))).toBe(true);
  const before = await (await page.request.get('/__fixture/rgb-review')).json();
  expect(before.departure_authorized).toBe(false);
  expect(Object.values(before.observation.independent_facts).every(v => v === null)).toBe(true);
  expect((await page.request.post('/__fixture/rgb-review', {data:{input:'/etc/passwd'}})).status()).toBe(405);
  expect((await page.request.get('/__fixture/rgb-review?input=/etc/passwd')).status()).toBe(400);
  expect((await page.request.get('/__fixture/rgb-review', {headers:{Origin:'https://untrusted.invalid'}})).status()).toBe(403);
  await page.reload();
  await expect(review).toHaveAttribute('data-state', 'COMPLETE');
  const after = await (await page.request.get('/__fixture/rgb-review')).json();
  expect(after).toEqual(before);
  // This fixture is generated synthetic RGB only; private runs use separate paths.
  const path = info.outputPath('synthetic-rgb-review.png');
  await review.screenshot({path});
  await info.attach('synthetic RGB review', {path, contentType:'image/png'});
});

async function connect(page) {
  const backend = await installDashboardBackend(page);
  // All mission authoring/execution requests reach the real local Python API.
  // Other dashboard providers remain explicit UI fixtures.
  await page.route(/\/api\/v1\/(mission-(plans|runs|competition)|saved-maps|routes)(\/|$)/, route => route.continue());
  page.on('dialog', d => d.accept());
  await page.goto('/#missions');
  const workspace = page.locator('.mr-workspace');
  await expect(workspace).toHaveAttribute('data-busy','false');
  return {workspace,backend};
}
async function draft(page) {
  const result = await connect(page), w = result.workspace;
  await w.getByRole('button',{name:'지도 불러오기 / 새 미션',exact:true}).click();
  await w.getByRole('button',{name:'대회 DRAFT 만들기',exact:true}).click();
  await expect(w.locator('ol li')).toHaveCount(6);
  return result;
}

test('mission workspace saves explicit waypoint coordinates through the real API and reloads the definition', async ({page}) => {
  const {workspace:w,backend} = await connect(page);
  await w.getByRole('button',{name:'지도 불러오기 / 새 미션',exact:true}).click();
  await w.getByLabel('미션 이름',{exact:true}).fill('C1 explicit waypoint');
  await w.getByLabel('지도 도구',{exact:true}).selectOption('add');
  await w.locator('svg').click();
  await expect(w.locator('ol li')).toHaveCount(1);
  await w.getByLabel('방문 이름',{exact:true}).fill('C1 waypoint');
  await w.getByLabel('x(m)',{exact:true}).fill('1.5');
  await w.getByLabel('y(m)',{exact:true}).fill('2.25');
  await w.getByLabel('방향(°)',{exact:true}).fill('90');
  const saved = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/mission-plans'
    && response.request().method() === 'POST');
  await w.getByRole('button',{name:'미션 저장',exact:true}).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  const {plan} = await response.json();
  expect(plan.definition.label).toBe('C1 explicit waypoint');
  const visit = plan.definition.visits[0];
  expect(visit.label).toBe('C1 waypoint');
  expect(visit.target).toBe('mission_local_pose');
  expect(visit.pose).toEqual({x:1.5,y:2.25,yaw:Math.PI/2});
  const persisted = await page.request.get(`/api/v1/mission-plans/${plan.id}`);
  expect(persisted.ok()).toBe(true);
  expect((await persisted.json()).plan).toEqual(plan);
  await expect(w.getByRole('status')).toContainText('저장됨');
  // Remove the browser draft: reload must recover the definition from the API.
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(w.getByLabel('미션 이름',{exact:true})).toHaveValue('C1 explicit waypoint');
  await expect(w.locator('ol li')).toHaveCount(1);
  await w.locator('[data-visit-label]').click();
  await expect(w.getByLabel('x(m)',{exact:true})).toHaveValue('1.5');
  await expect(w.getByLabel('y(m)',{exact:true})).toHaveValue('2.25');
  expect((await (await page.request.get('/api/v1/mission-runs')).json()).runs).toEqual([]);
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
});

test('competition real API saves DRAFT, field edits, minima and per-step blockers', async ({page}) => {
  const errors=[]; page.on('pageerror', e => errors.push(e.message));
  const {workspace:w,backend} = await draft(page);
  await expect(w.locator('[data-visit]')).toHaveCount(0);
  await w.getByText('설계 모델 · 실측 지도와 별도 보기',{exact:true}).click();
  await w.getByRole('button',{name:'설계 GLB 불러오기',exact:true}).click();
  await expect(w.locator('[data-arena-glb]')).toBeVisible();
  await expect(w).toContainText('GLB Y-up · 정합 미확인');
  await w.locator('[data-visit-label]').nth(1).click();
  const dwell = w.getByLabel('유효 정차 최소(초)',{exact:true});
  await dwell.fill('1');
  await w.getByRole('button',{name:'미션 저장',exact:true}).click();
  await expect(w.getByRole('status')).toContainText('허용 범위');
  await dwell.fill('2.5');
  await w.getByLabel('signal ID',{exact:true}).fill('review-signal-1');
  await w.getByLabel('출구 x(m)',{exact:true}).fill('3');
  await w.getByLabel('출구 y(m)',{exact:true}).fill('4');
  await w.getByLabel('지도 도구',{exact:true}).selectOption('place');
  await w.locator('svg').click();
  await expect(w.locator('[data-visit]')).toHaveCount(1);
  await w.getByRole('button',{name:'미션 저장',exact:true}).click();
  await expect(w.getByRole('status')).toContainText('저장됨');
  const plans = await (await page.request.get('/api/v1/mission-plans')).json();
  const d = plans.definitions.at(-1).definition;
  expect(d.visits[1].mission_action.dwell_seconds).toBe(2.5);
  expect(d.visits[1].mission_action.signal_id).toBe('review-signal-1');
  expect(d.visits[1].mission_action.exit_pose).toEqual({x:3,y:4,yaw:0});
  expect(d.visits[1].target).toBe('mission_local_pose');
  await expect(w.getByRole('button',{name:'새 실행 만들기',exact:true})).toBeDisabled();
  await expect(w).toContainText('FEET_EVIDENCE_UNCONNECTED');
  await expect(w).toContainText('정합 미확인');
  await w.getByRole('button',{name:'작성 검사',exact:true}).click();
  await expect(w).toContainText('COMPETITION_ADAPTER_UNCONNECTED');
  await page.reload(); await expect(w.locator('ol li')).toHaveCount(6);
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
  expect(errors).toEqual([]);
});

test('fixture continues through page close and reconnect; GREEN progresses and timer is server-owned', async ({page,context}) => {
  const {workspace:w}=await draft(page);
  await w.getByRole('button',{name:'미션 저장',exact:true}).click();
  await w.getByRole('button',{name:'fixture 시도 만들기',exact:true}).click();
  await w.getByRole('button',{name:'fixture 시작',exact:true}).click();
  await expect(w.locator('[data-competition-summary]')).toContainText('FIXTURE');
  await expect(w.getByRole('button',{name:'방문 건너뛰기',exact:true})).toBeDisabled();
  const first=(await (await page.request.get('/api/v1/mission-runs')).json()).runs[0];
  const id=first.run.id;
  await page.close();
  const second=await context.newPage(); await connect(second);
  await second.locator('.mr-workspace').getByLabel('실행 이력',{exact:true}).selectOption(id);
  await expect.poll(async()=> (await (await second.request.get(`/api/v1/mission-runs/${id}`)).json()).mission.completed_count).toBeGreaterThanOrEqual(2);
  const current=await (await second.request.get(`/api/v1/mission-runs/${id}`)).json();
  expect(current.mission.elapsed_s).toBeGreaterThan(first.mission.elapsed_s);
  expect(current.mission.timer_owner).toBe('onboard_backend');
  expect(current.run.trajectory).toEqual([]);
  await expect(second.locator('[data-evidence="native_preview"]')).toHaveCount(0);
  await expect.poll(async()=> (await (await second.request.get(`/api/v1/mission-runs/${id}`)).json()).mission.state, {timeout:22000}).toBe('completed');
});

for (const viewport of [{width:1440,height:900},{width:390,height:844}]) test(`competition fixture ${viewport.width} light/dark and STOP`, async ({page},info) => {
  await page.setViewportSize(viewport);
  const {workspace:w}=await draft(page);
  await expect(w.getByRole('link',{name:'공통 STOP으로 이동'})).toBeVisible();
  await w.getByText('설계 모델 · 실측 지도와 별도 보기',{exact:true}).click();
  await w.getByRole('button',{name:'설계 GLB 불러오기',exact:true}).click();
  await expect(w.locator('[data-arena-glb]')).toBeVisible();
  await w.evaluate(element => { const label=document.createElement('p'); label.textContent='명시적 합성 UI fixture · 실장비 연결·주행 증거 아님'; label.style.gridColumn='1 / -1'; element.prepend(label); });
  expect((await w.boundingBox()).width).toBeLessThanOrEqual(viewport.width);
  const dark=info.outputPath(`competition-${viewport.width}-dark-explicit-fixture.png`); await page.screenshot({path:dark,fullPage:true}); await info.attach('dark fixture',{path:dark,contentType:'image/png'});
  await page.locator('#themeToggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  if(viewport.width < 780) await w.getByRole('button',{name:'방문 설정',exact:true}).click();
  await expect(w.getByLabel('회피 profile',{exact:true})).toBeVisible();
  const light=info.outputPath(`competition-${viewport.width}-light-explicit-fixture.png`); await page.screenshot({path:light,fullPage:true}); await info.attach('light fixture',{path:light,contentType:'image/png'});
});

async function offlineSignal(page) {
  await installDashboardBackend(page);
  await page.route(/\/__fixture\//, route => route.continue());
  await page.route(/\/api\/v1\/(mission-(plans|runs|competition)|saved-maps|routes)(\/|$)/, route => route.continue());
  await page.goto('/?offline_signal=1#missions');
  await expect(page.locator('[data-offline-signal]')).toContainText('OFFLINE SYNTHETIC');
  return page.locator('.mr-workspace');
}

test('actual C2 runtime and C4 RGB signal cross after independent dwell; reconnect does not create goal', async ({page}, info) => {
  const w = await offlineSignal(page);
  await w.getByLabel('오프라인 신호 시나리오',{exact:true}).selectOption('normal');
  await w.getByRole('button',{name:'오프라인 신호 시작',exact:true}).click();
  await expect(page.locator('[data-offline-signal]')).toHaveAttribute('data-phase','HOLD_SIGNAL');
  const before = await (await page.request.get('/__fixture/native-signal')).json();
  await page.reload();
  await expect(page.locator('[data-offline-signal]')).toHaveAttribute('data-phase','SUCCEEDED');
  const final = await (await page.request.get('/__fixture/native-signal')).json();
  expect(final.run_id).toBe(before.run_id);
  expect(final.goal_count).toBe(2);
  expect(final.departed).toBe(true);
  expect(final.trace.map(x=>x.phase)).toEqual(expect.arrayContaining(['APPROACH','HOLD_ACK','HOLD_SIGNAL','EXIT_PENDING','DEPARTING','SUCCEEDED']));
  expect(final.physical_motion).toBe(false);
  await expect(page.locator('[data-offline-signal]')).toContainText('독립 앞발');
  const path = info.outputPath('native-signal-software-completion.png');
  await page.screenshot({path,fullPage:true}); await info.attach('C2 C4 software completion',{path,contentType:'image/png'});
  const tracePath = info.outputPath('native-signal-software-trace.json');
  await writeFile(tracePath, JSON.stringify(final,null,2));
  await info.attach('actual software trace',{path:tracePath,contentType:'application/json'});
});

for(const scenario of ['red','unknown']) test(`offline ${scenario} holds before departure`, async ({page}) => {
  const w = await offlineSignal(page);
  await w.getByLabel('오프라인 신호 시나리오',{exact:true}).selectOption(scenario);
  await w.getByRole('button',{name:'오프라인 신호 시작',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/__fixture/native-signal')).json()).dwell_elapsed_s).toBeGreaterThan(2);
  const held = await (await page.request.get('/__fixture/native-signal')).json();
  expect(held.phase).toBe('HOLD_SIGNAL'); expect(held.goal_count).toBe(1); expect(held.departed).toBe(false);
  await w.getByRole('button',{name:'오프라인 STOP',exact:true}).click();
  await expect(page.locator('[data-offline-signal]')).toHaveAttribute('data-phase','INTERRUPTED');
});

test('offline STOP while planner awaits never dispatches the exit goal', async ({page}) => {
  const w = await offlineSignal(page);
  await w.getByLabel('오프라인 신호 시나리오',{exact:true}).selectOption('delayed_plan');
  await w.getByRole('button',{name:'오프라인 신호 시작',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/__fixture/native-signal')).json()).planning_delayed).toBe(true);
  await w.getByRole('button',{name:'오프라인 STOP',exact:true}).click();
  await expect(page.locator('[data-offline-signal]')).toHaveAttribute('data-phase','INTERRUPTED');
  const final = await (await page.request.get('/__fixture/native-signal')).json();
  expect(final.goal_count).toBe(1); expect(final.departed).toBe(false);
});
