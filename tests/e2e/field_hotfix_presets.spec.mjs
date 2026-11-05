import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { once } from 'node:events';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.setTimeout(90_000);

async function serverFixture() {
  const root = await mkdtemp(join(tmpdir(), 'a0-preset-http-'));
  let base = '';
  let server, diagnostics = '';
  async function stop() {
    if (!server || server.exitCode !== null) return;
    server.kill('SIGTERM');
    await once(server, 'exit');
  }
  async function start(mode = 'idle') {
    diagnostics = ''; base = '';
    server = spawn(process.env.PCD_EDIT_TEST_PYTHON || 'python3',
      ['tests/e2e/field_hotfix_server.py', root, '0', mode],
      { env: { ...process.env, PYTHONPATH: resolve('.') }, stdio: ['ignore', 'pipe', 'pipe'] });
    server.stdout.on('data', data => {
      const match = String(data).match(/PORT=(\d+)/);
      if (match) base = 'http://127.0.0.1:' + match[1];
    });
    server.stderr.on('data', data => { diagnostics += data; });
    await expect.poll(async () => {
      if (server.exitCode !== null) throw new Error(diagnostics);
      if (!base) return 0;
      try { return (await fetch(base + '/api/v1/navigation/presets')).status; } catch { return 0; }
    }, { timeout: 15_000 }).toBe(200);
  }
  try { await start(); }
  catch (error) { await stop(); await rm(root, { recursive: true, force: true }); throw error; }
  return {
    root, get base() { return base; },
    async restart(mode) { await stop(); await start(mode); },
    async close() { await stop(); await rm(root, { recursive: true, force: true }); },
  };
}

