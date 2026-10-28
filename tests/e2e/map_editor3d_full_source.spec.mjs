// Synthetic browser flow through the real catalogue/store, without app lifespan or robot access.
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { delimiter, join, resolve } from 'node:path';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.use({ viewport: { width: 1600, height: 2200 } });
test.setTimeout(60_000);

const exec = promisify(execFile);
const repository = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const bridge = fileURLToPath(new URL('./pcd_edit_fixture.py', import.meta.url));
const python = process.env.PCD_EDIT_TEST_PYTHON || 'python3';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

async function fixture(page) {
  const root = await mkdtemp(join(tmpdir(), 'robot-scope-pcd-browser-'));
  const call = async (command, ...args) => {
    const env = { ...process.env, PYTHONPATH: [repository, process.env.PYTHONPATH].filter(Boolean).join(delimiter) };
    const { stdout } = await exec(python, [bridge, root, command, ...args], { cwd: repository, env, maxBuffer: 8 * 1024 * 1024 });
    return JSON.parse(stdout);
  };
  try {
    const initial = (await call('init')).data;
    const original = initial.maps[0];
    expect(initial.maps).toHaveLength(1);
    expect(original.point_count).toBe(12_000);
    const originalBytes = await readFile(join(root, 'synthetic_source.pcd'));
    const originalHash = sha256(originalBytes);
    const backend = await installDashboardBackend(page);
    const pageErrors = [], requests = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/pcd-edited-copy')) requests.push(request.postDataJSON());
    });
    let saved = null, failNextCatalogueRefresh = false, alteredDescriptor = false;
    const addMapRoutes = map => {
      backend.on(`/api/v1/saved-maps/${map.id}/data`, async ({ json }) => {
        const answer = await call('data', map.id); return json(answer.data, answer.status);
      });
      backend.on(`/api/v1/saved-maps/${map.id}/pcd-edit-source`, async ({ json }) => {
        const answer = await call('descriptor', map.id);
        if (alteredDescriptor) answer.data.sha256 = '0'.repeat(64);
        return json(answer.data, answer.status);
      });
      backend.on(`/api/v1/saved-maps/${map.id}/pcd-edited-copy`, async ({ json, body }) => {
        const answer = await call('save', map.id, JSON.stringify(body));
        if (answer.status === 201) {
          saved = answer.data.map;
          addMapRoutes(saved);
        }
        return json(answer.data, answer.status);
      });
    };
    addMapRoutes(original);
    backend.on('/api/v1/saved-maps', async ({ json }) => {
      if (failNextCatalogueRefresh && saved) {
        failNextCatalogueRefresh = false;
        return json({ detail: 'synthetic catalogue refresh failure' }, 503);
      }
      const answer = await call('list'); return json(answer.data, answer.status);
    });
    await page.goto('/#maps');
    await expect(page.locator('.saved-map-item').filter({ hasText: original.name })).toBeVisible();
    await page.locator('.saved-map-item').filter({ hasText: original.name }).click();
    await expect(page.locator('#savedMapTitle')).toContainText(original.name);
    // Selection metadata appears before the asynchronous PCD preview is ready.
    await expect(page.locator('#savedMappingState')).toContainText('SAVED 3D MAP');
    await page.locator('#mapEditorMode').selectOption('3d');
    await page.locator('#map3Load').click();
    await expect(page.locator('#map3Stats')).toContainText('150 loaded points / 12,000 source points (sampled)');
    return { root, original, originalHash, backend, requests, pageErrors, call,
      get saved() { return saved; },
      set alteredDescriptor(value) { alteredDescriptor = value; },
      set failNextCatalogueRefresh(value) { failNextCatalogueRefresh = value; },
      async cleanup() { await rm(root, { recursive: true, force: true }); } };
  } catch (error) {
    await rm(root, { recursive: true, force: true });
    throw error;
  }
}

async function addOutsideRegion(page) {
  await page.locator('#map3Selection').selectOption('outside');
  const canvas = page.locator('#map3Canvas');
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  for (const [x, y] of [[500, 320], [600, 320], [600, 220], [500, 220]]) {
    await page.mouse.click(box.x + x / 1100 * box.width, box.y + y / 540 * box.height);
  }
  await page.locator('#map3Add').click();
  await expect(page.locator('#map3Regions li')).toHaveCount(1);
}

