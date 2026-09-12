import { test, expect } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('Route Planner saved-map order editor remains usable without private schematic assets', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  backend.state.routePlanner.schematic = { available: false, context: 'SAVED_OCCUPANCY', error: 'schematic local assets/storage unavailable', motion_authority: false, control_authority: false };
  await page.goto('/#route-planner');
  const host = page.locator('#dashboardRoutePlannerHost');
  await expect(host.getByRole('button', { name: '주문 저장', exact: true })).toBeEnabled();
  await expect(host.getByLabel('지도 컨텍스트', { exact: true })).toBeDisabled();
  await host.getByRole('button', { name: '주문 저장', exact: true }).click();
  await expect(host.getByRole('button', { name: '주문 잠금', exact: true })).toBeEnabled();
});