test('real preset HTTP roundtrip, restart, conflict, partial apply and built-in protection', async ({ page, context }, testInfo) => {
  const server = await serverFixture();
  try {
    const backend = await installDashboardBackend(page);
    const errors = [], writes = [];
    page.on('pageerror', error => errors.push(error.message));
    let pauseUpdate = null;
    await page.route(/\/api\/v1\/navigation\/(presets(?:\/[^/]+)?|parameters)$/, async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() !== 'GET') writes.push({ path, method: request.method(), body: request.postDataJSON() });
      if (pauseUpdate && request.method() === 'PATCH' && path.includes('/presets/')) await pauseUpdate;
      const response = await fetch(server.base + path, {
        method: request.method(),
        headers: { 'Content-Type': 'application/json', Origin: server.base },
        body: request.postData() || undefined,
      });
      await route.fulfill({ status: response.status, contentType: 'application/json', body: await response.text() });
    });
    await page.goto('/#navigation');
    const speed = page.locator('[data-navigation-parameter="desired_linear_vel"]');
    await expect(speed).toHaveValue('0.25');
    await expect(page.locator('#navigationPresetUpdate')).toBeDisabled();
    const initial = await (await fetch(server.base + '/api/v1/navigation/parameters')).json();
    async function saveAs(name, value) {
      await speed.fill(value);
      await page.locator('#navigationPresetName').fill(name);
      await page.locator('#navigationPresetSave').click();
      await expect(page.locator('#navigationPresetMessage')).toContainText('저장했습니다');
      return await page.locator('#navigationPreset').inputValue();
    }
    const a = await saveAs('A', '0.4');
    const b = await saveAs('B', '0.3');
    expect((await (await fetch(server.base + '/api/v1/navigation/parameters')).json()).revision).toBe(initial.revision);
    async function load(id) {
      await page.locator('#navigationPreset').selectOption(id);
      await page.locator('#navigationPresetLoad').click();
    }
    await load(a);
    await expect(speed).toHaveValue('0.4');
    await speed.fill('0.5');
    await page.locator('#navigationParameterApply').click();
    await expect(page.locator('#navigationParameterDirty')).toHaveText('NO CHANGES');
    await expect(page.locator('#navigationPresetDifference')).toContainText('1개');
    let release;
    pauseUpdate = new Promise(resolve => { release = resolve; });
    await page.locator('#navigationPresetUpdate').click();
    await expect(page.locator('#navigationPreset')).toBeDisabled();
    await expect(speed).toBeDisabled();
    release(); pauseUpdate = null;
    await expect(page.locator('#navigationPresetMessage')).toContainText('프리셋 저장 완료');
    await load(b); await load(a);
    await expect(speed).toHaveValue('0.5');
    await page.reload();
    await expect(speed).toHaveValue('0.5');
    await load(a); await expect(speed).toHaveValue('0.5');
    await server.restart();
    await page.reload(); await load(a);
    await expect(speed).toHaveValue('0.5');
    const second = await context.newPage();
    await installDashboardBackend(second);
    // A new tab uses a fresh catalog over the real HTTP service.
    await second.route(/\/api\/v1\/navigation\/presets$/, async route => {
      const response = await fetch(server.base + '/api/v1/navigation/presets');
      await route.fulfill({ json: await response.json() });
    });
    await second.goto('/#navigation');
    await second.locator('#navigationPreset').selectOption(a);
    await second.locator('#navigationPresetLoad').click();
    await expect(second.locator('[data-navigation-parameter="desired_linear_vel"]')).toHaveValue('0.5');
    await second.close();

    // Another client wins while this tab retains its loaded revision.
    const catalog = await (await fetch(server.base + '/api/v1/navigation/presets')).json();
    const stored = catalog.presets.find(preset => preset.id === a);
    const external = await fetch(server.base + '/api/v1/navigation/presets/' + a, {
      method: 'PATCH', headers: { Origin: server.base, 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_revision: stored.revision, values: { ...stored.values, desired_linear_vel: .6 } }),
    });
    expect(external.status).toBe(200);
    await speed.fill('0.55');
    await page.locator('#navigationPresetUpdate').click();
    await expect(page.locator('#navigationPresetMessage')).toContainText('다른 사용자가 수정');
    await expect(speed).toHaveValue('0.55');
    await page.locator('#navigationPresetRefresh').click();
    await expect(page.locator('#navigationPresetDifference')).toContainText('desired_linear_vel=0.6');
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('#navigationPresetUpdate').click();
    await expect(speed).toHaveValue('0.55');
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#navigationPresetApply').click();
    await expect(page.locator('#navigationPresetMessage')).toContainText('프리셋 저장 완료 / 현재 설정 적용 완료');

    // Server running while the UI snapshot is idle exercises partial success.
    await speed.fill('0.52');
    const staleCurrent = await fetch(server.base + '/api/v1/navigation/parameters');
    const active = await staleCurrent.json();
    await fetch(server.base + '/api/v1/navigation/parameters', {
      method: 'PATCH', headers: { Origin: server.base, 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_revision: active.revision, values: { desired_linear_vel: .56 } }),
    });
    await page.locator('#navigationParameterApply').click();
    await expect(speed).toHaveValue('0.52');
    await page.locator('#refreshButton').click();
    await expect(speed).toHaveValue('0.52');
    await page.locator('#navigationParameterApply').click();
    await expect(page.locator('#navigationParameterDirty')).toHaveText('NO CHANGES');
    await server.restart('running');
    await speed.fill('0.45');
    await page.locator('#navigationPresetApply').click();
    await expect(page.locator('#navigationPresetMessage')).toContainText('프리셋 저장 완료 / 현재 적용 실패');
    await expect(speed).toHaveValue('0.45');
    const end = await (await fetch(server.base + '/api/v1/navigation/presets')).json();
    expect(end.presets).toHaveLength(2);
    expect(end.presets.find(preset => preset.id === a).values.desired_linear_vel).toBe(.45);
    const current = await (await fetch(server.base + '/api/v1/navigation/parameters')).json();
    expect(current.values.desired_linear_vel).toBe(.52);
    expect(current.presets[0]).toEqual(initial.presets[0]);
    expect(writes.every(write => write.path.includes('/presets') || write.path.endsWith('/parameters'))).toBe(true);
    expect(backend.state.requests.filter(write => /\/goal|\/start|\/control/.test(write.path))).toEqual([]);
    expect(errors).toEqual([]);
    for (const [theme, width] of [['dark', 1440], ['light', 390]]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      await page.locator('.navigation-parameters-panel').screenshot({ path: testInfo.outputPath('presets-' + theme + '-' + width + '.png') });
    }
    const file = JSON.parse(await readFile(join(server.root, 'navigation/presets.json'), 'utf8'));
    expect(file.presets.find(preset => preset.id === a).values.desired_linear_vel).toBe(.45);
  } finally { await server.close(); }
});
