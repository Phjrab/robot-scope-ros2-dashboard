import assert from 'node:assert/strict';
import test from 'node:test';

import { CAMERA_PANEL_STALE_MS, createCameraPanel, projectCameraPanelState } from '../robot_dashboard/static/features/cockpit/panels/camera_panel.js';

test('camera panel projection replaces an aged frame with an explicit stale overlay', () => {
  const source = {
    connection: 'live', state: 'ok', transport: 'raw',
    metadata: { width: 640, height: 480, fps: 15, state: 'ok', transport: 'raw' },
  };
  const live = projectCameraPanelState(source, 10_000, 10_500);
  assert.equal(live.state, 'LIVE');
  assert.equal(live.overlay, '');
  assert.equal(live.resolution, '640×480');
  const stale = projectCameraPanelState(source, 10_000, 10_000 + CAMERA_PANEL_STALE_MS + 1);
  assert.equal(stale.state, 'STALE');
  assert.match(stale.overlay, /^STALE/);
  assert.equal(projectCameraPanelState({ ...source, metadata: { ...source.metadata, age_s: 4 } }, 10_000, 10_100).state, 'STALE');
  const error = projectCameraPanelState({ ...source, error: 'decode failed' }, 10_000, 10_100);
  assert.equal(error.state, 'ERROR');
  assert.equal(error.reconnect, 'ERROR');
});

test('camera panel activation and compact deactivation acquire and release exact demand', () => {
  let consumer = null;
  let releaseCount = 0;
  let intervalCount = 0;
  let clearCount = 0;
  const rendered = [];
  const view = {
    render: (state) => rendered.push(state),
    renderFrame: () => true,
    clearFrame: () => { clearCount += 1; },
    destroy: () => {},
  };
  const demand = {
    sourceSnapshot: () => ({ id: 'go2_front', available: true, connection: 'waiting' }),
    acquire(sourceId, callbacks) {
      assert.equal(sourceId, 'go2_front');
      consumer = callbacks;
      return { release: () => { releaseCount += 1; return true; } };
    },
  };
  const panel = createCameraPanel({
    descriptor: { sourceId: 'go2_front', label: 'Go2 Front Camera' },
    cameraDemand: demand,
    viewFactory: () => view,
    now: () => 1_000,
    setInterval: () => { intervalCount += 1; return 17; },
    clearInterval: (id) => { assert.equal(id, 17); },
  });

  panel.mount({});
  panel.activate();
  panel.activate();
  assert.equal(intervalCount, 1);
  consumer.onFrame({ canvas: {}, width: 320, height: 240, lastFrameAt: 900, source: { connection: 'live', state: 'ok' } });
  assert.equal(panel.diagnostics().renders, 1);
  panel.deactivate();
  panel.deactivate();
  assert.equal(releaseCount, 1);
  assert.equal(clearCount, 1);
  assert.equal(panel.diagnostics().demand, false);
  assert.equal(rendered.at(-1).state, 'WAITING');
  panel.activate();
  panel.destroy();
  assert.equal(releaseCount, 2);
});

test('camera panel implementation owns no socket or decoder transport', async () => {
  const source = await import('node:fs/promises').then((fs) => fs.readFile(new URL('../robot_dashboard/static/features/cockpit/panels/camera_panel.js', import.meta.url), 'utf8'));
  assert.doesNotMatch(source, /new\s+WebSocket|VideoDecoder|fetch\s*\(/);
  assert.doesNotMatch(source, /dataset|capture/i);
});
