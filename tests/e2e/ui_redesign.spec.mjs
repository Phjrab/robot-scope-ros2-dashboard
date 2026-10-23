import { expect, test } from '@playwright/test';
import { mkdir, appendFile, writeFile, readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { installMissionFixture } from './ui_redesign_fixture.mjs';

const phase = process.env.UI_CAPTURE_PHASE || 'after';
const evidenceRoot = process.env.UI_EVIDENCE_ROOT || 'docs/ui-redesign';
const captureRoot = `${evidenceRoot}/captures`;
test.beforeAll(async () => {
  await mkdir(`${captureRoot}/${phase}`, { recursive: true });
  await mkdir(`${evidenceRoot}/evidence`, { recursive: true });
});
const provenance = 'mission-control-v1 synthetic sensor/map fixture; no ROS/backend process';

async function isolated(page, options = {}) {
  return installMissionFixture(page, options);
}

async function fixtureLabel(page) {
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.id = 'syntheticFixtureLabel';
    label.textContent = 'UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님';
    label.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;padding:6px 12px;background:#11161c;color:#e9f0f5;border-top:1px solid #59d3e5;font:12px system-ui;pointer-events:none';
    document.body.append(label);
  });
}

test('Mission Control actual route captures with isolated synthetic data', async ({ page }) => {
  test.setTimeout(120_000);
  const { backend, unexpected, consoleErrors, pageErrors, httpErrors } = await isolated(page);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await mkdir(`${captureRoot}/${phase}`, { recursive: true });
  const manifest = `${captureRoot}/CAPTURE_MANIFEST.csv`;
  const manifestHeader = 'filename,repo,commit_sha,captured_at,viewport,route,scenario,fixture_id,data_provenance,live_actions,privacy_review\n';
  if (phase === 'before') await writeFile(manifest, manifestHeader);
  else {
    const previous = await readFile(manifest, 'utf8').catch((error) => { if (error.code === 'ENOENT') return manifestHeader; throw error; });
    await writeFile(manifest, previous.split('\n').filter((line) => !line.startsWith(`${phase}/`) && line).join('\n') + '\n');
  }
  const sha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    for (const scenario of ['observation', 'navigation', 'maps', 'capture', 'disconnected']) {
      if (viewport.width < 1366 && !['observation', 'disconnected'].includes(scenario)) continue;
      backend.state.online = scenario !== 'disconnected';
      const route = { observation: 'cockpit', navigation: 'navigation', maps: 'maps', capture: 'sensors', disconnected: 'cockpit' }[scenario];
      await page.goto(`/?ui-capture=${scenario}-${viewport.width}#${route}`);
      await expect(page.locator('#pageTitle')).not.toHaveText('');
      await expect(page.locator('#connectionLabel')).toContainText(scenario === 'disconnected' ? '연결 끊김' : '준비');
      if (scenario === 'maps') { await expect(page.locator('.saved-map-item')).toHaveCount(1); await page.locator('.saved-map-item').click(); }
      await page.evaluate(() => document.fonts.ready);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.waitForTimeout(650);
      await fixtureLabel(page);
      const filename = `${phase}/${scenario}-${viewport.width}x${viewport.height}.png`;
      await page.screenshot({ path: `${captureRoot}/${filename}`, animations: 'disabled' });
      await appendFile(manifest, `${filename},Phjrab/robot-scope-ros2-dashboard,${sha}${phase === 'after' ? '+working-tree' : ''},${new Date().toISOString()},${viewport.width}x${viewport.height},/#${route},${scenario},mission-control-v1,${provenance},NONE,SYNTHETIC_ONLY\n`);
    }
  }
  expect(unexpected).toEqual([]);
  expect(errors).toEqual([]);
  expect(httpErrors.filter((entry) => !((entry.url === '/api/v1/state' && entry.status === 503) || (entry.url === '/static/data/go2_saved_map.json' && entry.status === 404)))).toEqual([]);
  await writeFile(`${evidenceRoot}/evidence/${phase}-capture-events.json`, JSON.stringify({ unexpected, consoleErrors, pageErrors, httpErrors, mutations: backend.state.requests }, null, 2));
  expect(backend.state.requests.filter((request) => /control\/(arm|acquire|command)|navigation\/goal|mapping\/start/.test(request.path))).toEqual([]);
});

