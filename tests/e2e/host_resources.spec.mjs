import { test, expect } from '@playwright/test';
import { installMissionFixture } from './ui_redesign_fixture.mjs';

// UI fixture only. These values do not constitute a deployed Jetson measurement.
const snapshot = { schema_version: 1, scope: 'dashboard_host',
  sampled_at: '2026-10-13T12:00:00Z',
  host: { model: 'NVIDIA Jetson Orin NX', is_jetson: true },
  cpu: { percent: 44.5 }, gpu: { percent: 18 }, ram: { percent: 10.8,
    used_bytes: 1.7 * 1073741824, total_bytes: 15.3 * 1073741824 },
  swap: { used_bytes: 0, total_bytes: 7.6 * 1073741824 },
  disk: { percent: 16.2, free_bytes: 369 * 1073741824 },
  temperature: { max_celsius: 65.2 }, unavailable: [],
  history: [{ cpu_percent: 40, gpu_percent: 0, ram_percent: 10 },
    { cpu_percent: 44.5, gpu_percent: 18, ram_percent: 10.8 }] };

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`resource panel ${viewport.width}px, stale state and visibility`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await installMissionFixture(page);
    let requests = 0, failed = false;
    await page.route('**/api/v1/system/resources', (route) => {
      requests++;
      return route.fulfill({ status: failed ? 503 : 200, contentType: 'application/json',
        body: JSON.stringify(snapshot) });
    });
    await page.goto('/#settings');
    const panel = page.locator('#hostResourcePanel');
    await expect(panel.locator('[data-resource="cpu"]')).toHaveText('44.5%');
    await expect(panel.locator('[data-resource="gpu"]')).toHaveText('18.0%');
    await expect(panel.locator('[data-resource="host"]')).toContainText('대시보드 실행 호스트');
    expect(await panel.evaluate((p) => [...p.querySelectorAll('.host-resource-grid > div')].every(
      (card) => card.scrollWidth <= card.clientWidth + 1))).toBe(true);
    await panel.screenshot({ path: `/private/tmp/isaac-vslam-evidence-20261013/resource-panel-${viewport.width}.png` });
    failed = true;
    await expect(panel).toHaveAttribute('data-state', 'stale', { timeout: 7000 });
    await expect(panel.locator('[data-resource="cpu"]')).toHaveText('44.5%');
    await expect(panel.locator('[data-resource="notes"]')).toContainText('이전 측정치');
    await page.evaluate(() => { location.hash = '#overview'; });
    const before = requests;
    await page.waitForTimeout(2500);
    expect(requests).toBe(before);
  });
}
