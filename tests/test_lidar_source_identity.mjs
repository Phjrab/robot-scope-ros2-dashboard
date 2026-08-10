import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
const stylesSource = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

const identityStart = appSource.indexOf('const LidarSourceIdentity = (() => {');
const identityEndMarker = '\n})();\n\n// Exposed for the lightweight Node contract test';
const identityEnd = appSource.indexOf(identityEndMarker, identityStart);
assert.ok(identityStart >= 0 && identityEnd > identityStart, 'LiDAR identity implementation must be extractable');
const sandbox = {};
runInNewContext(
  `${appSource.slice(identityStart, identityEnd + '\n})();'.length)}\nglobalThis.identity = LidarSourceIdentity;`,
  sandbox,
);
const identity = sandbox.identity;

test('exact topic fallback never presents the Go2 deskewed cloud as XT16', () => {
  const deskewed = identity.describe('/utlidar/cloud_deskewed');
  assert.equal(deskewed.sensorId, 'go2_builtin_lidar');
  assert.equal(deskewed.sensorLabel, 'GO2 BUILT-IN LIDAR');
  assert.equal(deskewed.stage, 'deskewed');
  assert.match(deskewed.stageLabel, /^보정 · DESKEWED$/);

  const lookalike = identity.describe('/customer/cloud_deskewed');
  assert.equal(lookalike.sensorId, 'generic_pointcloud');
  assert.equal(lookalike.stage, 'unknown');

  const heightMap = identity.describe('/utlidar/height_map');
  assert.equal(heightMap.sensorId, 'go2_builtin_lidar');
  assert.equal(heightMap.stageLabel, '센서 맵 · HEIGHT MAP');
});

test('allowlisted XT16 and FAST-LIO stages receive explicit labels', () => {
  const raw = identity.describe('/lidar_points');
  assert.equal(raw.sensorLabel, 'HESAI XT16');
  assert.equal(raw.stageLabel, '원본 · RAW');

  const registered = identity.describe('/cloud_registered');
  assert.equal(registered.sensorLabel, 'HESAI XT16');
  assert.equal(registered.stage, 'registered');
  assert.equal(registered.stageLabel, 'FAST-LIO · REGISTERED');
});

test('backend source metadata takes precedence and preserves its processing label', () => {
  const described = identity.describe('/utlidar/cloud_deskewed', {
    sensor_id: 'hesai_xt16',
    sensor_label: 'Hesai XT16',
    pipeline_stage: 'registered',
    pipeline_stage_label: 'Registered cloud',
  });
  assert.equal(described.metadataPresent, true);
  assert.equal(described.sensorLabel, 'HESAI XT16');
  assert.equal(described.stage, 'registered');
  assert.equal(described.stageLabel, 'FAST-LIO · REGISTERED CLOUD');
});

test('freshness vocabulary is limited to LIVE, WAITING and STALE', () => {
  assert.equal(identity.normalizeReportedStatus('ok'), 'LIVE');
  assert.equal(identity.normalizeReportedStatus('streaming'), 'LIVE');
  assert.equal(identity.normalizeReportedStatus('waiting'), 'WAITING');
  assert.equal(identity.normalizeReportedStatus('timeout'), 'STALE');
});

test('settings and Live Mapping always expose sensor, topic, stage and freshness readouts', () => {
  for (const id of [
    'cloudSourceSensorBadge', 'cloudSourcePin', 'cloudSourceTopicLabel', 'cloudSourceStageLabel', 'cloudSourceFreshness',
    'mappingLidarSensorBadge', 'mappingLidarPin', 'mappingLidarTopic', 'mappingLidarStage', 'mappingLidarFreshness',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  assert.match(indexSource, /id="cloudSourceFreshness">WAITING<\/span>/);
  assert.match(indexSource, /id="mappingLidarFreshness">WAITING<\/span>/);
  assert.match(appSource, /document\.createElement\('optgroup'\)/);
  assert.match(appSource, /\['GO2 BUILT-IN LIDAR', 'HESAI XT16'\]/);
  assert.match(appSource, /renderLidarSourceIdentity\('STALE'\)/);
  assert.match(stylesSource, /\.lidar-source-freshness\.live/);
  assert.match(stylesSource, /\.lidar-source-freshness\.stale/);
  assert.match(stylesSource, /\.lidar-source-pin\.default-pin/);
});

const pinStart = appSource.indexOf('function lidarSourcePinInfo(');
const freshnessEnd = appSource.indexOf('\nfunction renderLidarSourceReadout(', pinStart);
assert.ok(pinStart >= 0 && freshnessEnd > pinStart, 'pin and freshness implementation must be extractable');
const pinAndFreshnessSource = appSource.slice(pinStart, freshnessEnd);

function sourceReadout(topic, catalogEntry, selection, latestState, latestTopics) {
  return new Function(
    'LidarSourceIdentity', 'pointcloudSelection', 'lastCloudSnapshot', 'pointcloudLastFrameAt',
    'latestState', 'latestTopics', 'topic', 'catalogEntry',
    `function pointcloudTransportWanted() { return true; }\n${pinAndFreshnessSource}\nreturn { pin: lidarSourcePinInfo(topic, catalogEntry), freshness: lidarSourceFreshness(topic, catalogEntry) };`,
  )(
    identity, selection, { topic, offline_snapshot: false }, 1,
    latestState, latestTopics, topic, catalogEntry,
  );
}

test('profile and operator LiDAR pins receive explicit badges', () => {
  const catalogEntry = { metadata: { pinned: true, publishers: 0, selection_origin: 'profile_default' } };
  const defaultPin = sourceReadout(
    '/velodyne_points', catalogEntry,
    { mode: 'pinned', requested: '/velodyne_points', origin: 'profile_default' },
    {}, [],
  ).pin;
  assert.equal(defaultPin.label, 'DEFAULT PIN');
  assert.equal(defaultPin.defaultPin, true);

  const userPin = sourceReadout(
    '/velodyne_points', catalogEntry,
    { mode: 'pinned', requested: '/velodyne_points', origin: 'user' },
    {}, [],
  ).pin;
  assert.equal(userPin.label, 'PINNED');
  assert.equal(userPin.defaultPin, false);
});

test('publisher-zero XT16 pin stays selected and reports WAITING instead of cached STALE', () => {
  const readout = sourceReadout(
    '/velodyne_points',
    { metadata: { pinned: true, publishers: 0, state: 'waiting', selection_origin: 'profile_default' } },
    { mode: 'pinned', requested: '/velodyne_points', origin: 'profile_default', fail_closed: true },
    {
      sources: { pointcloud: '/velodyne_points' },
      cloud: { state: 'stale' },
      mapping: { cloud: { state: 'stale' } },
    },
    [{ name: '/velodyne_points', publishers: 0, state: 'stale', age_s: 30 }],
  );
  assert.equal(identity.describe('/velodyne_points').sensorLabel, 'HESAI XT16');
  assert.equal(readout.pin.label, 'DEFAULT PIN');
  assert.equal(readout.freshness, 'WAITING');
});
