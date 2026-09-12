import { test, expect } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { installDashboardBackend } from './dashboard_backend.mjs';

const outputs = process.env.SCHEMATIC_OUTPUT_DIR || resolve('test-results/schematic-captures');
test('competition map real server: order to manual completion, FIELD fence, responsive and zero motion', async ({ page, context, request }) => {
  const writes = []; const external = []; const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await context.route('**/*', async (route) => {
    const req = route.request(); const url = new URL(req.url());
    if (url.hostname !== '127.0.0.1') { external.push(req.url()); return route.abort(); }
    if (req.method() !== 'GET') writes.push({ path: url.pathname, data: req.postDataJSON() });
    return route.continue();
  });
  await page.goto('/');
  const host = page.locator('#dashboardRoutePlannerHost');
  await expect(host.getByLabel('지도 컨텍스트', { exact: true })).toBeEnabled();
  await host.getByLabel('지도 컨텍스트', { exact: true }).selectOption('DEMO');
  await expect(host.getByText('DEMO — 예시 배치', { exact: false })).toBeVisible();
  await expect(host.getByLabel('Route operation mode')).toBeHidden();
  await expect(host.getByRole('button', { name: 'NAV2 PREVIEW', exact: true })).toBeHidden();
  await expect(host.getByRole('button', { name: 'MISSION DRAFT EXPORT', exact: true })).toBeHidden();
  await host.getByRole('button', { name: '주문 저장', exact: true }).click();
  await expect(host.getByRole('button', { name: '주문 잠금', exact: true })).toBeEnabled();
  await host.getByRole('button', { name: '주문 잠금', exact: true }).click();
  await expect(host.getByRole('button', { name: '주문 잠금 해제', exact: true })).toBeVisible();
  await host.getByLabel('도식 출발 장소').selectOption('COEX');
  await host.getByRole('button', { name: '도식 추천 경로 계산', exact: true }).click();
  await host.getByRole('button', { name: '이 도식 경로 선택' }).first().click();
  await expect(host.getByText('선택됨 ·', { exact: false })).toBeVisible();
  await mkdir(outputs, { recursive: true });
  for (const [width, height] of [[1366, 768], [1920, 1080]]) {
    await page.setViewportSize({ width, height });
    await host.locator('.competition-map-view').scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(outputs, `schematic-${width}x${height}.png`) });
    const svg = host.getByRole('img', { name: '도식 수동 안내 지도' });
    await svg.click({ position: { x: 50, y: 50 } });
    await expect(host.getByText('도식 클릭 x_px=', { exact: false })).toBeVisible();
    const measure = await svg.evaluate((svg) => { const matrix=svg.getScreenCTM(); const p=svg.createSVGPoint();p.x=150;p.y=146;const screen=p.matrixTransform(matrix);const back=screen.matrixTransform(matrix.inverse());return {x:back.x,y:back.y,background:svg.querySelector('image').getAttribute('x')}; });
    expect(measure.x).toBeCloseTo(150); expect(measure.y).toBeCloseTo(146); expect(measure.background).toBe('-30');
    await host.getByRole('button', { name: '확대', exact: true }).click();
    await expect(svg).not.toHaveAttribute('viewBox', '0 0 1135 812');
    await host.getByRole('button', { name: '맞춤 / 초기화' }).click();
    await expect(svg).toHaveAttribute('viewBox', '0 0 1135 812');
  }
  await host.getByLabel('참고 지도 보기').selectOption('arena_p11_original.png');
  await expect(host.locator('.competition-map-view svg')).toBeHidden();
  await expect.poll(() => host.locator('.competition-map-view img').evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
  await host.getByLabel('참고 지도 보기').selectOption('arena_p13_top_original.png');
  await expect.poll(() => host.locator('.competition-map-view img').evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
  await host.getByLabel('참고 지도 보기').selectOption('arena_schematic.svg');
  await host.getByRole('button', { name: '수동 안내 시작 (로봇 동작 없음)', exact: true }).click();
  await expect(host.getByText('수동 기록 WAIT_OPERATOR', { exact: false })).toBeVisible();
  for (let i=0; i<100; i++) {
    const done = host.getByText('수동 기록 COMPLETE', { exact: false });
    if (await done.count()) break;
    const confirm = host.getByRole('button', { name: /(?:픽업|배달) 확인$/ });
    if (await confirm.count()) await confirm.first().click();
    else await host.getByRole('button', { name: '현재 구간 완료 기록 (통과 허가 아님)' }).click();
    await expect.poll(() => page.evaluate(() => window.schematicTest.client.diagnostics().busy)).toBe(false);
  }
  await expect(host.getByText('수동 기록 COMPLETE', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => window.schematicTest.client.snapshot().schematic.signal_state)).toBe('UNKNOWN');
  await page.getByRole('button', { name: '좁은 Cockpit 공통 패널', exact: true }).click();
  const cockpit = page.locator('#cockpitTestHost');
  await expect(cockpit.getByText('수동 기록 COMPLETE', { exact: false })).toBeVisible();
  await cockpit.locator('.competition-map-view').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(outputs, 'schematic-cockpit-narrow.png') });
  for (let i=0; i<5; i++) { await page.getByRole('button', { name: '패널 닫기', exact: true }).click(); await expect.poll(() => page.evaluate(() => window.schematicTest.client.diagnostics().polling)).toBe(false); await page.getByRole('button', { name: '좁은 Cockpit 공통 패널', exact: true }).click(); }
  expect(await page.evaluate(() => window.schematicTest.client.diagnostics().subscribers)).toBe(1);
  await cockpit.getByLabel('지도 컨텍스트', { exact: true }).selectOption('FIELD');
  await expect(cockpit.getByText('FIELD — 미승인 / 시작 차단', { exact: false })).toBeVisible();
  await cockpit.getByText('현장 배치·연결 설정 / 별도 승인', { exact: true }).click();
  await expect(cockpit.getByLabel('COEX 정지 x_px', { exact: true })).toHaveValue('');
  await expect(cockpit.getByRole('button', { name: '현재 FIELD revision 승인' })).toBeDisabled();
  await page.screenshot({ path: resolve(outputs, 'schematic-field-unconfigured.png') });
  expect(writes.every((w) => w.path === '/api/v1/route-planner/schematic')).toBe(true);
  expect(JSON.stringify(writes)).not.toMatch(/AUTO_NAV2|"motion_authority":true/);
  expect(external).toEqual([]); expect(errors).toEqual([]);
  expect((await (await request.get('/test/traps')).json()).calls).toEqual([]);
});