test('sampled editor saves a full-source PCD copy, preserves selection, and loads the new revision only when selected', async ({ page }) => {
  const f = await fixture(page);
  try {
    await expect(page.locator('#map3ServerNote')).toContainText('샘플 미리보기');
    await expect(page.locator('#map3ServerSave')).toBeDisabled();
    await addOutsideRegion(page);
    await page.locator('#map3ServerName').fill('synthetic-edited');
    await expect(page.locator('#map3ServerSave')).toBeEnabled();
    await page.locator('#map3ServerSave').click();
    await expect(page.locator('#map3Status')).toContainText('저장·등록');
    await expect(page.locator('.saved-map-item').filter({ hasText: 'synthetic-edited' })).toHaveCount(1);
    const result = f.saved;
    expect(result.id).toMatch(/^[a-f0-9]{24}$/);
    expect(result.revision).toMatch(/^[a-f0-9]{64}$/);
    expect(result.frame_id).toBe('camera_init');
    expect(result.units).toBe('m');
    expect(result.point_count).toBeGreaterThan(150);
    expect(result.point_count).toBeLessThan(f.original.point_count);
    expect(result.manageable).toBe(false);
    expect(f.requests).toHaveLength(1);
    expect(Object.keys(f.requests[0]).sort()).toEqual(['annotation', 'name', 'purpose', 'schema', 'source']);
    expect(JSON.stringify(f.requests[0])).not.toMatch(/"points"|"preview"/);
    expect(f.requests[0].source.sha256).toBe(f.originalHash);
    expect(f.requests[0].annotation.source).toEqual({ map_id: f.original.id, revision: f.original.revision, frame_id: 'camera_init' });
    await expect(page.locator(`.saved-map-item.is-active[data-saved-map-id="${f.original.id}"]`)).toHaveCount(1);
    await expect(page.locator('#savedMapRevision')).toHaveText(f.original.revision);
    await expect(page.locator('#savedGlobalState')).toContainText('HISTORICAL_ONLY');
    expect(f.backend.state.requests.map(request => request.path)).toEqual([`/api/v1/saved-maps/${f.original.id}/pcd-edited-copy`]);
    expect(sha256(await readFile(join(f.root, 'synthetic_source.pcd')))).toBe(f.originalHash);
    expect(sha256(await readFile(join(f.root, 'pcd-edits', result.id, 'map.pcd')))).toBe(result.sha256);
    const manifest = JSON.parse(await readFile(join(f.root, 'pcd-edits', result.id, 'manifest.json'), 'utf8'));
    const edit = manifest.edit_history.at(-1);
    expect(edit.input_points).toBe(f.original.point_count);
    expect(edit.output_points).toBe(result.point_count);
    expect(edit.output_points + edit.removed_points).toBe(f.original.point_count);
    expect(manifest.frame_id).toBe('camera_init');
    expect(manifest.sha256).toBe(result.sha256);
    const fresh = (await f.call('list')).data.maps.find(map => map.id === result.id);
    expect(fresh.revision).toBe(result.revision);
    expect(fresh.point_count).toBe(result.point_count);
    await page.locator(`.saved-map-item[data-saved-map-id="${result.id}"]`).click();
    await expect(page.locator('#savedMapRevision')).toHaveText(result.revision);
    await expect(page.locator('#savedMappingState')).toContainText('SAVED 3D MAP');
    await page.locator('#map3Load').click();
    await expect(page.locator('#map3Stats')).toContainText(`SOURCE ${result.id} · REV ${result.revision} · FRAME camera_init`);
    await expect(page.locator('#savedGlobalState')).toContainText('HISTORICAL_ONLY');
    expect(f.pageErrors).toEqual([]);
  } finally { await f.cleanup(); }
});

test('real store conflict leaves the draft and source selection intact', async ({ page }) => {
  const f = await fixture(page);
  try {
    await addOutsideRegion(page);
    await page.locator('#map3ServerName').fill('conflict-copy');
    f.alteredDescriptor = true;
    await page.locator('#map3ServerSave').click();
    await expect(page.locator('#map3Status')).toContainText('Reload its descriptor and preview');
    await expect(page.locator('#map3Regions li')).toHaveCount(1);
    await expect(page.locator(`.saved-map-item.is-active[data-saved-map-id="${f.original.id}"]`)).toHaveCount(1);
    expect(f.saved).toBeNull();
    expect((await f.call('list')).data.maps).toHaveLength(1);
    expect(sha256(await readFile(join(f.root, 'synthetic_source.pcd')))).toBe(f.originalHash);
    expect(f.pageErrors).toEqual([]);
  } finally { await f.cleanup(); }
});

test('catalogue refresh failure after a real save retains its new ID and the current map', async ({ page }) => {
  const f = await fixture(page);
  try {
    await addOutsideRegion(page);
    await page.locator('#map3ServerName').fill('refresh-failed-copy');
    f.failNextCatalogueRefresh = true;
    await page.locator('#map3ServerSave').click();
    await expect(page.locator('#map3Status')).toContainText('저장·등록');
    expect(f.saved?.id).toMatch(/^[a-f0-9]{24}$/);
    await expect(page.locator('#map3Status')).toContainText(f.saved.id);
    await expect(page.locator('#toast')).toContainText(f.saved.id);
    await expect(page.locator('#toast')).toContainText('새로고침에 실패');
    await expect(page.locator(`.saved-map-item.is-active[data-saved-map-id="${f.original.id}"]`)).toHaveCount(1);
    await expect(page.locator('#savedMapRevision')).toHaveText(f.original.revision);
    expect((await f.call('list')).data.maps.some(map => map.id === f.saved.id)).toBe(true);
    expect(sha256(await readFile(join(f.root, 'synthetic_source.pcd')))).toBe(f.originalHash);
    expect(f.pageErrors).toEqual([]);
  } finally { await f.cleanup(); }
});
