// Hardware-free Chromium visual audit. All API/stream inputs are synthetic.
// Run: node docs/ui-consistency/audit.mjs before|after
import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { installDashboardBackend } from '../../tests/e2e/dashboard_backend.mjs';

const phase = process.argv[2];
if (!['before', 'after'].includes(phase)) throw new Error('Use before or after');
// Fixture stream timers should not keep the CLI alive after Chromium closes.
const interval = globalThis.setInterval;
globalThis.setInterval = (...args) => interval(...args).unref();
const root = resolve('docs/ui-consistency'), output = resolve(root, 'captures', phase);
await mkdir(output, { recursive: true });
const origin = 'http://127.0.0.1:4187';
const server = spawn(process.execPath, ['tests/e2e/static_server.mjs'], {
  env: { ...process.env, UI_REGRESSION_PORT: '4187', UI_PROBE_PORT: '4188' }, stdio: 'ignore',
});
const browser = await chromium.launch();
const report = { phase, provenance: 'SYNTHETIC_BROWSER_FIXTURE_ONLY', hardware: 'NOT_CONTACTED', cases: [] };
const baseline = '1b7e191b89e7';
report.baseline = baseline;
report.componentCapture = 'Global topbar, safety HUD, footer and toast are hidden only during component screenshots. Viewport captures retain the actual shell.';
const id = '3'.repeat(24), revision = 'b'.repeat(64), points = [];
for (let x = -5; x <= 5; x += .5) for (let y = -5; y <= 5; y += .5) points.push(x, y, Math.abs(x) > 4 || Math.abs(y) > 4 ? 1 : 0);
const cloud = { id, revision, kind: 'pointcloud3d', name: 'SYNTHETIC · saved 3D reference', frame_id: 'map',
  format: 'pcd-binary', file_name: 'synthetic.pcd', point_count: points.length / 3, source_points: points.length / 3,
  size_bytes: 12000, manageable: true, data_url: `/api/v1/saved-maps/${id}/data` };
const observation = (seq, epoch = 'c') => ({ observer_id: 'd'.repeat(32), publisher_epoch: epoch.repeat(32), publisher_gid: epoch.repeat(32), publisher_count: 1,
  identity_status: 'OBSERVED_PUBLISHER', source_stamp_ns: String(1792309179130175352n + BigInt(seq)), received_monotonic_s: Date.now() / 1000, receipt_clock: 'OBSERVER_HOST_MONOTONIC' });
