import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COCKPIT_MAX_POINTS,
  COCKPIT_POINT_BUDGETS,
  createAdaptivePointBudgetController,
  createSpatialPointLod,
} from '../robot_dashboard/static/features/cockpit/point_quality.js';

function bandCloud(pointsPerBand = 1_000) {
  const points = new Float32Array(pointsPerBand * 9);
  let offset = 0;
  for (const radius of [2, 10, 25]) {
    for (let index = 0; index < pointsPerBand; index += 1) {
      points[offset++] = radius;
      points[offset++] = (index % 20) / 100;
      points[offset++] = index / pointsPerBand;
    }
  }
  return { seq: 1, points, prevalidated: true, source_points: pointsPerBand * 3 };
}

function retainedBands(points) {
  const counts = [0, 0, 0];
  for (let index = 0; index < points.length; index += 3) {
    const radius = Math.hypot(points[index], points[index + 1]);
    counts[radius < 5 ? 0 : radius < 15 ? 1 : 2] += 1;
  }
  return counts;
}

test('Cockpit spatial LOD keeps near-field density above medium and far density', () => {
  const lod = createSpatialPointLod();
  const projected = lod.project(bandCloud(), 1_000, true);
  const counts = retainedBands(projected.points);
  assert.equal(projected.sent_points, 1_000);
  assert.ok(counts[0] > counts[1]);
  assert.ok(counts[1] > counts[2]);
  assert.deepEqual(projected.cockpit_lod, { budget: 1_000, near_field: true });
});

test('Cockpit LOD enforces the 60K product ceiling and reuses two typed buffers', () => {
  const lod = createSpatialPointLod();
  const cloud = bandCloud(30_000);
  const first = lod.project(cloud, 1_000_000, false);
  const second = lod.project({ ...cloud, seq: 2 }, 50_000, false);
  const third = lod.project({ ...cloud, seq: 3 }, 40_000, false);
  assert.equal(first.points.length / 3, COCKPIT_MAX_POINTS);
  assert.equal(COCKPIT_POINT_BUDGETS.high, 60_000);
  assert.notStrictEqual(first.points.buffer, second.points.buffer);
  assert.strictEqual(first.points.buffer, third.points.buffer);
  assert.deepEqual(lod.diagnostics(), { capacity: 60_000, buffers: 2, allocations: 2, projections: 3 });
});

test('adaptive budget uses dwell and hysteresis to degrade quickly and recover slowly', () => {
  const controller = createAdaptivePointBudgetController({ minimumDwellMs: 3_000, recoveryDwellMs: 8_000 });
  controller.setCeiling('high', 0, true);
  const bad = { frameMs: 35, fps: 20, decodeMs: 12, uploadMs: 9 };
  controller.sample(bad, 3_000);
  assert.equal(controller.sample(bad, 3_100).level, 'medium');
  controller.sample(bad, 6_200);
  assert.equal(controller.sample(bad, 6_300).level, 'low');

  const good = { frameMs: 12, fps: 60, decodeMs: 2, uploadMs: 2 };
  for (let index = 0; index < 4; index += 1) controller.sample(good, 14_400 + index);
  assert.equal(controller.snapshot().level, 'low', 'recovery needs more consecutive samples than degradation');
  assert.equal(controller.sample(good, 14_500).level, 'medium');
  for (let index = 0; index < 5; index += 1) controller.sample(good, 22_600 + index);
  assert.equal(controller.snapshot().level, 'high');
});

test('adaptive mode treats dropped and stale input as bad without exceeding its ceiling', () => {
  const controller = createAdaptivePointBudgetController({ minimumDwellMs: 0, badSamplesRequired: 1 });
  controller.setCeiling('medium', 0, true);
  assert.equal(controller.sample({ droppedFrames: 2 }, 1).level, 'low');
  controller.setCeiling('medium', 2, true);
  assert.equal(controller.sample({ stale: true }, 3).level, 'low');
  assert.ok(controller.snapshot().budget <= COCKPIT_POINT_BUDGETS.medium);
});
