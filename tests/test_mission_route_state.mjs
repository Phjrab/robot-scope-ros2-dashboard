import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createDraftStore, newVisit, resolvedTarget, headingToNext, worldToGrid, gridToWorld } from '../robot_dashboard/static/features/mission_route/state.js';
import { createPlanClient } from '../robot_dashboard/static/features/mission_route/client.js';
const definition = () => ({ label: '초안', visits: [newVisit({x:2,y:3,yaw:0}, '같은 지점'), newVisit({x:2,y:3,yaw:1}, '같은 지점')] });

test('MR repeated visits, reorder, duplicate and undo preserve semantic IDs', () => {
  const store = createDraftStore(); store.fresh(definition()); const first = store.snapshot();
  assert.notEqual(first.draft.visits[0].visit_id, first.draft.visits[1].visit_id);
  store.select(first.draft.visits[1].visit_id); store.move(-1); assert.equal(store.snapshot().draft.visits[0].visit_id, first.draft.visits[1].visit_id);
  store.duplicate(); assert.equal(store.snapshot().draft.visits.length, 3);
  store.undo(); assert.equal(store.snapshot().draft.visits.length, 2);
});
test('MR polling cannot overwrite dirty input and late preview is rejected', () => {
  const store = createDraftStore(); store.fresh(definition()); const generation = store.snapshot().generation;
  store.edit((d) => { d.label = '입력 중인 이름'; }); store.poll({label:'서버 이름'});
  assert.equal(store.snapshot().draft.label, '입력 중인 이름');
  assert.equal(store.applyPreview({actual_nav2_run:true}, generation), false);
  assert.equal(store.snapshot().preview, null);
});
test('MR map coordinate helpers roundtrip translated rotated maps', () => {
  const map = { origin:[3,-2,Math.PI/3],width:300,height:200,resolution:.05 };
  const expected = {x:34,y:120}; const world = gridToWorld(map,expected.x,expected.y); const grid = worldToGrid(map,world);
  assert.ok(Math.abs(grid.x-expected.x)<1e-9); assert.ok(Math.abs(grid.y-expected.y)<1e-9);
});
test('MR plan reads and compile cannot call a navigation mutation endpoint', async () => {
  const calls=[]; const client=createPlanClient(async (url,options) => { calls.push({url,options}); return {ok:true,json:async()=>({})}; });
  const entry={id:'a'.repeat(32),revision:'b'.repeat(64)};
  await client.list(); await client.compile(entry); await client.preview(entry,{x:1,y:2,yaw:0});
  assert.ok(calls.every((c)=>!c.url.includes('/navigation')&&!c.url.includes('/start')));
  assert.equal(JSON.parse(calls[2].options.body).start_source,'hypothetical_preview_start');
});
test('MR explicit mutation retry can retain original request ID', async()=> {
  const keys=[]; const client=createPlanClient(async(url,options)=>{ keys.push(JSON.parse(options.body).request_id); return {ok:true,json:async()=>({})}; });
  await client.action('a'.repeat(32),'resume','b'.repeat(32),'same-request-0001');
  await client.action('a'.repeat(32),'resume','b'.repeat(32),'same-request-0001');
  assert.deepEqual(keys,['same-request-0001','same-request-0001']);
});

test('MR delayed save commits only the submitted version and keeps newer edits for CAS', () => {
  const store = createDraftStore(); store.fresh(definition());
  const submitted = store.snapshot();
  store.select(submitted.draft.visits[1].visit_id);
  store.edit((draft) => { draft.label = '응답 대기 중 입력'; draft.visits[1].hold_seconds = 4.5; });
  const committed = { id: 'a'.repeat(32), revision: 'c'.repeat(64), definition: submitted.draft };
  assert.equal(store.acceptSave(committed, submitted.generation), false);
  const next = store.snapshot();
  assert.equal(next.draft.label, '응답 대기 중 입력');
  assert.equal(next.draft.visits[1].hold_seconds, 4.5);
  assert.equal(next.saved.revision, committed.revision);
  assert.equal(next.selected, submitted.draft.visits[1].visit_id);
  assert.equal(next.dirty, true);
  assert.equal(store.acceptSave({ ...committed, definition: next.draft }, next.generation), true);
  assert.equal(store.snapshot().dirty, false);
});