function binary(seq, obs) {
  const metadata = Buffer.from(JSON.stringify({ seq, stream_id: 'synthetic', topic: '/cloud_registered', pipeline_stage: 'registered', frame_id: 'odom', units: 'm', encoding: 'float32le', point_count: points.length / 3, source_points: points.length / 3, observation: obs }));
  const offset = (16 + metadata.length + 3) & ~3, buffer = Buffer.alloc(offset + points.length * 4);
  buffer.write('RSPC'); buffer.writeUInt8(1, 4); buffer.writeUInt16LE(metadata.length, 6); buffer.writeUInt32LE(points.length / 3, 8); buffer.writeUInt32LE(points.length * 4, 12); metadata.copy(buffer, 16);
  points.forEach((v, i) => buffer.writeFloatLE(v, offset + i * 4)); return buffer;
}
async function inspect(page, selector, name, theme, width) {
  const target = page.locator(selector);
  await target.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  const metrics = await target.evaluate((element) => {
    const visible = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, right: r.right, width: r.width }; };
    const rgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const luminance = (s) => rgb(s).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((a, v, i) => a + v * [.2126, .7152, .0722][i], 0);
    const entries = [...element.querySelectorAll('p, label, button, input, select, strong, small, th, td, h3, h4, summary')].filter(visible).map(e => {
      const s = getComputedStyle(e); let bg = s.backgroundColor, parent = e;
      while (bg === 'rgba(0, 0, 0, 0)' && (parent = parent.parentElement)) bg = getComputedStyle(parent).backgroundColor;
      const l = luminance(s.color), b = luminance(bg);
      return { id: e.id || e.className || e.tagName, text: e.textContent.trim().slice(0, 80), size: parseFloat(s.fontSize), font: s.fontFamily, containedTable: Boolean(e.closest('.table-scroll')),
        contrast: (Math.max(l, b) + .05) / (Math.min(l, b) + .05), opacity: s.opacity, disabled: e.disabled || false, ...box(e) };
    });
    return { viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, panel: box(element),
      overflow: entries.filter(e => !e.containedTable && (e.x < -1 || e.right > innerWidth + 1)),
      containedTableOverflow: entries.filter(e => e.containedTable && (e.x < -1 || e.right > innerWidth + 1)),
      lowContrast: entries.filter(e => !e.disabled && e.opacity === '1' && e.contrast < 4.5), entries };
  });
  const path = `${theme}-${name}-${width}.png`;
  if (['observation', 'calibration'].includes(name) && width !== 1024) await page.screenshot({ path: resolve(output, `${theme}-${name}-${width}-viewport.png`), animations: 'disabled' });
  await target.screenshot({ path: resolve(output, path), animations: 'disabled', style: '.topbar, .toast, footer, .cockpit-safety-hud { visibility: hidden !important; }' });
  report.cases.push({ theme, name, width, screenshot: `captures/${phase}/${path}`, ...metrics });
}

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(origin)).ok) break; } catch {} await new Promise(r => setTimeout(r, 100)); }
  for (const theme of ['dark', 'light']) for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' });
    const errors = [], writes = []; let lastCloud, streaming = true;
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', dialog => dialog.accept());
    page.on('request', r => { if (!['GET', 'HEAD', 'OPTIONS'].includes(r.method())) writes.push(new URL(r.url()).pathname); });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.fallback() : route.abort());
    const backend = await installDashboardBackend(page, { pointcloudFrame: seq => { if (!streaming) return null; lastCloud = observation(seq); return binary(seq, lastCloud); } });
    if (phase === 'before') {
      for (const file of ['index.html', 'features/maps/live_observation.js', 'features/maps/live_observation.css', 'features/map_editor3d/editor.css', 'features/settings/mount_calibration.css']) {
        const content = execFileSync('git', ['show', `${baseline}:robot_dashboard/static/${file}`], { encoding: 'utf8' });
        await page.route(file === 'index.html' ? `${origin}/` : `**/static/${file}`, route => route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html', body: content }));
      }
    }
    backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: [
      { id: backend.mapId, revision: backend.state.mapRevision, kind: 'occupancy2d', name: 'SYNTHETIC · 2D map', format: 'map-server-pgm', file_name: 'fixture.yaml', frame_id: 'map', width: 4, height: 4, resolution: .25, origin: [0, 0, 0], size_bytes: 4096, manageable: true, editable: true, data_url: `/api/v1/saved-maps/${backend.mapId}/data` }, cloud,
    ], total_size_bytes: 16096 }));
    backend.on(cloud.data_url, ({ json }) => json({ ...cloud, map_id: id, seq: 1, points, units: 'm' }));
    backend.on('/api/v1/observations/map-alignment', ({ json, body }) => json({ schema: 'robot-scope.observation-alignment.v1', experimental: true, operational_application: 'NOT_RUN', map_id: id, map_revision: revision, target_frame: 'map', source: { ...body, received_monotonic_s: lastCloud.received_monotonic_s }, status: 'CANDIDATE', reason: 'CANDIDATE', T_map_odom: body.T_map_odom_seed, correspondence_gate_m: .75, metrics: { converged: true, rmse_m: .02, overlap_ratio: .8, geometry_min_max_eigen_ratio: .2, matched_geometry_min_max_eigen_ratio: .2 } }));
    backend.on('/api/v1/settings/mount-calibration/status', ({ json }) => json({ mode: 'offline', provenance: 'SYNTHETIC_BROWSER_FIXTURE', hardware_access: false, persistence: false }));
    backend.on('/api/v1/settings/mount-calibration/estimate', ({ json, body }) => json({ schema_version: '1.0.0', status: 'RELATIVE_ONLY', synthetic: true, provenance: 'SYNTHETIC_BROWSER_FIXTURE', reference_id: body.reference_id, body_extrinsic_validated: false, absolute_pitch_validated: false, pitch_only_consistent: true, warnings: ['SYNTHETIC · UI only · not an operational validation'], samples: body.samples.map((sample, index) => ({ id: sample.id, relative_pitch_deg: index * 7.5, normal_camera: [0, 0, 1], plane_rmse_m: .00025, valid_points: sample.points.length, inlier_points: sample.points.length, inlier_ratio: 1, warnings: [], validated_points: sample.points.map(p => ({ ...p, valid: true, inlier: true })) })) }));
    await page.routeWebSocket('**/api/v1/ws/pose', socket => {
      let seq = 0; const send = () => { if (streaming) socket.send(JSON.stringify({ seq: ++seq, topic: '/Odometry', frame_id: 'odom', child_frame_id: 'base_link', state: 'ok', age_s: 0, position: { x: 0, y: 0, z: .3 }, orientation: { x: 0, y: 0, z: 0, w: 1 }, observation: observation(seq, 'f') })); };
      send(); const timer = setInterval(send, 150); socket.onClose(() => clearInterval(timer));
    });
    await page.goto(`${origin}/#maps`);
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    await page.locator('.saved-map-item').filter({ hasText: 'SYNTHETIC · 2D map' }).click();
    await expect(page.locator('#mapEditorState')).toContainText('READY');
    await page.locator('#mapEditorRotationNumber').fill('27.5');
    await inspect(page, '.map-editor-panel', 'editor-2d', theme, width);
    await page.locator('.saved-map-item').filter({ hasText: cloud.name }).click();
    await expect(page.locator('#savedMapTitle')).toContainText(cloud.name);
    await page.locator('#mapEditorMode').selectOption('3d');
    await page.locator('#map3Load').click();
    await expect(page.locator('#map3Stats')).toContainText(id);
    const canvas = page.locator('#map3Canvas'); await canvas.scrollIntoViewIfNeeded(); const b = await canvas.boundingBox();
    for (const [x, y] of [[.4, .35], [.6, .35], [.6, .65], [.4, .65]]) await page.mouse.click(b.x + b.width * x, b.y + b.height * y);
    await page.locator('#map3Add').click(); await expect(page.locator('#map3Regions li')).toHaveCount(1);
    await page.locator('#map3Preview').check();
    await inspect(page, '.map-editor-panel', 'editor-3d', theme, width);
    await page.locator('#mapEditorMode').selectOption('2d');
    await expect(page.locator('#mapEditorRotationNumber')).toHaveValue('27.5');
    await expect(page.locator('#mapEditor3D')).toBeHidden();
    await page.locator('#mapEditorMode').selectOption('3d'); await expect(page.locator('#map3Regions li')).toHaveCount(1);
    await page.locator('#savedLiveEnabled').check(); await page.locator('#savedLiveConfirm').check(); await page.locator('#savedLiveAnchor').click();
    await page.locator('#savedLiveRegistration').check(); await expect(page.locator('#savedLiveState')).toHaveText('SCAN_TO_MAP_CANDIDATE_UNVERIFIED');
    await inspect(page, '#savedLiveObservation', 'observation', theme, width);
    streaming = false; await expect(page.locator('#savedLiveState')).toHaveText('STALE');
    await expect(page.locator('#savedLiveCenter')).toBeDisabled();
    await inspect(page, '#savedLiveObservation', 'observation-stale', theme, width);
    if (phase === 'after') await expect(page.locator('#savedLiveState')).toHaveAttribute('data-status', 'STALE');
    await page.goto(`${origin}/#settings`); await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    await page.locator('#mount-calibration-demo-button').click();
    await inspect(page, '#mount-calibration-panel', 'calibration', theme, width);
    for (const name of ['stationary', 'wall', 'pitch']) await page.locator(`#mount-calibration-${name}-check`).check();
    await page.locator('#mount-calibration-estimate-button').click();
    await expect(page.locator('#mount-calibration-results-content')).toBeVisible();
    await inspect(page, '.mount-calibration .results-panel', 'results', theme, width);
    if (phase === 'after') {
      const table = page.getByRole('region', { name: '상대 피치 추정 결과 표 · 좌우 스크롤' });
      await table.focus(); await expect(table).toBeFocused();
      if (width === 390) { await table.press('ArrowRight'); await expect.poll(() => table.evaluate(e => e.scrollLeft)).toBeGreaterThan(0); }
    }
    await inspect(page, '.diagnostics-export-panel', 'diagnostics', theme, width);
    const controls = page.locator('#diagnosticsExportButton'); await controls.focus(); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
    await expect(controls).toBeFocused();
    const focus = await controls.evaluate(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return { visible: e.matches(':focus-visible'), outline: s.outline, offset: s.outlineOffset, unobscured: e.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)) }; });
    report.cases.push({ theme, width, name: 'behavior', errors, writes, focus, draftsPreserved: true, stalePreserved: true });
    expect(errors).toEqual([]);
    expect(writes.every(p => ['/api/v1/observations/map-alignment', '/api/v1/settings/mount-calibration/estimate'].includes(p))).toBe(true);
    await page.close();
    console.log(`${phase}: ${theme} ${width} complete`);
  }
} finally {
  await writeFile(resolve(root, `${phase}.json`), JSON.stringify(report, null, 2) + '\n');
  await browser.close(); server.kill('SIGTERM');
  globalThis.setInterval = interval;
}
