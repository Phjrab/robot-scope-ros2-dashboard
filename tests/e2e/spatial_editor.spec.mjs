import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('delivery posture is visit-specific and stays non-executable after save', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  await page.goto('/#navigation');
  await expect(page.locator('#mapAnnotationList')).toContainText('E2E Home');
  await page.locator('[data-nav="missions"]').click();
  const panel = page.locator('#dashboardMissionHost');
  await panel.locator('[data-mission-draft-id]').click();
  await panel.locator('[data-mission-draft-id]').click();
  await panel.getByLabel('2번 방문 도착 동작').selectOption('sit_then_rise');
  await panel.locator('[data-mission-draft-move="up"]').nth(1).click();
  await expect(panel.getByLabel('1번 방문 도착 동작')).toHaveValue('sit_then_rise');
  await panel.locator('[data-mission-action="create"]').click();
  await expect(panel.locator('.cockpit-mission-route')).toContainText('앉기 → 일어서기');
  await expect(panel.locator('[data-mission-action="start"]')).toBeDisabled();
  expect(backend.mutations('/api/v1/missions')[0].body.waypoints.map((p) => p.arrival_action)).toEqual(['sit_then_rise', 'none']);
  expect(backend.mutations(`/api/v1/missions/${backend.state.missions[0].id}/start`)).toHaveLength(0);
});

test('spatial editor draws, edits, saves a constrained draft and retains it after CAS rejection', async ({ page }, testInfo) => {
  const backend = await installDashboardBackend(page);
  const id = '0123456789abcdef01234567', rev = 'a'.repeat(64), routeId = 'f'.repeat(24);
  const family = { family_id: '1'.repeat(24), family_revision: '2'.repeat(64), source: { pcd_map_id: '3'.repeat(24), pcd_revision: '4'.repeat(64) }, occupancy: { map_id: id, map_revision: rev } };
  const writes = []; let stored;
  await page.route(`**/api/v1/saved-maps/${id}/family`, (r) => r.fulfill({ json: { map_id: id, map_revision: rev, families: [family] } }));
  await page.route(`**/api/v1/saved-maps/${id}/data`, (r) => r.fulfill({ json: { map_id: id, revision: rev, kind: 'occupancy2d', frame_id: 'map', width: 100, height: 100, resolution: 0.1, origin: [2, -3, Math.PI / 2], data_b64: Buffer.alloc(10000).toString('base64') } }));
  await page.route('**/api/v1/routes', async (r) => {
    if (r.request().method() === 'GET') return r.fulfill({ json: { routes: stored ? [stored] : [] } });
    const body = r.request().postDataJSON(); writes.push(body); stored = { ...body, route_id: routeId, revision: '5'.repeat(64) };
    return r.fulfill({ status: 201, json: { route: stored, validation: { valid: true, violations: [] } } });
  });
  await page.route(`**/api/v1/routes/${routeId}`, (r) => r.request().method() === 'PATCH' ? r.fulfill({ status: 409, json: { detail: 'route revision changed' } }) : r.fulfill({ json: { route: stored, validation: { valid: true, violations: [] } } }));
  await page.goto('/#route-planner');
  const editor = page.locator('.spatial-route-editor'); await editor.locator('summary').click();
  await editor.getByRole('button', { name: '지도 목록 새로고침', exact: true }).click();
  await editor.getByRole('button', { name: '지도 불러오기', exact: true }).click();
  const svg = editor.locator('svg'); await expect(svg.locator('image')).toHaveCount(1);
  await svg.scrollIntoViewIfNeeded();
  // Use the actual SVG transform so layout/letterboxing cannot mask mapping errors.
  const screen = await svg.evaluate((node) => { const p = node.createSVGPoint(); p.x = 30; p.y = 40; const a = p.matrixTransform(node.getScreenCTM()); p.x = 50; p.y = 40; const b = p.matrixTransform(node.getScreenCTM()); return { a: { x: a.x, y: a.y }, b: { x: b.x, y: b.y } }; });
  await page.mouse.move(screen.a.x, screen.a.y); await page.mouse.down(); await page.mouse.move(screen.b.x, screen.b.y, { steps: 5 }); await page.mouse.up();
  const pointCount = await svg.locator('[data-point-index]').count();
  expect(pointCount).toBeGreaterThan(2);
  await editor.getByLabel('편집 도구', { exact: true }).selectOption('DELETE');
  await svg.locator('[data-point-index="1"]').click();
  await expect(svg.locator('[data-point-index]')).toHaveCount(pointCount - 1);
  await editor.getByRole('button', { name: '되돌리기', exact: true }).click();
  await expect(svg.locator('[data-point-index]')).toHaveCount(pointCount);
  await editor.getByLabel('경로 제약', { exact: true }).selectOption('CORRIDOR');
  await editor.getByLabel('통로 전체 폭(m)').fill('1.2');
  await editor.getByLabel('마지막 방향(°)').fill('45');
  await editor.getByRole('button', { name: '검사 후 저장', exact: true }).click();
  await expect(editor.getByRole('status')).toContainText('검사 통과');
  expect(writes[0].policy).toEqual({ mode: 'CORRIDOR', corridor_width_m: 1.2, blocked_behavior: 'STOP' });
  expect(writes[0].poses[0].x).toBeCloseTo(-4); expect(writes[0].poses[0].y).toBeCloseTo(0);
  expect(writes[0].poses.at(-1).yaw).toBeCloseTo(Math.PI / 4);
  await editor.screenshot({ path: testInfo.outputPath('spatial-editor.png') });
  await editor.getByLabel('경로 이름', { exact: true }).fill('changed');
  await editor.getByRole('button', { name: '검사 후 저장', exact: true }).click();
  await expect(editor.getByRole('status')).toContainText('route revision changed');
  await expect(editor.getByLabel('경로 이름', { exact: true })).toHaveValue('changed');
  expect(backend.mutations('/api/v1/missions')).toHaveLength(0);
});
