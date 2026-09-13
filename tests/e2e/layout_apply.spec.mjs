import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

async function edit(page) {
  const toggle = page.locator('.cockpit-safety-toggle');
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
  await page.locator('[data-cockpit-layout-action="edit"]').click();
}

test('Cockpit Apply persists panels on reload and a new window without saving a named preset', async ({ page, context }) => {
  const backend = await installDashboardBackend(page);
  await page.goto('/?workspace=cockpit#cockpit');
  await expect(page.locator('.cockpit-layout-profile')).toHaveText('PROFILE · go2');
  await edit(page);
  await page.locator('.cockpit-launcher-item[data-panel-type="placeholder.map"]').click();
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  await expect(page.locator('.cockpit-layout-save-status')).toContainText('저장 완료');
  const panel = page.locator('[data-panel-id="placeholder-map"]');
  const before = await panel.boundingBox();
  await page.reload();
  await expect(panel).toBeVisible();
  const after = await panel.boundingBox();
  for (const axis of ['x', 'y', 'width', 'height']) expect(Math.abs(before[axis] - after[axis])).toBeLessThan(2);
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  const reopened = await context.newPage();
  await installDashboardBackend(reopened);
  await reopened.goto('/?workspace=cockpit#cockpit');
  await expect(reopened.locator('[data-panel-id="placeholder-map"]')).toBeVisible();
  await reopened.close();
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
  expect(backend.mutations('/api/v1/navigation/start')).toHaveLength(0);
});

test('Cockpit Apply storage failure remains editable and reports failure', async ({ page }) => {
  await installDashboardBackend(page);
  await page.goto('/?workspace=cockpit#cockpit');
  await expect(page.locator('.cockpit-layout-profile')).toHaveText('PROFILE · go2');
  await edit(page);
  await page.evaluate(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (key.startsWith('robot-scope.cockpit.applied-layout.')) throw new Error('quota blocked');
      return original.call(this, key, value);
    };
  });
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  await expect(page.locator('.cockpit-layout-save-status')).toContainText('저장 실패');
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'layout-edit');
});