async function editLayout(page) {
  // Layout editing is directly available while safety details stay collapsed.
  await page.locator('[data-cockpit-layout-action="edit"]').click();
  await expect(page.locator('#missionPresetSelect')).toBeEnabled();
}

test('Mission Control presets preserve singleton lifecycle, camera cleanup, resize and zero control requests', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend, unexpected, pageErrors } = await isolated(page, { closeFirstSockets: ['camera', 'pointcloud'] });
  await page.goto('/');
  await expect(page.locator('#pageTitle')).toHaveText('관측');
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'fixture');
  await expect(page.locator('[data-panel-id="camera-go2-front"]')).toBeVisible();
  await expect.poll(() => backend.state.wsConnections.pointcloud).toBeGreaterThanOrEqual(2);
  await editLayout(page);
  for (let index = 0; index < 20; index += 1) {
    const id = ['mapping', 'navigation', 'capture', 'observation'][index % 4];
    await page.locator('#missionPresetSelect').selectOption(id);
    await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-mission-preset', id);
    const snapshot = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
    const visible = snapshot.workspace.panels.panels.filter((panel) => panel.visible);
    expect(new Set(visible.map((panel) => panel.id)).size).toBe(visible.length);
    expect(snapshot.workspace.scene.rendererCount).toBe(1);
    expect(snapshot.pointcloud.activeConsumers).toEqual(['cockpit']);
  }
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  await expect(page.locator('#missionPresetSelect')).toBeDisabled();
  await page.setViewportSize({ width: 1366, height: 768 });
  await expect.poll(() => page.locator('#cockpitSceneCanvas').evaluate((canvas) => canvas.width)).toBeGreaterThan(600);
  await page.reload();
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  await page.goto('/#overview');
  await expect.poll(() => page.evaluate(() => window.RobotScopeCameraStreams.snapshot().demand.totalConsumers)).toBe(0);
  expect(unexpected).toEqual([]); expect(pageErrors).toEqual([]);
  expect(backend.state.requests.filter((entry) => /control\/(arm|acquire|command)|navigation\/(start|goal)|mapping\/(start|save)/.test(entry.path))).toEqual([]);
});

test('Mission Control keeps stale camera/cloud distinct and disconnected STOP available in Settings', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend } = await isolated(page);
  await page.goto('/#cockpit');
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'fixture');
  await expect(page.locator('[data-panel-id="camera-go2-front"] .cockpit-camera-state')).toHaveText('합성 예시');
  await expect(page.locator('[data-panel-id="camera-go2-front"] .cockpit-camera-state')).toHaveAttribute('data-state', 'fixture');
  backend.state.uiCloudStreaming = false;
  backend.state.cameraStreaming.go2_front = false;
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'stale', { timeout: 8000 });
  await expect(page.locator('[data-inspector-field="camera"]')).toHaveText('오래된 데이터');
  await expect(page.locator('[data-inspector-field="camera"]')).toHaveAttribute('data-state', 'stale');
  backend.state.online = false;
  for (const route of ['cockpit', 'mapping', 'maps', 'navigation', 'sensors', 'controls', 'route-planner', 'settings']) {
    await page.goto(`/?offline=${route}#${route}`);
    await expect(page.locator('#connectionLabel')).toContainText('연결 끊김');
    if (route === 'settings') await page.locator('[data-cockpit-software-stop]').click({ trial: true });
    else await expect(page.locator('[data-cockpit-software-stop]')).toBeHidden();
  }
  expect(backend.mutations('/api/v1/control/arm')).toHaveLength(0);
});

test('Mission Control mock STOP distinguishes pending, server acknowledgement and failure with no dialog', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend } = await isolated(page);
  let dialogs = 0; page.on('dialog', () => { dialogs += 1; });
  backend.on('/api/v1/control/stop', async ({ json }) => { await new Promise((resolve) => setTimeout(resolve, 200)); return json({ state: 'stopped', estop_latched: true }); });
  await page.goto('/#settings');
  await page.locator('[data-cockpit-software-stop]').click();
  await expect(page.locator('#softwareStopFeedback')).toHaveAttribute('data-state', 'pending');
  await expect(page.locator('#softwareStopFeedback')).toHaveAttribute('data-state', 'acknowledged');
  backend.on('/api/v1/control/stop', ({ json }) => json({ detail: 'fixture stop unavailable' }, 503));
  await page.locator('[data-cockpit-software-stop]').click();
  await expect(page.locator('#softwareStopFeedback')).toHaveAttribute('data-state', 'failed');
  await expect(page.locator('#softwareStopFeedback')).toContainText('정지 미확인');
  expect(backend.mutations('/api/v1/control/stop')).toHaveLength(2); expect(dialogs).toBe(0);
});

