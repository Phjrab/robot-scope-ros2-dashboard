import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('Missions repeat registered points in order and remove only one occurrence', async ({ page }) => {
  const backend = await installDashboardBackend(page, { includeSecondAnnotation: true });
  await page.goto('/#navigation');
  await expect(page.locator('#mapAnnotationList')).toContainText('E2E Home');
  await page.locator('[data-nav="missions"]').click();
  const panel = page.locator('#dashboardMissionHost');
  const choices = panel.locator('[data-mission-draft-id]');
  for (const i of [0, 1, 0, 1, 1]) await choices.nth(i).click();
  await expect(panel.locator('.cockpit-mission-order > li')).toHaveCount(5);
  await panel.locator('[data-mission-draft-move="remove"]').nth(2).click();
  await expect(panel.locator('.cockpit-mission-order > li')).toHaveCount(4);
  await panel.locator('[data-mission-action="create"]').click();
  await expect(panel.locator('.cockpit-mission-header strong')).toHaveText('MISSION READY');
  expect(backend.mutations('/api/v1/missions')[0].body.waypoints.map((w) => w.label)).toEqual(['E2E Home', 'E2E Inspect', 'E2E Inspect', 'E2E Inspect']);
  expect(backend.mutations(`/api/v1/missions/${backend.state.missions[0].id}/start`)).toHaveLength(0);
});

test('Route Planner keeps menu rows after save reload and second save, with destination above menus', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  await page.goto('/#route-planner');
  const panel = page.locator('#dashboardRoutePlannerHost');
  await panel.getByRole('button', { name: '+ 메뉴 항목 추가', exact: true }).click();
  await panel.getByRole('button', { name: '+ 메뉴 항목 추가', exact: true }).click();
  await panel.getByLabel('주문서 1 음식점 2', { exact: true }).selectOption('EDIYA');
  await panel.getByLabel('주문서 1 메뉴 2', { exact: true }).selectOption('CAFE_LATTE');
  await panel.getByLabel('주문서 1 수량 3', { exact: true }).fill('2');
  const destination = await panel.locator('.route-planner-sheet-destination').boundingBox();
  const menu = await panel.locator('.route-planner-menu-row').first().boundingBox();
  expect(menu.y).toBeGreaterThanOrEqual(destination.y + destination.height);
  await panel.locator('[data-route-action="save-order"]').click();
  await expect(panel.locator('.route-planner-menu-row')).toHaveCount(3);
  await page.reload();
  await expect(panel.locator('.route-planner-menu-row')).toHaveCount(3);
  await expect(panel.getByLabel('주문서 1 메뉴 2', { exact: true })).toHaveValue('CAFE_LATTE');
  await expect(panel.getByLabel('주문서 1 수량 3', { exact: true })).toHaveValue('2');
  await panel.locator('[data-route-action="save-order"]').click();
  const id = backend.state.routePlanner.order.id;
  await expect.poll(() => backend.mutations(`/api/v1/route-planner/orders/${id}`).length).toBe(1);
  expect(backend.mutations(`/api/v1/route-planner/orders/${id}`)[0].body.orders[0].lines).toHaveLength(3);
  await expect(panel.locator('.route-planner-menu-row')).toHaveCount(3);
});
