import {expect, test} from '@playwright/test';
import {installDashboardBackend} from './dashboard_backend.mjs';

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
