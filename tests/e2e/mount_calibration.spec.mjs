import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

// These are hardware-free browser integration tests. Every API response below is
// a SYNTHETIC fixture, not a call to the Python solver or a real camera/robot.
const API = '/api/v1/settings/mount-calibration';
const PREFIX = 'mount-calibration-';
const checks = ['stationary-check', 'wall-check', 'pitch-check'];
const field = (page, id) => page.locator(`#${PREFIX}${id}`);
const panel = (page) => field(page, 'panel');
const sampleButtons = (page) => field(page, 'sample-list').locator('.sample-select');
const forbiddenMutation = /\/api\/v1\/(?:control|navigation|mapping|slam|missions|mission-runs|camera|cameras|realsense|services|system\/services?|datasets)(?:\/|$)/;

function syntheticAnalysis(input, marker = 'SYNTHETIC_MOCK_ANALYSIS') {
  // Deliberate fixed values exercise rendering only. Solver correctness belongs
  // to the real Python API/core tests, never these mocked browser responses.
  const referenceIndex = input.samples.findIndex((sample) => sample.id === input.reference_id);
  return {
    schema_version: '1.0.0', status: 'RELATIVE_ONLY', synthetic: true,
    provenance: 'SYNTHETIC_BROWSER_FIXTURE', reference_id: input.reference_id,
    body_extrinsic_validated: false, absolute_pitch_validated: false,
    pitch_only_consistent: true, warnings: [marker],
    samples: input.samples.map((sample, index) => ({
      id: sample.id, relative_pitch_deg: (index - referenceIndex) * 7.5,
      normal_camera: [0, 0, 1], plane_rmse_m: 0.00025,
      valid_points: sample.points.length, inlier_points: sample.points.length,
      inlier_ratio: 1, warnings: [],
      validated_points: sample.points.map((point) => ({ ...point, valid: true, inlier: true })),
    })),
  };
}

function syntheticImport() {
  const width = 16, height = 12;
  return {
    reference_id: 'SYNTHETIC import A',
    samples: ['A', 'B'].map((label) => ({
      id: `SYNTHETIC import ${label}`, width, height,
      intrinsics: { fx: 16, fy: 16, cx: 8, cy: 6, model: 'pinhole' },
      depth_m: Array(width * height).fill(2.2),
      points: [{ u: 2, v: 2 }, { u: 8, v: 2 }, { u: 13, v: 2 }, { u: 2, v: 9 }, { u: 8, v: 9 }, { u: 13, v: 9 }],
      metadata: {
        synthetic: true, serial: 'SYNTHETIC-NO-DEVICE', rectified: true,
        frame_id: 'camera_depth_optical_frame', profile_id: 'synthetic-16x12',
        depth_semantics: 'optical_z', projection_model: 'pinhole',
        source_timestamp: '2026-01-01T00:00:00.000Z', clock_domain: 'synthetic_fixture',
      },
    })),
  };
}

