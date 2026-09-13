import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('Cockpit remembers manual camera after page reload', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  await page.goto('/?workspace=cockpit#cockpit');
  await expect(page.locator('#cockpitSceneFollow')).toHaveText('FOLLOW');
  await page.locator('#cockpitSceneFollow').click();
  const canvas = page.locator('#cockpitSceneCanvas'); const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.55, { steps: 5 }); await page.mouse.up();
  await page.mouse.wheel(0, -180);
  const camera = await page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera);
  await page.reload();
  await expect(page.locator('#cockpitSceneFollow')).toHaveText('WORLD');
  await expect.poll(() => page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera)).toEqual(camera);
  await page.locator('#cockpitSceneReset').click();
  await expect(page.locator('#cockpitSceneFollow')).toHaveText('FOLLOW');
  expect(backend.mutations('/api/v1/navigation/start')).toHaveLength(0);
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
});
