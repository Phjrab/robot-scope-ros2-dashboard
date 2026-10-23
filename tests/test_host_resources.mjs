import test from 'node:test';
import assert from 'node:assert/strict';
import { percent, capacity, sparkline } from '../robot_dashboard/static/host_resources.mjs';

test('missing metrics never become measured zero', () => {
  for (const value of [null, undefined, NaN, Infinity, -1, '0']) {
    assert.equal(percent(value), 'N/A');
    assert.equal(capacity(value), 'N/A');
  }
  assert.equal(percent(0), '0.0%');
  assert.equal(capacity(1073741824), '1.0 GiB');
});

test('sparkline breaks across unavailable samples and rejects malformed history', () => {
  const path = sparkline([{cpu_percent: 20}, {cpu_percent: null}, {cpu_percent: 40}], 'cpu_percent');
  assert.equal((path.match(/M/g) || []).length, 2);
  assert.equal(path.includes('L'), false);
  assert.equal(sparkline(null, 'cpu_percent'), '');
});
