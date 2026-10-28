import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('state polling accepts responses slower than its interval without overlapping requests', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  let active = 0, maximum = 0, completed = 0;
  await page.route('**/api/v1/state', async route => {
    active++; maximum = Math.max(maximum, active);
    await new Promise(resolve => setTimeout(resolve, 1400));
    active--; completed++;
    await route.fallback();
  });
  await page.goto('/#overview');
  await expect(page.locator('#batteryMetric')).toHaveText('83%', { timeout: 6000 });
  await expect.poll(() => completed).toBeGreaterThanOrEqual(3);
  expect(maximum).toBe(1);
  expect(backend.state.requests).toEqual([]);
});

test('a stalled state response times out and polling recovers without a reload', async ({ page }) => {
  const backend = await installDashboardBackend(page);
  const started = [];
  await page.route('**/api/v1/state', async route => {
    started.push(Date.now());
    if (started.length === 1) return; // Keep the first request pending, like a silent connection.
    await route.fallback();
  });
  await page.goto('/#overview');
  await expect(page.locator('#batteryMetric')).toHaveText('83%', { timeout: 8000 });
  expect(started.length).toBeGreaterThanOrEqual(2);
  expect(started[1] - started[0]).toBeGreaterThanOrEqual(4500);
  expect(started[1] - started[0]).toBeLessThan(7500);
  expect(backend.state.requests).toEqual([]);
});
