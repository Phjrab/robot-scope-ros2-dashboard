import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('food clock runs independently, restores and never sends robot commands', async ({ page }, testInfo) => {
  const backend = await installDashboardBackend(page);
  await page.clock.install({ time: new Date('2026-09-12T12:00:00Z') });
  await page.goto('/#route-planner');
  const panel = page.getByRole('region', { name: '음식 생성 예상 현황' });
  await expect(panel).toContainText('생성 예상 0/31개');
  await panel.getByRole('button', { name: '조리 시작', exact: true }).click();
  await page.clock.fastForward(20000);
  await expect(panel).toContainText('생성 예상 3/31개');
  await panel.getByRole('button', { name: '1개 수령 확인', exact: true }).first().click();
  await expect(panel.locator('.food-production-row').first()).toContainText('수령 확인 1개');
  await page.reload();
  await expect(panel.locator('.food-production-row').first()).toContainText('수령 확인 1개');
  await expect(panel.getByRole('button', { name: '조리 시작', exact: true })).toBeDisabled();
  await panel.getByRole('button', { name: '수령 1개 취소', exact: true }).first().click();
  await page.clock.fastForward(240000);
  await expect(panel).toContainText('생성 예상 31/31개');
  await panel.screenshot({ path: testInfo.outputPath('food-production.png') });
  await expect(panel.getByRole('button', { name: '타이머 초기화 확인' })).toBeDisabled();
  await panel.getByLabel('타이머 초기화 동의').check();
  await panel.getByRole('button', { name: '타이머 초기화 확인' }).click();
  await expect(panel).toContainText('생성 예상 0/31개');
  for (const path of ['/api/v1/missions', '/api/v1/navigation/goal', '/api/v1/control/lease', '/api/v1/route-planner/orders']) expect(backend.mutations(path)).toHaveLength(0);
});