test('MR reload restores only the edit snapshot and invalidates old preview', () => {
  let persisted;
  const source = createDraftStore((value) => { persisted = value; }); source.fresh(definition());
  source.select(source.snapshot().draft.visits[1].visit_id);
  source.update({ after_arrival_confirmation: true });
  source.applyPreview({ actual_nav2_run: true }, source.snapshot().generation);
  const reloaded = createDraftStore(); assert.equal(reloaded.restore(persisted), true);
  assert.equal(reloaded.snapshot().dirty, true);
  assert.equal(reloaded.snapshot().draft.visits[1].after_arrival_confirmation, true);
  assert.equal(reloaded.snapshot().selected, persisted.selected);
  assert.equal(reloaded.snapshot().preview, null);
  assert.equal(reloaded.restore({ draft: { label: 'bad', visits: [{ visit_id: '<script>' }] } }), false);
});

test('MR annotation heading override is per visit and next heading uses resolved positions', () => {
  const annotation = { id: 'a'.repeat(24), pose: { x: 2, y: 3, yaw: 0.4 } };
  const visit = { ...newVisit(annotation.pose), pose: null, target: 'annotation_ref', annotation_id: annotation.id };
  const next = newVisit({ x: 2, y: 5, yaw: -1 });
  assert.equal(resolvedTarget(visit, { points: [annotation] }).yaw, 0.4);
  assert.equal(resolvedTarget({ ...visit, heading_yaw: -0.8 }, { points: [annotation] }).yaw, -0.8);
  assert.equal(annotation.pose.yaw, 0.4);
  assert.equal(headingToNext([visit, next], visit.visit_id, { points: [annotation] }), Math.PI / 2);
  assert.equal(headingToNext([visit, next], next.visit_id, { points: [annotation] }), null);
  assert.equal(headingToNext([visit, { ...next, pose: annotation.pose }], visit.visit_id, { points: [annotation] }), null);
});

test('MR delete is revision pinned and export is a read-only request', async () => {
  const calls = []; const client = createPlanClient(async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({}) }; });
  const entry = { id: 'a'.repeat(32), revision: 'b'.repeat(64) };
  await client.remove(entry); await client.exportRun(entry.id); await client.run(entry.id);
  assert.equal(calls[0].options.method, 'DELETE'); assert.equal(JSON.parse(calls[0].options.body).revision, entry.revision);
  assert.equal(calls[1].url, `/api/v1/mission-runs/${entry.id}/export`); assert.equal(calls[1].options.body, undefined);
  assert.equal(calls[2].url, `/api/v1/mission-runs/${entry.id}`);
});

test('MR server rejection retains HTTP status so it is not confused with uncertain transport', async () => {
  const client = createPlanClient(async () => ({ ok: false, status: 409, json: async () => ({ detail: 'DEFINITION_ACTIVE_COPY_REQUIRED' }) }));
  await assert.rejects(client.list(), (error) => error.status === 409 && error.message === 'DEFINITION_ACTIVE_COPY_REQUIRED');
});

test('MR one drag is one undo transaction and cancel restores its initial pose', () => {
  const store = createDraftStore(); store.fresh(definition()); const selected = store.snapshot().draft.visits[0];
  store.beginEdit(); for (let x=3;x<12;x++) store.update({pose:{...selected.pose,x}}); store.endEdit();
  assert.equal(store.snapshot().draft.visits[0].pose.x,11); store.undo(); assert.deepEqual(store.snapshot().draft.visits[0].pose,selected.pose);
  store.beginEdit(); store.update({pose:{...selected.pose,x:20}}); store.endEdit(true); assert.deepEqual(store.snapshot().draft.visits[0].pose,selected.pose);
});