async function fixture(page, options = {}) {
  const errors = [], writes = [], requests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push({ path, method: request.method() });
  });
  const backend = await installDashboardBackend(page, { online: false });
  await page.route(`**${API}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const body = method === 'POST' ? request.postDataJSON() : null;
    requests.push({ path, method, body, headers: await request.allHeaders() });
    if (path === `${API}/status` && method === 'GET') {
      return route.fulfill({ json: {
        status: 'ok', schema_version: '1.0.0', mode: 'offline',
        input_source: 'imported_depth_json', live_capture_available: false,
        hardware_access: false, persistence: false,
        body_extrinsic_validated: false, absolute_pitch_validated: false,
        max_request_bytes: 64 * 1024 * 1024, provenance: 'SYNTHETIC_BROWSER_FIXTURE',
      } });
    }
    if (path === `${API}/estimate` && method === 'POST') {
      const index = requests.filter((entry) => entry.path === path).length;
      if (options.estimate) return options.estimate({ route, body, index });
      return route.fulfill({ json: syntheticAnalysis(body) });
    }
    if (path === `${API}/export` && method === 'POST') {
      return route.fulfill({ json: {
        schema_version: '1.0.0', export_kind: 'relative_wall_pitch_analysis',
        input: body, analysis: syntheticAnalysis(body, 'SYNTHETIC_EXPORT_RECOMPUTED'),
      } });
    }
    throw new Error(`Unexpected mount calibration request: ${method} ${path}`);
  });
  return { backend, errors, writes, requests };
}

async function openSettings(page) {
  await page.goto('/#settings');
  await expect(page.locator('[data-page="settings"]')).toBeVisible();
  await expect(panel(page)).toBeVisible();
}

async function loadDemo(page) {
  await field(page, 'demo-button').click();
  await expect(sampleButtons(page)).toHaveCount(3);
  await expect(field(page, 'source-badge')).toContainText('합성');
  for (const id of checks) await expect(field(page, id)).not.toBeChecked();
}

async function confirmConditions(page) {
  for (const id of checks) await field(page, id).check();
  await expect(field(page, 'estimate-button')).toBeEnabled();
}

async function estimate(page) {
  await field(page, 'estimate-button').click();
  await expect(field(page, 'results-content')).toBeVisible();
  await expect(field(page, 'export-button')).toBeEnabled();
}

async function expectInvalidated(page) {
  await expect(field(page, 'results-content')).toBeHidden();
  await expect(field(page, 'results-empty')).toBeVisible();
  await expect(field(page, 'export-button')).toBeDisabled();
}

function expectNoHardwareEffects(state) {
  expect(state.writes.filter((request) => forbiddenMutation.test(request.path))).toEqual([]);
  expect(state.backend.state.wsConnections.camera).toBe(0);
  expect(state.errors).toEqual([]);
}

test.describe('Settings mount calibration · SYNTHETIC mocked integration', () => {
  test('is a native, empty Settings panel without automatic capture, demo, or analysis', async ({ page }) => {
    const state = await fixture(page);
    await openSettings(page);
    await expect(panel(page).locator('iframe')).toHaveCount(0);
    await expect(panel(page).locator('a[target="_blank"]')).toHaveCount(0);
    await expect(sampleButtons(page)).toHaveCount(0);
    await expect(field(page, 'sample-total')).toHaveText(/0+/);
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await expect(field(page, 'export-button')).toBeDisabled();
    for (const id of checks) await expect(field(page, id)).not.toBeChecked();
    await expect(panel(page)).toContainText(/가져오기|가져온/);
    await expect(panel(page).getByRole('button', { name: /실장비.*적용|TF.*적용|VSLAM.*시작|apply.*hardware|start.*vslam/i })).toHaveCount(0);
    await expect.poll(() => state.requests.filter((request) => request.path === `${API}/status`).length).toBeGreaterThan(0);
    await expect(field(page, 'status')).toContainText('IMPORT ONLY');
    await expect(field(page, 'depth-canvas')).toBeHidden();
    expect(state.requests.filter((request) => request.method === 'POST')).toEqual([]);
    expect(new URL(page.url()).hash).toBe('#settings');
    expectNoHardwareEffects(state);
  });

  test('loads demo only on click and gates estimation on explicit conditions and spread-out points', async ({ page }) => {
    const state = await fixture(page);
    await openSettings(page);
    await loadDemo(page);
    await expect(field(page, 'fixture-note')).toContainText('합성');
    await expect(field(page, 'metadata-list')).toContainText('SYNTHETIC-NO-DEVICE');
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await expect(field(page, 'point-count')).toHaveText('8');
    await field(page, 'depth-canvas').click();
    await expect(field(page, 'point-count')).toHaveText('9');
    await field(page, 'undo-button').click();
    await expect(field(page, 'point-count')).toHaveText('8');
    await field(page, 'clear-button').click();
    await expect(field(page, 'point-count')).toHaveText('0');
    for (const id of checks) await field(page, id).check();
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await panel(page).locator('.manual-points summary').click();
    for (const [u, v] of [[45, 38], [160, 35], [274, 40], [45, 200], [160, 204], [275, 200]]) {
      await field(page, 'point-u').fill(String(u));
      await field(page, 'point-v').fill(String(v));
      await field(page, 'point-form').getByRole('button', { name: '점 추가' }).click();
    }
    await expect(field(page, 'point-count')).toHaveText('6');
    await expect(field(page, 'estimate-button')).toBeEnabled();
    expect(state.requests.filter((request) => request.method === 'POST')).toEqual([]);
    expectNoHardwareEffects(state);
  });

  test('renders synthetic relative-only results, keeps view-only selection, and invalidates edited inputs', async ({ page }) => {
    const state = await fixture(page);
    await openSettings(page);
    await loadDemo(page);
    await confirmConditions(page);
    await estimate(page);
    await expect(field(page, 'results-summary')).toContainText('합성 데모 분석');
    await expect(field(page, 'results-summary')).toContainText('상대 피치만');
    await expect(field(page, 'results-summary')).toContainText('본체 외부 파라미터 미검증');
    await expect(field(page, 'results-body').locator('tr')).toHaveCount(3);
    await expect(field(page, 'result-warnings')).toContainText('SYNTHETIC_MOCK_ANALYSIS');
    const request = state.requests.find((entry) => entry.path === `${API}/estimate`);
    expect(request.method).toBe('POST');
    expect(request.headers['content-type']).toContain('application/json');
    expect(request.headers.origin).toBe(new URL(page.url()).origin);
    expect(request.headers['x-robot-scope-browser-session']).toBeTruthy();
    expect(Number(request.headers['x-robot-scope-request-sequence'])).toBeGreaterThan(0);
    expect(request.body).toMatchObject({ robot_stationary_confirmed: true, wall_same_confirmed: true, mount_only_pitch_confirmed: true });
    expect(request.body.samples).toHaveLength(3);
    expect(request.body.samples.every((sample) => sample.metadata.synthetic === true)).toBe(true);

    await sampleButtons(page).nth(1).click();
    await expect(field(page, 'results-content')).toBeVisible();
    await expect(field(page, 'schematic-angle')).toHaveText('+7.50°');
    await field(page, 'depth-canvas').click();
    await expectInvalidated(page);
    await estimate(page);
    await field(page, 'wall-check').uncheck();
    await expectInvalidated(page);
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await field(page, 'wall-check').check();
    await estimate(page);
    await field(page, 'sample-list').locator('input[type="radio"]').nth(1).check();
    await expectInvalidated(page);
    expectNoHardwareEffects(state);
  });

  test('imports replace synthetic inputs, reset assertions, and never trust imported analysis', async ({ page }) => {
    const state = await fixture(page);
    await openSettings(page);
    await loadDemo(page);
    await confirmConditions(page);
    await estimate(page);
    const input = syntheticImport();
    await field(page, 'file-input').setInputFiles({
      name: 'SYNTHETIC-import-with-untrusted-analysis.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({ input, analysis: { status: 'VALIDATED_BODY_EXTRINSIC', samples: [], synthetic: false } })),
    });
    await expect(sampleButtons(page)).toHaveCount(2);
    await expect(sampleButtons(page).first()).toContainText('SYNTHETIC import A');
    await expectInvalidated(page);
    for (const id of checks) await expect(field(page, id)).not.toBeChecked();
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await expect(panel(page)).not.toContainText('VALIDATED_BODY_EXTRINSIC');
    expect(state.requests.filter((request) => request.path === `${API}/estimate`)).toHaveLength(1);
    await confirmConditions(page);
    await estimate(page);
    await field(page, 'file-input').setInputFiles({
      name: 'SYNTHETIC-invalid.json', mimeType: 'application/json', buffer: Buffer.from('{"samples":[]}'),
    });
    await expect(field(page, 'notice')).toContainText('가져오기 실패');
    await expectInvalidated(page);
    expectNoHardwareEffects(state);
  });

  test('export sends current input for recomputation and downloads a clearly synthetic JSON', async ({ page }) => {
    const state = await fixture(page);
    await openSettings(page);
    await loadDemo(page);
    await confirmConditions(page);
    await estimate(page);
    const downloadPromise = page.waitForEvent('download');
    await field(page, 'export-button').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);
    const stream = await download.createReadStream();
    expect(stream).not.toBeNull();
    let text = '';
    for await (const chunk of stream) text += chunk.toString('utf8');
    const exported = JSON.parse(text);
    expect(exported.export_kind).toBe('relative_wall_pitch_analysis');
    expect(exported.analysis.synthetic).toBe(true);
    expect(exported.analysis.body_extrinsic_validated).toBe(false);
    expect(exported.analysis.warnings).toContain('SYNTHETIC_EXPORT_RECOMPUTED');
    const exports = state.requests.filter((request) => request.path === `${API}/export`);
    expect(exports).toHaveLength(1);
    expect(exported.input).toEqual(exports[0].body);
    await expect(field(page, 'result-warnings')).toContainText('SYNTHETIC_EXPORT_RECOMPUTED');
    expectNoHardwareEffects(state);
  });

  test('a delayed estimate cannot restore results after the inputs change', async ({ page }) => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    let finished;
    const responded = new Promise((resolve) => { finished = resolve; });
    const state = await fixture(page, { estimate: async ({ route, body }) => {
      await gate;
      try { await route.fulfill({ json: syntheticAnalysis(body, 'SYNTHETIC_STALE_RESPONSE') }); }
      catch (error) {
        // Aborting the request is expected after an input edit; teardown errors
        // are not silently swallowed by the ordinary fixture.
        if (!/closed|canceled|cancelled|aborted|handled/i.test(error.message)) throw error;
      } finally { finished(); }
    } });
    await openSettings(page);
    await loadDemo(page);
    await confirmConditions(page);
    await field(page, 'estimate-button').click();
    await expect.poll(() => state.requests.filter((request) => request.path === `${API}/estimate`).length).toBe(1);
    await field(page, 'wall-check').uncheck();
    await expectInvalidated(page);
    release();
    await responded;
    // Allow delivery and painting after the mocked server response is released.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expectInvalidated(page);
    await expect(field(page, 'estimate-button')).toBeDisabled();
    await expect(field(page, 'result-warnings')).not.toBeVisible();
    expectNoHardwareEffects(state);
  });

  test('server validation errors stay visible without stale success or an enabled export', async ({ page }) => {
    const state = await fixture(page, { estimate: ({ route }) => route.fulfill({
      status: 422, json: { detail: 'SYNTHETIC fixture: depth metadata is inconsistent.' },
    }) });
    await openSettings(page);
    await loadDemo(page);
    await confirmConditions(page);
    await field(page, 'estimate-button').click();
    await expect(field(page, 'notice')).toContainText('SYNTHETIC fixture: depth metadata is inconsistent.');
    await expectInvalidated(page);
    await expect(field(page, 'estimate-button')).toBeEnabled();
    expectNoHardwareEffects(state);
  });

  for (const width of [390, 768, 1440]) {
    test(`native calibration stays inside the ${width}px viewport before and after results`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const state = await fixture(page);
      await openSettings(page);
      const expectNoOverflow = async () => {
        const layout = await panel(page).evaluate((root) => ({
          documentWidth: document.documentElement.scrollWidth,
          panelLeft: root.getBoundingClientRect().left,
          panelRight: root.getBoundingClientRect().right,
          viewerWidth: root.querySelector('.canvas-wrap').getBoundingClientRect().width,
        }));
        expect(layout.documentWidth).toBeLessThanOrEqual(width + 1);
        expect(layout.panelLeft).toBeGreaterThanOrEqual(-1);
        expect(layout.panelRight).toBeLessThanOrEqual(width + 1);
        expect(layout.viewerWidth).toBeGreaterThan(200);
      };
      await expectNoOverflow();
      await loadDemo(page);
      await confirmConditions(page);
      await estimate(page);
      await expectNoOverflow();
      await expect(field(page, 'results-body').locator('tr')).toHaveCount(3);
      expectNoHardwareEffects(state);
    });
  }
});
