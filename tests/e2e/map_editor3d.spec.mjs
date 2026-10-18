import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test.use({ viewport: { width: 1600, height: 2200 } });

const CLOUD_ID = '3'.repeat(24), CLOUD_REVISION = 'b'.repeat(64);
const points = [];
for (let x = -5; x <= 5; x += 0.25) for (let y = -5; y <= 5; y += 0.25) points.push(x, y, Math.abs(x) > 4.5 || Math.abs(y) > 4.5 ? 1 : 0);
const cloud = {
  id: CLOUD_ID, revision: CLOUD_REVISION, name: 'e2e_annotation_cloud', kind: 'pointcloud3d',
  format: 'pcd-binary', file_name: 'e2e_annotation_cloud.pcd', frame_id: 'map',
  point_count: points.length / 3, source_points: points.length / 3, sent_points: points.length / 3,
  bounds: { min: [-5, -5, 0], max: [5, 5, 1] }, size_bytes: 32768, manageable: true,
  data_url: `/api/v1/saved-maps/${CLOUD_ID}/data`,
};

async function openEditor(page, { loadCloud = true } = {}) {
  const backend = await installDashboardBackend(page);
  const writes = [], pageErrors = [];
  page.on('request', (request) => { if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push({ method: request.method(), url: request.url() }); });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  backend.on('/api/v1/saved-maps', ({ json }) => json({ total_size_bytes: 36864, maps: [
    { id: backend.mapId, revision: backend.state.mapRevision, name: 'e2e_static_map', kind: 'occupancy2d', format: 'map-server-pgm', file_name: 'e2e_static_map.yaml', frame_id: 'map', width: 4, height: 4, resolution: 0.25, origin: [0, 0, 0], size_bytes: 4096, manageable: true, editable: true, data_url: `/api/v1/saved-maps/${backend.mapId}/data` },
    cloud,
  ] }));
  backend.on(`/api/v1/saved-maps/${CLOUD_ID}/data`, ({ json }) => json({ ...cloud, map_id: CLOUD_ID, seq: 1, points }));
  await page.goto('/#maps');
  await expect(page.locator('#mapEditorMode')).toBeVisible();
  if (loadCloud) {
    await page.locator('.saved-map-item').filter({ hasText: cloud.name }).click();
    await expect(page.locator('#savedMapTitle')).toContainText(cloud.name);
    await page.locator('#mapEditorMode').selectOption('3d');
    await page.locator('#map3Load').click();
    await expect(page.locator('#map3Stats')).toContainText(CLOUD_ID);
  }
  return { backend, writes, pageErrors };
}

async function selectPolygon(page, vertices = [[500, 320], [600, 320], [600, 220], [500, 220]]) {
  const canvas = page.locator('#map3Canvas');
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  for (const [x, y] of vertices) await page.mouse.click(box.x + x / 1100 * box.width, box.y + y / 540 * box.height);
}

async function exportVersion(page) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#map3Export').click()]);
  expect(download.suggestedFilename()).toMatch(/^map-annotations-edit-.+\.json$/);
  return JSON.parse(await readFile(await download.path(), 'utf8'));
}

async function importVersion(page, version) {
  await page.locator('#map3Import').setInputFiles({ name: 'annotations.json', mimeType: 'application/json', buffer: Buffer.from(typeof version === 'string' ? version : JSON.stringify(version)) });
}

test('one map editor panel switches modes and retains unsaved 2D and 3D drafts', async ({ page }, testInfo) => {
  const { writes, pageErrors } = await openEditor(page, { loadCloud: false });
  await expect(page.locator('.map-editor-panel')).toHaveCount(1);
  await expect(page.locator('#mapEditor2D')).toBeVisible(); await expect(page.locator('#mapEditor3D')).toBeHidden();
  await page.locator('.saved-map-item').filter({ hasText: 'e2e_static_map' }).click();
  await expect(page.locator('#mapEditorState')).toContainText('READY');
  await page.locator('#mapEditorRotationNumber').fill('27.5');
  await page.locator('#mapEditorMode').selectOption('3d');
  await expect(page.locator('#mapEditor2D')).toBeHidden(); await expect(page.locator('#mapEditor3D')).toBeVisible();
  await page.locator('#mapEditorMode').selectOption('2d');
  await expect(page.locator('#mapEditorRotationNumber')).toHaveValue('27.5');
  await expect(page.locator('#mapEditorSave')).toBeEnabled();
  await page.locator('.map-editor-panel').screenshot({ path: testInfo.outputPath('map-editor-2d.png') });
  await page.locator('#mapEditorReset').click();
  await page.locator('.saved-map-item').filter({ hasText: cloud.name }).click();
  await page.locator('#mapEditorMode').selectOption('3d'); await page.locator('#map3Load').click();
  await selectPolygon(page); await page.locator('#map3Add').click();
  await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await page.locator('#mapEditorMode').selectOption('2d'); await page.locator('#mapEditorMode').selectOption('3d');
  await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await page.locator('#map3Preview').check();
  await page.locator('.map-editor-panel').screenshot({ path: testInfo.outputPath('map-editor-3d.png') });
  expect(writes).toEqual([]); expect(pageErrors).toEqual([]);
});