test('Mission Control ownership blocks presets, denied ARM stays disarmed, map search preserves revision', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend } = await isolated(page);
  backend.state.control.lease = { active: true, source: 'other-client', bound: false };
  await page.goto('/#cockpit');
  await expect(page.locator('#missionPresetSelect')).toBeDisabled();
  await expect(page.locator('[data-cockpit-layout-action="edit"]')).toBeDisabled();
  backend.state.control.lease = { active: false, bound: false, source: null };
  backend.on('/api/v1/control/arm', ({ json }) => json({ detail: 'fixture ownership denied' }, 403));
  await page.goto('/#controls');
  await expect(page.locator('#controlArmButton')).toBeEnabled();
  await page.locator('#controlArmButton').click();
  await expect(page.locator('#controlArmButton')).toBeEnabled();
  await expect(page.locator('.cockpit-safety-summary')).toContainText('ARM DISARMED');
  await page.goto('/#maps');
  await expect(page.locator('.saved-map-item')).toHaveCount(1);
  await page.locator('.saved-map-item').click();
  await expect(page.locator('#savedMapRevision')).toHaveText(backend.mapRevision);
  await page.locator('#savedMapSearch').fill('<script> no result');
  await expect(page.locator('#savedMapList')).toContainText('검색 결과가 없습니다');
  await expect(page.locator('#savedMapRevision')).toHaveText(backend.mapRevision);
  await page.locator('#savedMapSearch').fill('STATIC');
  await expect(page.locator('.saved-map-item')).toHaveCount(1);
  expect(backend.mutations('/api/v1/navigation/goal')).toHaveLength(0);
});

test('Mission Control viewport, keyboard, safety hit target and token contrast are checked in Chromium', async ({ page }) => {
  test.skip(phase === 'before');
  const { pageErrors } = await isolated(page);
  const geometry = [];
  for (const size of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 720, height: 450 }]) {
    await page.setViewportSize(size);
    await page.goto(`/?viewport=${size.width}#cockpit`);
    await expect(page.locator('#cockpitWorkspace')).toBeVisible();
    await expect(page.locator('[data-cockpit-software-stop]')).toBeHidden();
    const bounds = await page.evaluate(() => {
      const workspace = document.querySelector('#cockpitWorkspace').getBoundingClientRect();
      const scene = document.querySelector('#cockpitSceneCanvas').getBoundingClientRect();
      return { workspaceWidth: workspace.width, sceneWidth: scene.width, sceneHeight: scene.height,
        tools: ['.cockpit-overlay-layer', '.cockpit-scene-controls', '#cockpitLayoutLibrary', '#cockpitCompetitionStatus'].map((selector) => { const node = document.querySelector(selector); const style = getComputedStyle(node); return { selector, box: node.getBoundingClientRect().toJSON(), column: style.gridColumn, row: style.gridRow, columns: style.gridTemplateColumns }; }),
        overflow: document.documentElement.scrollWidth > innerWidth };
    });
    expect(bounds.overflow).toBe(false);
    if (size.width >= 1024) {
      expect(bounds.sceneWidth / bounds.workspaceWidth).toBeGreaterThanOrEqual(0.6);
      expect(bounds.tools[3].box.bottom).toBeLessThanOrEqual(bounds.tools[0].box.bottom);
    }
    expect(bounds.sceneHeight).toBeGreaterThan(200);
    await page.evaluate(() => { location.hash = 'settings'; });
    const stop = page.locator('[data-cockpit-software-stop]');
    await stop.click({ trial: true });
    const stopBounds = await stop.boundingBox();
    expect(stopBounds.height).toBeGreaterThanOrEqual(44);
    expect(stopBounds.x).toBeGreaterThanOrEqual(0); expect(stopBounds.y).toBeGreaterThanOrEqual(0);
    expect(stopBounds.x + stopBounds.width).toBeLessThanOrEqual(size.width);
    expect(stopBounds.y + stopBounds.height).toBeLessThanOrEqual(size.height);
    geometry.push({ ...size, ...bounds, stopBounds, stopRoute: 'settings' });
  }
  await page.locator('.cockpit-safety-toggle').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#cockpitSafetyHud')).toHaveAttribute('data-expanded', 'true');
  await page.locator('[data-cockpit-software-stop]').click({ trial: true });
  const contrasts = await page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    const luminance = (hex) => hex.match(/[a-f\d]{2}/gi).map((value) => parseInt(value, 16) / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    const ratio = (first, second) => { const values = [luminance(first), luminance(second)].sort((a, b) => b - a); return (values[0] + .05) / (values[1] + .05); };
    const value = (name) => styles.getPropertyValue(name).trim();
    return { body: ratio(value('--text'), value('--panel')), secondary: ratio(value('--muted'), value('--panel')), action: ratio(value('--cyan'), value('--panel')), boundary: ratio(value('--line-strong'), value('--bg')) };
  });
  for (const key of ['body', 'secondary', 'action']) expect(contrasts[key]).toBeGreaterThanOrEqual(4.5);
  expect(contrasts.boundary).toBeGreaterThanOrEqual(3);
  await writeFile(`${evidenceRoot}/evidence/browser-geometry-contrast.json`, JSON.stringify({ geometry, contrasts, pageErrors, zoomEquivalent: '720x450 represents 200% CSS viewport at 1440x900' }, null, 2));
  expect(pageErrors).toEqual([]);
});

