import assert from 'node:assert/strict';
import test from 'node:test';

import {
  cascadePanelLayout,
  dockPanelGeometry,
  snapPanelGeometry,
  splitPanelLayout,
  tilePanelLayout,
} from '../robot_dashboard/static/features/cockpit/snap_layout.js';

const viewport = { width: 1000, height: 700, padding: 12, reservedBottom: 78 };
const bounds = { minWidth: 250, minHeight: 150, maxWidth: 760, maxHeight: 600, compactWidth: 280, compactHeight: 58 };

test('snap geometry prefers nearby viewport and panel edges and supports an Alt bypass', () => {
  const edge = snapPanelGeometry({ x: 19, y: 18, width: 300, height: 200 }, viewport, [], { bounds, threshold: 14, gridSize: 16 });
  assert.deepEqual({ x: edge.geometry.x, y: edge.geometry.y }, { x: 12, y: 12 });
  assert.match(edge.preview.kind, /viewport-left/);

  const peer = { id: 'map', visible: true, mode: 'floating', x: 500, y: 180, width: 320, height: 240 };
  const panel = snapPanelGeometry({ x: 188, y: 183, width: 300, height: 200 }, viewport, [peer], { bounds, threshold: 14, gridSize: 16 });
  assert.equal(panel.geometry.x, 200, 'moving panel right edge must snap to the peer left edge');
  assert.equal(panel.geometry.y, 180, 'panel top edges must align');

  const bypassed = snapPanelGeometry({ x: 19, y: 18, width: 300, height: 200 }, viewport, [], { bounds, disabled: true });
  assert.deepEqual({ x: bypassed.geometry.x, y: bypassed.geometry.y, preview: bypassed.preview }, { x: 19, y: 18, preview: null });
});

test('grid snap is configurable when no edge candidate wins', () => {
  const snapped = snapPanelGeometry({ x: 109, y: 111, width: 300, height: 200 }, viewport, [], { bounds, threshold: 2, gridSize: 24 });
  assert.deepEqual({ x: snapped.geometry.x, y: snapped.geometry.y }, { x: 108, y: 108 });
  assert.equal(snapped.preview.kind, 'grid');
});

test('four-way dock uses half layouts and small viewports fall back to compact', () => {
  const left = dockPanelGeometry('left', viewport, bounds, { x: 50, y: 60, width: 330, height: 220 });
  assert.deepEqual(left, {
    mode: 'floating', dock: 'left', geometry: { x: 12, y: 12, width: 488, height: 598 },
  });
  const bottom = dockPanelGeometry('bottom', viewport, bounds, {});
  assert.deepEqual(bottom.geometry, { x: 12, y: 311, width: 976, height: 299 });
  const tiny = dockPanelGeometry('left', { width: 420, height: 320, padding: 12, reservedBottom: 78 }, bounds, { x: 20, y: 20, width: 320, height: 220 });
  assert.equal(tiny.mode, 'compact');
  assert.equal(tiny.dock, null);
  assert.ok(tiny.geometry.width >= 250);
});

function entries(count = 4) {
  return Array.from({ length: count }, (_, index) => ({
    id: `panel-${index}`,
    geometry: { x: 20 + index * 40, y: 30 + index * 30, width: 320, height: 220 },
    bounds,
  }));
}

test('50:50, 2x2 tile, and cascade layouts stay deterministic and inside the viewport', () => {
  const split = splitPanelLayout(entries(3), viewport);
  assert.equal(split.length, 2);
  assert.deepEqual(split.map((item) => item.dock), ['left', 'right']);
  assert.equal(split[0].geometry.width, split[1].geometry.width);

  const tile = tilePanelLayout(entries(), viewport);
  assert.equal(tile.length, 4);
  assert.equal(new Set(tile.map((item) => `${item.geometry.x}:${item.geometry.y}`)).size, 4);

  const cascade = cascadePanelLayout(entries(3), viewport);
  assert.equal(cascade.length, 3);
  for (const layout of [...tile, ...cascade]) {
    assert.ok(layout.geometry.x >= 12 && layout.geometry.y >= 12);
    assert.ok(layout.geometry.x + layout.geometry.width <= 988);
    assert.ok(layout.geometry.y + layout.geometry.height <= 610);
  }
});

test('tile layout compacts panels instead of forcing them below minimum size', () => {
  const compact = tilePanelLayout(entries(), { width: 500, height: 420, padding: 12, reservedBottom: 78 });
  assert.ok(compact.every((item) => item.mode === 'compact' && item.dock === null));
  assert.ok(compact.every((item) => item.geometry.width >= bounds.minWidth));
});