test('3D polygon editing, height validation and history fail safely without server writes', async ({ page }) => {
  const { writes } = await openEditor(page);
  await expect(page.locator('#map3Add')).toBeDisabled();
  await selectPolygon(page);
  await page.locator('#map3ZMin').fill(''); await page.locator('#map3Add').click();
  await expect(page.locator('#map3Status')).toHaveAttribute('data-error', 'true'); await expect(page.locator('#map3Regions li')).toHaveCount(0);
  await page.locator('#map3ZMin').fill('3'); await page.locator('#map3ZMax').fill('1'); await page.locator('#map3Add').click();
  await expect(page.locator('#map3Status')).toContainText('z_min'); await expect(page.locator('#map3Regions li')).toHaveCount(0);
  await page.locator('#map3ZMin').fill('-1'); await page.locator('#map3ZMax').fill('1'); await page.locator('#map3Add').click();
  await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await page.locator('#map3Undo').click(); await expect(page.locator('#map3Regions li')).toHaveCount(0);
  await page.locator('#map3Redo').click(); await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await page.locator('#map3Reset').click(); await expect(page.locator('#map3Regions li')).toHaveCount(0);
  await page.locator('#map3Undo').click(); await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await selectPolygon(page, [[500, 320], [600, 220], [600, 320], [500, 220]]); await page.locator('#map3Add').click();
  await expect(page.locator('#map3Status')).toContainText('self-intersect'); await expect(page.locator('#map3Regions li')).toHaveCount(1);
  await page.locator('#map3Canvas').press('Escape'); await expect(page.locator('#map3Add')).toBeDisabled();
  expect(writes).toEqual([]);
});

test('3D annotations export/import local versioned proposals and reject incompatible files', async ({ page }) => {
  const { writes, pageErrors } = await openEditor(page);
  for (const kind of ['visibility', 'localization', 'keepout']) {
    await page.locator('#map3Kind').selectOption(kind); await selectPolygon(page); await page.locator('#map3Add').click();
  }
  await expect(page.locator('#map3Regions li')).toHaveCount(3);
  const version = await exportVersion(page);
  expect(version.source).toEqual({ map_id: CLOUD_ID, revision: CLOUD_REVISION, frame_id: 'map' });
  expect(version.runtime_installed).toBe(false); expect(version.regions.map((r) => r.kind)).toEqual(['visibility', 'localization', 'keepout']);
  expect(version).not.toHaveProperty('points');
  await page.locator('#map3Reset').click(); await expect(page.locator('#map3Regions li')).toHaveCount(0);
  await importVersion(page, version); await expect(page.locator('#map3Regions li')).toHaveCount(3);
  for (const bad of ['{', { ...version, schema_version: 999 }, { ...version, source: { ...version.source, revision: 'stale' } }, { ...version, runtime_installed: true }]) {
    await importVersion(page, bad); await expect(page.locator('#map3Status')).toHaveAttribute('data-error', 'true'); await expect(page.locator('#map3Regions li')).toHaveCount(3);
  }
  await page.locator('#map3Import').setInputFiles({ name: 'oversized.json', mimeType: 'application/json', buffer: Buffer.alloc(2 * 1024 * 1024 + 1, 32) });
  await expect(page.locator('#map3Status')).toContainText('2 MB'); await expect(page.locator('#map3Regions li')).toHaveCount(3);
  expect(writes).toEqual([]); expect(pageErrors).toEqual([]);
});

test('outside-course removal downloads an identified edited copy and keeps the original immutable', async ({ page }, testInfo) => {
  const { writes, pageErrors } = await openEditor(page);
  await page.locator('.map-editor-panel').screenshot({ path: testInfo.outputPath('map-editor-outside-before.png') });
  await page.locator('#map3Selection').selectOption('outside'); await selectPolygon(page); await page.locator('#map3Add').click();
  await page.locator('#map3Preview').check();
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#map3CopyExport').click()]);
  expect(download.suggestedFilename()).toMatch(/^edited-cloud-copy-edit-.+\.json$/);
  const copy = JSON.parse(await readFile(await download.path(), 'utf8'));
  expect(copy.schema).toBe('robot-dashboard.edited-cloud-copy'); expect(copy.source.map_id).toBe(CLOUD_ID);
  expect(copy.runtime_installed).toBe(false); expect(copy.preview_only).toBe(false); expect(copy.units).toBe('m');
  expect(copy.loaded_points).toBe(points.length / 3); expect(copy.output_points).toBeGreaterThan(0); expect(copy.output_points).toBeLessThan(copy.loaded_points);
  expect(copy.points.length).toBe(copy.output_points * 3); expect(copy.regions[0].selection).toBe('outside');
  await page.locator('.map-editor-panel').screenshot({ path: testInfo.outputPath('map-editor-outside-course.png') });
  await page.locator('#map3Undo').click(); await expect(page.locator('#map3Stats')).toContainText('숨김 0');
  expect(writes).toEqual([]); expect(pageErrors).toEqual([]);
});
