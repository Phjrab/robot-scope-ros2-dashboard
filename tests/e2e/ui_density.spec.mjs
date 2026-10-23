import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

// Read-only synthetic fixture: no robot, ROS, camera or dataset service is used.
async function fixture(page) {
  await installDashboardBackend(page);
  const state = { session: null, writes: [], errors: [] };
  page.on('pageerror', error => state.errors.push(error.message));
  page.on('request', request => {
    if (!['GET', 'HEAD'].includes(request.method())) state.writes.push(new URL(request.url()).pathname);
  });
  await page.routeWebSocket('**/api/v1/ws/slam*', () => {});
  await page.route('**/api/v1/slam/**', route => {
    const path = new URL(route.request().url()).pathname;
    const value = path.endsWith('/engines') ? { engines: [
      { engine_id: 'lidar_fastlio', available_now: true, tasks: ['mapping'] },
      { engine_id: 'visual_stereo', available_now: true, tasks: ['mapping'] },
      { engine_id: 'realsense_depth', available_now: true, tasks: ['calibration'] },
    ] } : path.endsWith('/session') ? { active_session: state.session, generation: 0,
      camera: { reserved: Boolean(state.session), reservation_unknown: false } }
      : path.endsWith('/packages') ? { packages: [] }
        : path.endsWith('/depth/samples') ? { samples: [] }
          : path.endsWith('/preview') ? { global_map: { points: [], coverage: 'unknown', provenance: 'SYNTHETIC_FIXTURE' } } : {};
    return route.fulfill({ json: value });
  });
  await page.route('**/api/v1/routes', route => route.fulfill({ json: { routes: [] } }));
  await page.route('**/api/v1/mission-plans', route => route.fulfill({ json: { definitions: [], context: {} } }));
  await page.route('**/api/v1/mission-runs', route => route.fulfill({ json: { runs: [] } }));
  return state;
}

async function openWithKeyboard(page, selector) {
  const disclosure = page.locator(selector), summary = disclosure.locator(':scope > summary');
  await expect(disclosure).not.toHaveAttribute('open');
  await expect(disclosure.locator(':scope > :not(summary)').first()).toBeHidden();
  await summary.focus();
  await summary.press('Enter');
  await expect(disclosure).toHaveAttribute('open', '');
  await expect(disclosure.locator(':scope > :not(summary)').first()).toBeVisible();
  expect((await summary.boundingBox()).height).toBeGreaterThanOrEqual(44);
}

for (const width of [390, 1440]) for (const theme of ['dark', 'light']) {
  test(`progressive help keeps safety and primary work visible at ${width}px in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(theme => localStorage.setItem('robot-scope.ui.theme.v1', theme), theme);
    const state = await fixture(page);
    const noOverflow = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await page.goto('/#mapping');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect(page.locator('#depthCaptureState')).toHaveText('IDLE');
    const mapping = await page.locator('[data-page="mapping"]').evaluate(root => {
      const depth = root.querySelector('#depthCaptureConsole');
      const rect = node => node.getBoundingClientRect().toJSON();
      const primary = ['.mapping-panel', '.mapping-control-panel', '.mapping-support-grid'].map(selector => root.querySelector(selector));
      return { depth: rect(depth), primary: primary.map(rect),
        depthFollowsPrimary: primary.every(node => Boolean(node.compareDocumentPosition(depth) & Node.DOCUMENT_POSITION_FOLLOWING)),
        controls: rect(depth.querySelector('.depth-capture-controls')), library: rect(depth.querySelector('.depth-capture-library')),
        actionHeights: [...depth.querySelectorAll('button')].map(node => rect(node).height) };
    });
    expect(mapping.depthFollowsPrimary).toBe(true);
    for (const primary of mapping.primary) expect(mapping.depth.top).toBeGreaterThanOrEqual(primary.bottom);
    if (width > 800) {
      expect(Math.abs(mapping.controls.top - mapping.library.top)).toBeLessThan(1);
      expect(mapping.library.left).toBeGreaterThanOrEqual(mapping.controls.right);
    } else expect(mapping.library.top).toBeGreaterThanOrEqual(mapping.controls.bottom);
    expect(mapping.actionHeights.every(height => height >= 44)).toBe(true);
    for (const key of ['robot_seated', 'robot_stationary', 'camera_stationary']) {
      await expect(page.locator(`#depth_${key}`)).toBeVisible();
      await expect(page.locator(`#depth_${key}`)).not.toBeChecked();
    }
    await expect(page.locator('#depthCaptureStart')).toBeDisabled();
    await noOverflow();

    await page.goto('/#settings');
    const intro = page.locator('.calibration-intro');
    await expect(intro).toBeVisible();
    expect(await intro.evaluate(node => node.closest('details'))).toBeNull();
    await expect(page.locator('#mount-calibration-conditions')).toBeVisible();
    await expect(page.locator('#mount-calibration-estimate-button')).toBeDisabled();
    for (const selector of ['.import-hint', '.calibration-quality-help']) await openWithKeyboard(page, selector);
    await noOverflow();

    await page.goto('/#sensors');
    for (const selector of ['.dataset-help', '.dataset-browser-help']) await openWithKeyboard(page, selector);
    await expect(page.locator('#datasetCaptureState')).toBeVisible();
    await expect(page.locator('#datasetCaptureMessage')).toBeVisible();
    await noOverflow();

    await page.goto('/#missions');
    const safety = page.locator('.mission-page-help');
    await expect(safety).toBeVisible();
    expect(await safety.evaluate(node => node.closest('details'))).toBeNull();
    await openWithKeyboard(page, '.mission-setup-help');
    await noOverflow();

    // Hash navigation keeps native disclosure state without recreating content.
    for (const [route, selectors] of [
      ['settings', ['.import-hint', '.calibration-quality-help']],
      ['sensors', ['.dataset-help', '.dataset-browser-help']],
      ['missions', ['.mission-setup-help']],
    ]) {
      await page.goto(`/#${route}`);
      for (const selector of selectors) {
        const disclosure = page.locator(selector);
        await expect(disclosure).toHaveAttribute('open', '');
        await disclosure.locator(':scope > summary').focus();
        await disclosure.locator(':scope > summary').press('Enter');
        await expect(disclosure.locator(':scope > :not(summary)').first()).toBeHidden();
      }
      await noOverflow();
    }
    await expect(safety).toBeVisible();

    await page.goto('/#maps');
    await expect(page.locator('.saved-map-stage')).toBeVisible();
    expect(await page.locator('.saved-map-stage').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await noOverflow();
    expect(state.writes).toEqual([]);
    expect(state.errors).toEqual([]);
  });
}

test('mobile depth capture keeps a competing session status visible and actions unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await fixture(page);
  state.session = { session_id: 'synthetic-stereo-session', generation: 2, engine_id: 'visual_stereo', task: 'mapping', state: 'WAITING_INPUT' };
  await page.goto('/#mapping');
  const status = page.locator('#depthCaptureState');
  await expect(status).toHaveText('visual_stereo · WAITING_INPUT');
  await expect(status).toBeVisible();
  const panel = page.locator('#depthCaptureConsole');
  expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  for (const key of ['robot_seated', 'robot_stationary', 'camera_stationary']) await page.locator(`#depth_${key}`).check();
  for (const action of ['Start', 'Sample', 'Stop']) await expect(page.locator(`#depthCapture${action}`)).toBeDisabled();
  expect(state.writes).toEqual([]);
  expect(state.errors).toEqual([]);
});