test('competition map readonly references survive API unavailable and high DPR', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 2 });
  await ctx.route('**/api/**', (route) => route.abort());
  const page = await ctx.newPage(); await page.goto('http://127.0.0.1:4189/');
  const host = page.locator('#dashboardRoutePlannerHost');
  await host.getByText('읽기 전용 참고 지도 (서버 연결 없이 보기)', { exact: true }).click();
  await expect(host.getByRole('img', { name: '도식 수동 안내 지도' })).toBeVisible();
  await host.getByLabel('참고 지도 보기').selectOption('arena_p11_original.png');
  await expect.poll(() => host.locator('.competition-map-view img').evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
  await page.screenshot({ path: resolve(outputs, 'schematic-offline-dpr2.png') });
  await expect(host.getByLabel('지도 컨텍스트', { exact: true })).toBeDisabled();
  await ctx.close();
});

test('competition map FIELD setup uses explicit form inputs and separately approves revision', async ({ page }) => {
  // Deliberate test fixture, never a claim about field coordinates or approval.
  const fixture = JSON.parse(await readFile('robot_dashboard/static/assets/competition/gangnam2026/schematic_template.json', 'utf8'));
  await page.goto('/'); const host = page.locator('#dashboardRoutePlannerHost');
  await host.getByLabel('지도 컨텍스트', { exact: true }).selectOption('FIELD');
  await host.getByText('현장 배치·연결 설정 / 별도 승인', { exact: true }).click();
  for (const [c,z] of Object.entries(fixture.demo_corner_zone_binding)) await host.getByLabel(`${c} 공식 구역`, { exact: true }).selectOption(z);
  for (const v of fixture.venues) {
    const n = fixture.nodes.find((n) => n.id === v.id);
    await host.getByLabel(`${v.id} 코너`, { exact: true }).selectOption(v.demo_corner);
    await host.getByLabel(`${v.id} 접근 노드`, { exact: true }).selectOption(v.demo_corner);
    await host.getByLabel(`${v.id} 정지 x_px`, { exact: true }).fill(String(n.x_px));
    await host.getByLabel(`${v.id} 정지 y_px`, { exact: true }).fill(String(n.y_px));
    await host.getByLabel(`${v.id} yaw_rad`, { exact: true }).fill('0');
  }
  await host.getByLabel('조종 경기 음식별 사전준비 2개 규칙 확인', { exact: true }).check();
  await host.getByLabel('주최 측 정적 참고 지도 사용 허용 확인', { exact: true }).check();
  await host.getByRole('button', { name: '배치·연결 저장 (승인 해제)' }).click();
  await expect(host.getByRole('button', { name: '현재 FIELD revision 승인' })).toBeEnabled();
  await host.getByLabel('현장 배치 확인자 이름', { exact: true }).fill('TEST FIXTURE ONLY');
  await host.getByRole('button', { name: '현재 FIELD revision 승인' }).click();
  await expect(host.getByText('FIELD — 승인됨', { exact: false })).toBeVisible();
  await host.getByLabel('COEX yaw_rad', { exact: true }).fill('0.1');
  await host.getByRole('button', { name: '배치·연결 저장 (승인 해제)' }).click();
  await expect(host.getByText('FIELD — 미승인 / 시작 차단', { exact: false })).toBeVisible();
});

