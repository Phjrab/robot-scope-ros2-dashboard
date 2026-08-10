import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const functionStart = appSource.indexOf('function hasFreshLaserMap()');
const functionEnd = appSource.indexOf('\nfunction mappingPipelineActive()', functionStart);
assert.ok(functionStart >= 0 && functionEnd > functionStart, 'map readiness function must be extractable');
const readinessSource = appSource.slice(functionStart, functionEnd);

function hasFreshLaserMap({ topics = [], state = {}, pipelineState = 'idle' } = {}) {
  return new Function(
    'latestTopics',
    'latestState',
    'mappingControlSnapshot',
    `${readinessSource}\nreturn hasFreshLaserMap();`,
  )(topics, state, { pipeline: { state: pipelineState } });
}

test('verified mapping pipeline can save while XT16 bridge cloud is selected for display', () => {
  assert.equal(hasFreshLaserMap({
    topics: [{ name: '/Laser_map', publishers: 1, state: 'waiting' }],
    state: {
      sources: { pointcloud: '/velodyne_points', odometry: '/Odometry' },
      mapping: { cloud: { state: 'ok' }, odometry: { state: 'ok' } },
    },
    pipelineState: 'running',
  }), true);
});

test('process startup alone never enables save before map readiness', () => {
  assert.equal(hasFreshLaserMap({
    topics: [{ name: '/Laser_map', publishers: 1, state: 'waiting' }],
    state: {
      sources: { pointcloud: '/velodyne_points', odometry: '/Odometry' },
      mapping: { cloud: { state: 'ok' }, odometry: { state: 'ok' } },
    },
    pipelineState: 'starting',
  }), false);
  assert.equal(hasFreshLaserMap({
    topics: [{ name: '/Laser_map', publishers: 1, state: 'ok' }],
    pipelineState: 'starting',
  }), false);
  assert.equal(hasFreshLaserMap({
    topics: [],
    pipelineState: 'running',
  }), false);
});

test('metered and externally started Laser_map readiness paths remain supported', () => {
  assert.equal(hasFreshLaserMap({
    topics: [{ name: '/Laser_map', publishers: 1, state: 'ok' }],
  }), true);
  assert.equal(hasFreshLaserMap({
    topics: [{ name: '/Laser_map', publishers: 1, state: 'waiting' }],
    state: {
      sources: { pointcloud: '/cloud_registered', odometry: '/Odometry' },
      mapping: { cloud: { state: 'ok' }, odometry: { state: 'ok' } },
    },
  }), true);
});
