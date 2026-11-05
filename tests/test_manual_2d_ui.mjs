import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const html = readFileSync('robot_dashboard/static/index.html', 'utf8');
const shell = readFileSync('robot_dashboard/static/features/cockpit/mission_shell.js', 'utf8');
const app = readFileSync('robot_dashboard/static/app.js', 'utf8');
const feature = readFileSync('robot_dashboard/static/features/experiments/manual_2d/index.js', 'utf8');
test('manual 2D experiment has a real route and explicit controls', () => {
  assert.match(html, /href="#experiments" data-nav="experiments"/);
  assert.match(html, /data-page="experiments"/);
  assert.match(shell, /experiments: \[/);
  for (const name of ['map', 'site', 'prepare', 'initial', 'goal', 'send', 'annotation', 'cancel', 'stop']) assert.match(html, new RegExp(`data-manual="${name}"`));
  assert.match(html, /MANUAL_SEEDED_ODOMETRY/);
});
test('manual commands use existing navigation API with session and seed bindings', () => {
  for (const path of ['/start', '/initial-pose', '/goal', '/goal/annotation', '/cancel', '/stop']) assert.ok(feature.includes(`/api/v1/navigation${path}`));
  assert.match(feature, /mode: 'manual_seeded_2d'/);
  assert.match(feature, /body\.seed_generation = nav\.manual_seed\.seed_generation/);
  assert.match(feature, /job_id: jobId\(nav\)/);
  assert.match(feature, /seed\.state === 'ready_manual'/);
  assert.match(app, /navigationSnapshot\?\.mode === 'manual_seeded_2d'\) return false/);
});