test('competition map appears in the actual dashboard and Cockpit shells without ROS overlays', async ({ page }) => {
  // Other dashboard telemetry is explicitly a fixture; planner calls reach Python.
  await installDashboardBackend(page, { online: false });
  await page.route('**/api/v1/route-planner**', (route) => route.continue());
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/dashboard#route-planner');
  await expect(page.locator('#pageTitle')).toHaveText('Route Planner');
  const dashboard = page.locator('#dashboardRoutePlannerHost');
  await dashboard.getByLabel('지도 컨텍스트', { exact: true }).selectOption('DEMO');
  await expect(dashboard.getByText('DEMO — 예시 배치', { exact: false })).toBeVisible();
  await dashboard.locator('.competition-map-view').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(outputs, 'schematic-dashboard-shell.png') });
  // The sidebar intentionally opens a separate Cockpit window. Load its shell
  // directly in this test page so lifecycle assertions target the correct owner.
  await page.goto('/dashboard?surface=cockpit#cockpit');
  const safety = page.locator('.cockpit-safety-toggle');
  if (await safety.getAttribute('aria-expanded') === 'false') await safety.click();
  await page.locator('[data-cockpit-layout-action="edit"]').click();
  await page.locator('.cockpit-launcher-item[data-panel-type="route-planner.main"]').click();
  await page.locator('#cockpitSensorLauncher .cockpit-launcher-toggle').click();
  const cockpit = page.locator('[data-panel-id="route-planner"]');
  await expect(cockpit.getByText('DEMO — 예시 배치', { exact: false })).toBeVisible();
  await expect(cockpit.getByLabel('Route operation mode')).toBeHidden();
  await cockpit.locator('.competition-map-view').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(outputs, 'schematic-cockpit-shell.png') });
  expect(await page.evaluate(() => window.RobotScopeRoutePlanner.diagnostics().client.polling)).toBe(false);
});
