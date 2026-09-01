import assert from 'node:assert/strict';
import test from 'node:test';

import { createCameraDemandController } from '../robot_dashboard/static/features/sensors/camera_demand.js';

const CATALOG = [
  { id: 'go2_front', label: 'GO2 FRONT', available: true, state: 'ok', fps: 15, transport: 'raw' },
  { id: 'realsense_color', label: 'REALSENSE COLOR', available: true, state: 'ok', fps: 30, transport: 'raw' },
];

test('camera demand shares one source owner and releases only the exact consumer token', () => {
  const transitions = [];
  const controller = createCameraDemandController({
    onDemandChange: (sourceId, demanded) => transitions.push([sourceId, demanded]),
  });
  controller.updateCatalog(CATALOG);
  const first = controller.acquire('go2_front');
  const second = controller.acquire('go2_front');

  assert.deepEqual(transitions, [['go2_front', true]]);
  assert.equal(controller.sourceSnapshot('go2_front').viewerCount, 2);
  assert.equal(first.release(), true);
  assert.equal(first.release(), false);
  assert.equal(controller.sourceSnapshot('go2_front').viewerCount, 1);
  assert.deepEqual(transitions, [['go2_front', true]]);
  assert.equal(controller.release('not-a-token'), false);
  assert.equal(second.release(), true);
  assert.deepEqual(transitions, [['go2_front', true], ['go2_front', false]]);
});

test('camera demand rejects stale generation metadata and frames', () => {
  const frames = [];
  const controller = createCameraDemandController();
  controller.updateCatalog(CATALOG);
  controller.acquire('go2_front', { onFrame: (frame) => frames.push(frame) });

  assert.equal(controller.beginGeneration('go2_front', 7), true);
  assert.equal(controller.publishMetadata('go2_front', 7, { width: 640, height: 480 }), true);
  assert.equal(controller.publishFrame('go2_front', 7, { canvas: {}, width: 640, height: 480, lastFrameAt: 1000 }), true);
  assert.equal(controller.beginGeneration('go2_front', 8), true);
  assert.equal(controller.publishMetadata('go2_front', 7, { width: 1, height: 1 }), false);
  assert.equal(controller.publishFrame('go2_front', 7, { canvas: {}, width: 1, height: 1, lastFrameAt: 2000 }), false);
  assert.equal(frames.length, 1);
  assert.equal(controller.sourceSnapshot('go2_front').generation, 8);
  assert.equal(controller.sourceSnapshot('go2_front').metadata, null);
});

test('camera metadata refresh does not demote a live generation to waiting', () => {
  const connections = [];
  const controller = createCameraDemandController();
  controller.updateCatalog(CATALOG);
  controller.acquire('go2_front', {
    onState: (source) => connections.push(source.connection),
  });

  controller.beginGeneration('go2_front', 4);
  controller.publishMetadata('go2_front', 4, { width: 640, height: 480, seq: 1 });
  controller.publishFrame('go2_front', 4, { canvas: {}, width: 640, height: 480, lastFrameAt: 1_000 });
  controller.publishMetadata('go2_front', 4, { width: 640, height: 480, seq: 2 });

  assert.equal(controller.sourceSnapshot('go2_front').connection, 'live');
  assert.deepEqual(connections.slice(-2), ['live', 'live']);
});

test('camera catalog allowlist keeps unavailable profiles disabled and sources independent', () => {
  const controller = createCameraDemandController();
  controller.updateCatalog([CATALOG[0], { id: 'arbitrary_url', available: true }]);
  assert.equal(controller.sourceSnapshot('go2_front').available, true);
  assert.equal(controller.sourceSnapshot('realsense_color').available, false);
  assert.equal(controller.snapshot().sources.some((source) => source.id === 'arbitrary_url'), false);
  assert.throws(() => controller.acquire('arbitrary_url'), /not allowlisted/);

  controller.beginGeneration('go2_front', 1);
  controller.publishFrame('go2_front', 1, { canvas: {}, lastFrameAt: 1000 });
  controller.beginGeneration('realsense_color', 2);
  controller.endGeneration('realsense_color', 2, 'error', 'camera failed');
  assert.equal(controller.sourceSnapshot('go2_front').connection, 'live');
  assert.equal(controller.sourceSnapshot('realsense_color').connection, 'error');
});
