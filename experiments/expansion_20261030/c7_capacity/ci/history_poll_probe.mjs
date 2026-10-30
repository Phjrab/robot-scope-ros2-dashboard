// Read-only reproduction of the shared history controller's poll/open race.
// This is diagnostic evidence, not a passing regression for the defective UI.
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const repo = resolve(process.argv[2] || '.');
const source = 'robot_dashboard/static/features/maps/global_observation_contract.js';
const { GlobalObservationController } = await import(pathToFileURL(resolve(repo, source)));
const root = '/api/v1/observations/global-jobs';
const id = 'd'.repeat(24);
const requests = [];
let release;
const gate = new Promise(resolve => { release = resolve; });
let notifications = 0;
const model = new GlobalObservationController({
  changed: () => { notifications++; },
  request: async path => {
    requests.push(path);
    if (path !== root) return new Response(JSON.stringify({ detail: 'synthetic job not found' }), { status: 404 });
    await gate;
    return new Response(JSON.stringify({
      schema: 'robot-scope.raw-global-observations.v1', generation: 1,
      provider: { available: true }, closed: false, active: null, latest: null,
      historical_only: true, current_result: null, body_pose: null,
      tracking_verified: false, body_pose_verified: false, body_extrinsic_verified: false,
      operational_application: 'NOT_RUN', absolute_accuracy_m: null,
    }));
  },
});
model.setMap({ id: 'a'.repeat(24), revision: 'b'.repeat(64), kind: 'pointcloud3d', frame_id: 'camera_init' }, { frame_id: 'camera_init' });
assert.equal(model.snapshot().canOpenHistorical, true);
const before = notifications;
const poll = model.poll();
const whilePolling = { reading: model.reading, canOpenHistorical: model.snapshot().canOpenHistorical,
  changedNotifications: notifications - before };
await model.openHistorical(id);
const during = { requests: [...requests], error: model.snapshot().error };
release();
await poll;
const afterPoll = { requests: [...requests], error: model.snapshot().error, canOpenHistorical: model.snapshot().canOpenHistorical };
await model.openHistorical(id);
const retry = { requests: [...requests], error: model.snapshot().error };
assert.equal(whilePolling.changedNotifications, 0);
assert.deepEqual(during.requests, [root]);
assert.equal(afterPoll.error, '');
assert.match(retry.error, /synthetic job not found/);
console.log(JSON.stringify({
  result: 'REPRODUCED_SHARED_POLL_OPEN_RACE', source,
  sha: execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  whilePolling, during, afterPoll, retry,
}, null, 2));
