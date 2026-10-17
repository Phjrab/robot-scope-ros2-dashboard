import { expect, test } from '@playwright/test';
import { deflateSync } from 'node:zlib';
import { mkdir } from 'node:fs/promises';
import { installDashboardBackend } from './dashboard_backend.mjs';

// Entirely synthetic browser fixture: no robot, broker, camera or ROS process.
const SAMPLE_ID = 'd'.repeat(32);
const SESSION = { session_id: 'depth-fixture-session', generation: 4, engine_id: 'realsense_depth',
  task: 'calibration', state: 'CAPTURING' };
const FLAGS = { robot_seated: true, robot_stationary: true, camera_stationary: true };

function syntheticPng(width = 640, height = 480) {
  const chunk = (type, bytes) => {
    const body = Buffer.concat([Buffer.from(type), bytes]);
    let crc = 0xffffffff;
    for (const byte of body) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    const size = Buffer.alloc(4), checksum = Buffer.alloc(4);
    size.writeUInt32BE(bytes.length); checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
    return Buffer.concat([size, body, checksum]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8;
  const raw = Buffer.alloc((width + 1) * height);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) raw[y * (width + 1) + x + 1] =
    (Math.floor(x / 40) + Math.floor(y / 40)) % 2 ? 180 : 70;
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

async function fixture(page, { stereo = false, captureUncertain = false } = {}) {
  const backend = await installDashboardBackend(page);
  const state = { session: stereo ? { session_id: 'existing-stereo', generation: 2,
    engine_id: 'visual_stereo', task: 'mapping', state: 'MAPPING', map_epoch: 'stereo-map' } : null,
    mutations: [], samples: [], errors: [] };
  page.on('pageerror', error => state.errors.push(error.message));
  await page.routeWebSocket('**/api/v1/ws/slam*', () => {});
  await page.route('**/api/v1/slam/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.slice('/api/v1/slam'.length);
    const body = request.method() === 'POST' ? request.postDataJSON() : null;
    const reply = (json, status = 200) => route.fulfill({ status, json });
    if (body) state.mutations.push({ path, body });
    if (path === '/engines') return reply({ engines: [
      { engine_id: 'lidar_fastlio', available_now: true, tasks: ['mapping'] },
      { engine_id: 'visual_stereo', available_now: true, tasks: ['mapping', 'tracking'] },
      { engine_id: 'realsense_depth', available_now: true, tasks: ['calibration'] },
    ] });
    if (path === '/session') return reply({ active_session: state.session,
      camera: { reserved: Boolean(state.session && state.session.state !== 'IDLE'), reservation_unknown: false } });
    if (path === '/packages') return reply({ packages: [] });
    if (path === '/depth/samples') return reply({ samples: state.samples });
    if (path === '/depth/sessions' && body) {
      if (state.session && state.session.state !== 'IDLE') return reply({ detail: { code: 'RESOURCE_CONFLICT' } }, 409);
      state.session = { ...SESSION }; return reply({ ...SESSION }, 202);
    }
    if (path === `/sessions/${SESSION.session_id}/depth-samples` && body) {
      if (captureUncertain) return reply({ detail: { code: 'DEPTH_CAPTURE_OUTCOME_UNKNOWN' } }, 503);
      const receipt = { sample_id: SAMPLE_ID, ...SESSION, synthetic: true,
        compatibility: { available: true, reason: 'SYNTHETIC_FIXTURE_NO_HARDWARE' },
        image: { available: true, width: 640, height: 480, frame_id: 'fixture_infrared_optical' } };
      state.samples = [receipt]; return reply(receipt);
    }
    if (path === `/sessions/${SESSION.session_id}/stop` && body) {
      state.session = { ...SESSION, state: 'IDLE' }; return reply(state.session, 202);
    }
    if (path === `/depth/samples/${SAMPLE_ID}/image`) return route.fulfill({
      contentType: 'image/png', body: syntheticPng() });
    if (path === `/depth/samples/${SAMPLE_ID}/export`) return route.fulfill({
      contentType: 'application/zip', body: Buffer.from('504b0506000000000000000000000000000000000000', 'hex'),
      headers: { 'Content-Disposition': 'attachment; filename="SYNTHETIC-depth-sample.zip"' } });
    if (path === `/depth/samples/${SAMPLE_ID}/compatibility`) return route.fulfill({
      contentType: 'application/json', body: JSON.stringify({ synthetic: true, available: true }),
      headers: { 'Content-Disposition': 'attachment; filename="SYNTHETIC-depth-compatibility.json"' } });
    return reply({ detail: { code: 'UNEXPECTED_FIXTURE_REQUEST' } }, 404);
  });
  return { state, backend };
}

async function confirm(page) {
  for (const key of Object.keys(FLAGS)) await page.locator(`#depth_${key}`).check();
}

for (const width of [390, 1440]) {
  test(`synthetic depth lifecycle saves native pixels and exposes exports at ${width}px`, async ({ page }) => {
    const { state, backend } = await fixture(page);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/#mapping');
    const panel = page.locator('#depthCaptureConsole');
    await expect(panel).toBeVisible(); await expect(page.locator('#depthCaptureState')).toHaveText('IDLE');
    await expect(page.locator('#depthCaptureStart')).toBeDisabled();
    await confirm(page); await page.locator('#depthCaptureStart').click();
    await expect(page.locator('#depthCaptureState')).toHaveText('CAPTURING');
    await expect(page.locator('#depthCaptureSample')).toBeDisabled();
    for (const key of Object.keys(FLAGS)) await expect(page.locator(`#depth_${key}`)).not.toBeChecked();
    await confirm(page); await page.locator('#depthCaptureSample').click();
    const image = page.locator('#depthCaptureImage');
    await expect(image).toBeVisible();
    await expect(page.locator('#depthCaptureSampleDetail')).toContainText('SYNTHETIC_FIXTURE_NO_HARDWARE');
    await expect(page.locator('#depthCaptureSampleDetail')).toContainText('640 × 480px');
    expect(await image.evaluate(node => [node.getAttribute('width'), node.getAttribute('height'), node.naturalWidth, node.naturalHeight])).toEqual(['640', '480', 640, 480]);
    if (width === 390) expect((await image.boundingBox()).width).toBeLessThan(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    await expect(page.locator('#depthCaptureSample')).toBeDisabled();
    for (const key of Object.keys(FLAGS)) await expect(page.locator(`#depth_${key}`)).not.toBeChecked();
    for (const [name, suffix, type] of [['샘플 ZIP', 'export', 'application/zip'], ['호환성 JSON', 'compatibility', 'application/json']]) {
      const link = panel.getByRole('link', { name, exact: true });
      await expect(link).toHaveAttribute('href', `/api/v1/slam/depth/samples/${SAMPLE_ID}/${suffix}`);
      await expect(link).toHaveAttribute('download', '');
      // Native Chromium downloads bypass page.route; verify the actual DOM link
      // and its mocked browser GET without claiming a native file-save test.
      const response = await link.evaluate(async node => {
        const response = await fetch(node.href);
        return { type: response.headers.get('Content-Type'), disposition: response.headers.get('Content-Disposition'),
          prefix: [...new Uint8Array(await response.arrayBuffer()).slice(0, 2)] };
      });
      expect(response.type).toBe(type);
      expect(response.disposition).toContain('SYNTHETIC-depth-');
      if (suffix === 'export') expect(response.prefix).toEqual([80, 75]);
    }
    if (process.env.DEPTH_CAPTURE_SCREENSHOTS) {
      await mkdir(process.env.DEPTH_CAPTURE_SCREENSHOTS, { recursive: true });
      await panel.screenshot({ path: `${process.env.DEPTH_CAPTURE_SCREENSHOTS}/SYNTHETIC-depth-capture-${width}.png` });
    }
    await page.locator('#depthCaptureStop').click();
    await expect(page.locator('#depthCaptureState')).toHaveText('IDLE');
    expect(state.mutations.map(value => value.path)).toEqual(['/depth/sessions',
      `/sessions/${SESSION.session_id}/depth-samples`, `/sessions/${SESSION.session_id}/stop`]);
    expect(state.mutations[0].body).toMatchObject(FLAGS);
    expect(state.mutations[1].body).toMatchObject({ ...FLAGS, generation: 4, body_attitude: null });
    expect(state.mutations[2].body).toMatchObject({ generation: 4, discard_unsaved: false });
    expect(state.mutations.every(item => /^[A-Za-z0-9_-]{8,96}$/.test(item.body.request_id))).toBe(true);
    expect(backend.state.requests.filter(request => request.method === 'POST')).toEqual([]);
    expect(state.errors).toEqual([]);
  });
}

test('existing Stereo session remains exclusive and depth controls are mapping-only', async ({ page }) => {
  const { state } = await fixture(page, { stereo: true });
  await page.goto('/#mapping');
  await expect(page.locator('#depthCaptureMessage')).toContainText('다른 관측 세션');
  await confirm(page);
  for (const id of ['depthCaptureStart', 'depthCaptureSample', 'depthCaptureStop']) await expect(page.locator('#' + id)).toBeDisabled();
  await page.getByRole('link', { name: '저장 지도 · 지도 탐색·편집', exact: true }).click();
  await expect(page.locator('#depthCaptureConsole')).toBeHidden();
  await page.locator('[data-nav="mapping"]').click();
  await expect(page.locator('#depthCaptureConsole')).toBeVisible();
  expect(state.mutations).toEqual([]); expect(state.session.session_id).toBe('existing-stereo');
  expect(state.errors).toEqual([]);
});

test('uncertain capture does not silently submit another sample after refresh', async ({ page }) => {
  const { state } = await fixture(page, { captureUncertain: true });
  await page.goto('/#mapping'); await expect(page.locator('#depthCaptureState')).toHaveText('IDLE');
  await confirm(page); await page.locator('#depthCaptureStart').click();
  await expect(page.locator('#depthCaptureState')).toHaveText('CAPTURING');
  await confirm(page); await page.locator('#depthCaptureSample').click();
  await expect(page.locator('#depthCaptureMessage')).toContainText('요청 결과 미확정');
  await page.locator('#depthCaptureRefresh').click(); await confirm(page);
  await expect(page.locator('#depthCaptureSample')).toBeDisabled();
  await expect(page.locator('#depthCaptureImage')).toBeHidden();
  await expect(page.locator('#depthCaptureStop')).toBeEnabled();
  expect(state.mutations.filter(value => value.path.endsWith('/depth-samples'))).toHaveLength(1);
  await page.locator('#depthCaptureStop').click();
  await expect(page.locator('#depthCaptureState')).toHaveText('IDLE');
  expect(state.errors).toEqual([]);
});
