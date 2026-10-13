import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../robot_dashboard/static/features/resources/model.js', import.meta.url), 'utf8');
const model = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const sample = (timestamp, cpu = 20) => ({ timestamp_ms: timestamp, seq: timestamp, cpu: { percent: cpu, max_core_percent: 25 }, gpu: { percent: 30 }, memory: { percent: 40 }, sensors: { cameras: [], topics: [] } });

test('comparison windows never overlap a baseline or bridge an observation gap', () => {
  const history = Array.from({ length: 61 }, (_, i) => sample(i * 1000));
  const before = model.comparisonWindow(history.slice(0, 31));
  const after = model.comparisonWindow(history, before.at(-1).timestamp_ms);
  assert.equal(before.length, 31); assert.equal(after.length, 30);
  assert.ok(model.windowReady(before)); assert.ok(model.windowReady(after));
  assert.ok(after.every(row => row.timestamp_ms > before.at(-1).timestamp_ms));
  assert.equal(model.comparisonWindow([sample(0), sample(1000), sample(8000), sample(9000)]).length, 2);
  assert.equal(model.windowReady([sample(0), sample(1000)]), false);
});

test('missing measurements do not turn into zero or imply spare capacity', () => {
  const row = sample(1000); row.gpu.percent = null;
  assert.equal(model.format(null), '—'); assert.equal(model.mbps(null), null);
  assert.equal(model.guidance(row).known, false);
  assert.equal(model.summarize([row]).gpu.value, null);
});

test('single core load and stale sensor rates are distinguished from averages', () => {
  const row = sample(1000); row.cpu.max_core_percent = 95;
  row.sensors.cameras = [{ id: 'camera', label: 'Camera', state: 'stale', live: false, age_s: 8, receive_fps: 30 }];
  row.sensors.topics = [{ name: '/points', category: 'pointcloud', state: 'ok', age_s: 8, hz: 10 }];
  assert.equal(model.guidance(row).high, true);
  assert.match(model.guidance(row).rows[0], /CPU 코어/);
  assert.equal(model.measurements(row)['camera:camera'].value, null);
  assert.equal(model.measurements(row)['topic:/points'].value, null);
});

test('CSV includes sample data, sensor measurements, and safe settings annotations', () => {
  const csv = model.exportCsv([sample(1000)], [{ kind: 'change', timestamp_ms: 1500, note: '=HYPERLINK("malicious")' }]);
  assert.match(csv, /sensors_json/); assert.match(csv, /1970-01-01T00:00:01.000Z/);
  assert.match(csv, /'=HYPERLINK/);
  assert.equal(csv.split('\r\n').length, 3);
  assert.equal(model.csvCell('"a,b"'), '"""a,b"""');
});
