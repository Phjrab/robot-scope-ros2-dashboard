import assert from 'node:assert/strict';
import test from 'node:test';
import { OCCUPANCY_COLORS, occupancyClass, occupancyImage, drawOccupancyGrid, renderSavedOccupancyDetails } from '../robot_dashboard/static/features/maps/occupancy_display.js';

test('display palette flips rows and preserves input bytes and yaw-aware coordinates', () => {
  let rendered;
  const context = {
    createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
    putImageData: image => { rendered = image.data; },
    fillRect() {}, drawImage() {},
  };
  const document = { createElement: () => ({ getContext: () => context }) };
  const map = { width: 2, height: 2, data_b64: Buffer.from([255, 0, 100, 255]).toString('base64'), origin: [1, 2, Math.PI / 2], resolution: .5 };
  const before = JSON.stringify(map);
  assert.deepEqual(occupancyImage(map, document).counts, { occupied: 1, free: 1, unknown: 2 });
  assert.deepEqual([...rendered.slice(0, 3)], OCCUPANCY_COLORS.occupied);
  assert.deepEqual([...rendered.slice(12, 15)], OCCUPANCY_COLORS.free);
  assert.equal(occupancyClass(-1), 'unknown');
  globalThis.document = document;
  try {
    const { viewport } = drawOccupancyGrid(map, { getContext: () => context }, () => ({ width: 200, height: 200, ratio: 1 }));
    const point = viewport.projectWorld({ x: .5, y: 2.5, yaw: Math.PI / 2 });
    assert.equal(point.inside, true);
    assert.ok(Math.abs(point.x - 100) < 1e-8);
    assert.ok(Math.abs(point.y - 100) < 1e-8);
    assert.equal(point.heading, -0);
  } finally { delete globalThis.document; }
  assert.equal(JSON.stringify(map), before);
});

test('late lineage response cannot overwrite newly selected grid metadata', async () => {
  const host = { hidden: true, textContent: '' };
  globalThis.document = { getElementById: () => host };
  const map = id => ({ map_id: id, revision: id.repeat(64), width: 2, height: 2, resolution: .5, origin: [0, 0, 0], frame_id: 'map', data_b64: 'AAAAAA==' });
  const meta = data => ({ id: data.map_id, revision: data.revision, kind: 'occupancy2d' });
  const a = map('a'), b = map('b');
  let release;
  const api = async path => path.includes('/a/') ? new Promise(resolve => { release = resolve; }) :
    { map_id: b.map_id, map_revision: b.revision, families: [] };
  try {
    renderSavedOccupancyDetails(meta(a), a, api);
    renderSavedOccupancyDetails(meta(b), b, api);
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(host.textContent.startsWith('ID b'));
    release({ map_id: a.map_id, map_revision: a.revision, families: [] });
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(host.textContent.startsWith('ID b'));
    renderSavedOccupancyDetails({ id: 'c', kind: 'occupancy2d' }, null, api);
    assert.equal(host.textContent, '선택한 2D 지도 확인 중');
  } finally { delete globalThis.document; }
});
