// Rendered UI regression checks with synthetic, read-only inputs only.
import { expect, test } from '@playwright/test';
import { installMissionFixture } from './ui_redesign_fixture.mjs';

async function fixture(page) {
  const f = await installMissionFixture(page);
  const map = { id: 'a'.repeat(24), revision: 'b'.repeat(64), name: 'SYNTHETIC consistency reference',
    kind: 'pointcloud3d', frame_id: 'map', format: 'pcd-binary', file_name: 'fixture.pcd', point_count: 5, size_bytes: 1000 };
  let seq = 0;
  const values = {
    '/api/v1/routes': { routes: [] }, '/api/v1/mission-plans': { definitions: [], context: {} }, '/api/v1/mission-runs': { runs: [] },
    '/api/v1/saved-maps': { maps: [map], total_size_bytes: 1000 },
    [`/api/v1/observations/course-regions/${map.id}`]: {
      map: { map_id: map.id, map_revision: map.revision, map_frame: map.frame_id }, presets: [], incompatible_count: 0,
    },
    [`/api/v1/observations/anchor-presets/${map.id}`]: {
      map: { map_id: map.id, map_revision: map.revision, map_frame: map.frame_id },
      presets: [], incompatible_count: 0, approximate_only: true, requires_reanchor: true,
    },
    [`/api/v1/saved-maps/${map.id}/data`]: { ...map, map_id: map.id, seq: 1,
      points: [-2,-2,0, 2,-2,0, 2,2,0, -2,2,0, 0,0,1], units: 'm', source_points: 5 },
    '/api/v1/observations/global-jobs': { schema: 'robot-scope.raw-global-observations.v1',
      provider: { available: false, reason: 'SYNTHETIC_NO_HARDWARE' }, generation: 0, active: null, latest: null,
      historical_only: true, current_result: null, body_pose: null, tracking_verified: false,
      body_pose_verified: false, body_extrinsic_verified: false, operational_application: 'NOT_RUN', absolute_accuracy_m: null },
    '/api/v1/observations/sensor-tracking': { schema: 'robot-scope.sensor-tracking.v1', state: 'WAITING_GLOBAL',
      generation: 0, reason: 'SYNTHETIC_DIAGNOSTIC', worker_active: false, source_global_job: null, map: null,
      source: null, sensor_pose: null, trail: [], temporal_consistency_confirmed: false,
      globally_verified: false, body_pose: null, tracking_verified: false, source_clock_verified: false,
      body_extrinsic_verified: false, operational_application: 'NOT_RUN',
      last_alignment: { status: 'REJECTED', reason: 'SYNTHETIC_DIAGNOSTIC' } },
  };
  for (const [path, value] of Object.entries(values)) f.backend.on(path, ({ method, json }) => {
    expect(method).toBe('GET'); return json(value);
  });
  f.backend.on('/api/v1/system/resources', ({ method, json }) => {
    expect(method).toBe('GET');
    return json({ schema: 'robot-scope.resources.v1', seq: ++seq, timestamp_ms: Date.now(), sample_interval_s: 1,
      host: { model: 'Jetson fixture', hostname: 'fixture' }, cpu: { percent: 25, cores: [] },
      gpu: { percent: 15 }, memory: { percent: 40 }, sensors: {} });
  });
  return { ...f, map };
}

async function tokenColor(page, token) {
  return page.evaluate(token => {
    const probe = document.createElement('span'); probe.style.color = `var(${token})`; document.body.append(probe);
    const color = getComputedStyle(probe).color; probe.remove(); return color;
  }, token);
}
async function focusRing(page, target) {
  await page.keyboard.press('Tab'); await target.focus();
  await expect(target).toBeFocused();
  await expect(target).toHaveCSS('outline-width', '3px');
  await expect(target).toHaveCSS('outline-offset', '3px');
  await expect(target).toHaveCSS('outline-color', await tokenColor(page, '--cyan'));
}
async function standardField(target) {
  await expect(target).toHaveCSS('font-size', '15px');
  await expect(target).toHaveCSS('border-radius', '5px');
  expect(await target.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
}

for (const width of [390, 1440]) for (const theme of ['dark', 'light']) {
  test(`shared headings, controls and observation copy remain consistent at ${width}px in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(theme => localStorage.setItem('robot-scope.ui.theme.v1', theme), theme);
    const f = await fixture(page);
    const noOverflow = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.goto('/#resources');
    await expect(page.locator('#hostModel')).toHaveText('Jetson fixture');
    await expect(page.locator('h1:visible')).toHaveCount(1);
    await expect(page.locator('main:visible')).toHaveCount(1);
    await expect(page.locator('#resourceMonitor .intro-copy')).toBeVisible();
    await expect(page.locator('#resourceMonitor #connectionState')).toHaveAttribute('data-state', 'live');
    await expect(page.locator('#resourceMonitor .panel-heading h2').first()).toHaveCSS('font-size', '18px');
    await expect(page.locator('#resourceMonitor .panel-heading h2').first()).toHaveCSS('font-weight', '600');
    await standardField(page.locator('#loadThreshold'));
    await standardField(page.locator('#pauseButton'));
    await focusRing(page, page.locator('#pauseButton'));
    await noOverflow();

    await page.goto('/#sensors');
    await standardField(page.locator('.camera-primary-picker select'));
    await noOverflow();

    await page.goto('/#missions');
    const edit = page.locator('.mr-mode-actions button').first();
    await standardField(edit);
    await standardField(page.locator('.mr-identity select'));
    await focusRing(page, edit);
    await focusRing(page, page.locator('.mr-workspace svg'));
    await noOverflow();

    await page.goto('/#maps');
    await page.locator('.saved-map-item').filter({ hasText: f.map.name }).click();
    const sensor = page.locator('#savedSensorTracking');
    await expect(sensor).toBeVisible();
    await sensor.locator('.saved-sensor-heading').click();
    for (const selector of ['p', 'small']) {
      for (const copy of await sensor.locator(selector).all()) {
        await expect(copy).toHaveCSS('font-size', '15px');
        await expect(copy).toHaveCSS('line-height', '23.25px');
      }
    }
    await expect(sensor.locator('small')).toHaveCSS('color', await tokenColor(page, '--muted'));
    await expect(sensor.locator('.saved-sensor-body')).toHaveCSS('padding-left', width < 480 ? '12px' : '16px');
    const disclosure = page.locator('#savedSensorAlternatives > summary');
    await expect(disclosure).toBeVisible();
    expect(await disclosure.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await focusRing(page, disclosure);
    await disclosure.press('Enter');
    await expect(page.locator('#savedSensorAlternativesRecord')).toBeVisible();
    expect(await sensor.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await noOverflow();

    // The title belongs to the standalone page when it is opened directly.
    await page.goto('/static/resources.html');
    await expect(page.locator('h1:visible')).toHaveCount(1);
    await expect(page.locator('h1')).toContainText('Jetson 자원 모니터');
    await expect(page.locator('h1')).toHaveCSS('font-size', width < 820 ? '24px' : '26px');
    await expect(page.locator('#connectionState')).toHaveAttribute('data-state', 'live');
    await standardField(page.locator('#pauseButton'));
    await noOverflow();
    expect(f.pageErrors).toEqual([]); expect(f.unexpected).toEqual([]);
    expect(f.httpErrors.filter(x => x.url !== '/static/data/go2_saved_map.json')).toEqual([]);
    expect(f.backend.state.requests.filter(r => r.method !== 'GET')).toEqual([]);
  });
}