test('Mission Control migrates old layout in memory and keeps corrupted original recoverable', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend } = await isolated(page);
  const key = 'robot-scope.cockpit.applied-layout.v1.go2';
  const legacy = JSON.stringify({ schema_version: 0, name: 'Legacy operator layout', profile: 'go2',
    scene: { view: 'top', follow_robot: false, point_size: 2, range_m: 150 },
    panels: [{ id: 'placeholder-map', panel_type: 'placeholder.map', mode: 'floating', dock: null,
      x: .1, y: .2, width: .4, height: .5, z_index: 1, pinned: false, locked: false, restore_geometry: null }] });
  await page.goto('/#overview');
  await page.evaluate(({ key, legacy }) => localStorage.setItem(key, legacy), { key, legacy });
  await page.goto('/?migration=v0#cockpit');
  await expect(page.locator('[data-panel-id="placeholder-map"]')).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBe(legacy);
  await expect(page.locator('#missionPresetSelect')).toHaveValue('saved');
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  await page.evaluate((key) => localStorage.setItem(key, '{broken-original'), key);
  await page.goto('/?migration=corrupt#cockpit');
  await expect(page.locator('[data-panel-id="camera-go2-front"]')).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBe('{broken-original');
  expect(backend.state.requests.filter((entry) => /control\/(arm|acquire|command)|navigation\/goal/.test(entry.path))).toEqual([]);
});


test('Mission Control long map names and server errors stay escaped and empty maps remain usable', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend, map, pageErrors } = await isolated(page);
  const long = '<img src=x onerror="window.__unsafeName=true">' + '긴 지도명'.repeat(80);
  backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: [{ ...map, name: long }], total_size_bytes: map.size_bytes }));
  await page.goto('/#maps');
  await expect(page.locator('.saved-map-item')).toContainText(long);
  expect(await page.evaluate(() => window.__unsafeName)).toBeUndefined();
  expect(await page.locator('#savedMapList img').count()).toBe(0);
  await page.locator('.saved-map-item').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  backend.on('/api/v1/control/stop', ({ json }) => json({ detail: long }, 503));
  await page.goto('/#settings');
  await page.locator('[data-cockpit-software-stop]').click();
  await expect(page.locator('#softwareStopFeedback')).toHaveAttribute('data-state', 'failed');
  await expect(page.locator('#softwareStopFeedback')).toContainText('정지 미확인');
  expect(await page.evaluate(() => window.__unsafeName)).toBeUndefined();
  backend.on('/api/v1/saved-maps', ({ json }) => json({ maps: [], total_size_bytes: 0 }));
  await page.goto('/#maps');
  await page.reload();
  await expect(page.locator('[data-saved-map-id="' + map.id + '"]')).toHaveCount(0);
  await expect(page.locator('#savedMapList')).toContainText('Public demo cloud');
  await expect(page.locator('[data-saved-map-id="__fallback_cloud"]')).toHaveCount(1);
  await page.goto('/#settings');
  await page.locator('[data-cockpit-software-stop]').click({ trial: true });
  expect(pageErrors).toEqual([]);
});
