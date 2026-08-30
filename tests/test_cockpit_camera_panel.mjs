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
  assert.match(live.wifi, /^UNVERIFIED/);
  assert.match(live.source, /^UNVERIFIED/);
  assert.match(live.receive, /Mb/);
  assert.match(live.decode, /^OK 0 · FAIL 0 · DROP 0 · Q0$/);
  assert.equal(live.clock, 'UNVERIFIED_CLOCK_DOMAIN');
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

test('camera panel projects relay, transport and browser decode observability', () => {
  const projected = projectCameraPanelState({
    connection: 'live',
    state: 'ok',
    metadata: {
      state: 'ok',
      receive_fps: 14.8,
      receive_bitrate_mbps: 4.125,
      cross_host_latency_state: 'UNVERIFIED_CLOCK_DOMAIN',
      relay_health: {
        state: 'streaming',
        fps: 15,
        last_frame_age_s: 0.12,
        wifi: { state: 'LIVE', rssi_dbm: -54, link_mbps: 433.3 },
      },
      browser_decode: {
        decodedFrames: 20,
        decodeFailures: 1,
        supersededFrames: 3,
        queueDepth: 1,
      },
    },
  }, 10_000, 10_100);
  assert.match(projected.wifi, /LIVE · RSSI -54 dBm · LINK 433\.3 Mbps/);
  assert.match(projected.source, /LIVE · 15\.0 FPS · AGE 0\.12s/);
  assert.equal(projected.receive, '4.125 Mbps · 14.8 FPS · R0');
  assert.equal(projected.decode, 'OK 20 · FAIL 1 · DROP 3 · Q1');
  assert.equal(projected.clock, 'UNVERIFIED_CLOCK_DOMAIN');
});
