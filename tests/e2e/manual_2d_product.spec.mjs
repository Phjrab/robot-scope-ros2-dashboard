// Actual dashboard, saved map catalog, FastAPI routes, and navigation
// coordinator. ROS, process, and motion boundaries are SYNTHETIC.
import { test, expect } from '@playwright/test';

test('full experiment prepares, seeds, submits a goal, cancels, and stops', async ({ page, request }) => {
  const readback = async () => (await request.get('/test/manual-navigation')).json();
  // Unrelated hardware telemetry is outside the synthetic boundary.
  await page.routeWebSocket('**/api/v1/ws/**', (socket) => socket.close());
  await page.route(/\/api\/v1\//, (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === 'GET' && !/^\/api\/v1\/(?:navigation(?:\/(?:parameters|logs))?|saved-maps(?:\/.*)?)$/.test(path)) {
      return route.fulfill({ status: 503, json: { detail: 'Synthetic telemetry unavailable' } });
    }
    return route.continue();
  });
  await page.goto('/#experiments');
  const field = (name) => page.locator(`#manual2dExperiment [data-manual="${name}"]`);
  await expect(field('map-info')).toContainText('revision');
  await expect(field('prepare')).toBeDisabled();
  expect(await readback()).toEqual({
    actions: [], job_events: [], mapping_events: [], seed_count: 0, cancellations: [],
  });

  await field('site').check();
  await expect(field('prepare')).toBeEnabled();
  await field('prepare').click();
  await expect(field('status')).toContainText('waiting_initial_pose');

  const drag = async (from, to) => {
    const canvas = field('canvas');
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width * from, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * to, box.y + box.height / 2);
    await page.mouse.up();
  };
  await drag(0.44, 0.56);
  let rejectedSeeds = 0;
  await page.route('**/api/v1/navigation/initial-pose', route => {
    rejectedSeeds++;
    return route.fulfill({status:423, json:{detail:'MANUAL_RESEED_REQUIRES_OBSERVED_STOP'}});
  });
  await field('send').click();
  await expect(field('status')).toContainText('요청 실패:');
  await expect(field('status')).toContainText('MANUAL_RESEED_REQUIRES_OBSERVED_STOP');
  // Polling must retain the explanation without retrying the failed command.
  await page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/navigation' && response.request().method() === 'GET');
  await expect(field('status')).toContainText('MANUAL_RESEED_REQUIRES_OBSERVED_STOP');
  expect(rejectedSeeds).toBe(1);
  expect((await readback()).seed_count).toBe(0);
  await page.unroute('**/api/v1/navigation/initial-pose');
  await field('send').click();
  await expect(field('status')).toContainText('ready_manual');

  await field('goal').click();
  await drag(0.51, 0.63);
  page.once('dialog', (dialog) => dialog.accept());
  await field('send').click();
  await expect(field('cancel')).toBeEnabled();
  await field('cancel').click();
  await expect(field('cancel')).toBeDisabled();
  await field('stop').click();
  await expect(field('status')).toContainText('idle');

  const result = await readback();
  expect(result.seed_count).toBe(1);
  expect(result.actions).toHaveLength(1);
  expect(result.cancellations).toEqual(['synthetic_goal_01']);
  expect(result.job_events).toEqual(['start', ['validate_pose', result.actions[0].map_id],
    ['validate_pose', result.actions[0].map_id], 'stop']);
  expect(result.mapping_events).toEqual(['start_mapping', ['stop_mapping', 'a'.repeat(32)]]);
});
