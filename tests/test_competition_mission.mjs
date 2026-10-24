import assert from 'node:assert/strict';
import test from 'node:test';
import {createDraftStore, newVisit} from '../robot_dashboard/static/features/mission_route/state.js';
import {nativeBlockers, pathEvidence, observationText} from '../robot_dashboard/static/features/mission_route/competition.js';
test('competition duplicate visits get fresh action identity and keep zone reference',()=>{
  const s=createDraftStore(), v={...newVisit({x:1,y:2,yaw:0}),mission_action:{step_id:'a'.repeat(32),type:'TRAFFIC_STOP_AND_GO',zone_id:'same-zone'}};
  s.fresh({visits:[v]}); s.duplicate(); const visits=s.snapshot().draft.visits;
  assert.notEqual(visits[0].visit_id,visits[1].visit_id); assert.notEqual(visits[0].mission_action.step_id,visits[1].mission_action.step_id);
  assert.equal(visits[0].mission_action.zone_id,visits[1].mission_action.zone_id);
});
test('fixture path cannot claim native based on boolean alone',()=>{
  assert.equal(pathEvidence({actual_nav2_run:true,evidence_type:'synthetic'}),'fixture');
  assert.equal(pathEvidence({actual_nav2_run:true,scope:'synthetic_ui_fixture'}),'fixture');
  assert.equal(pathEvidence({actual_nav2_run:true,evidence_type:'native_planner'}),'native');
  assert.equal(pathEvidence(null),'unavailable');
});
test('missing adapter remains explicit and browser only displays server dwell',()=>{
  assert.match(nativeBlockers({competition:{},visits:[{label:'신호',mission_action:{type:'TRAFFIC_STOP_AND_GO'}}]},null)[0],/UNCONNECTED/);
  assert.match(observationText({dwell_elapsed_s:1.25}),/1.25s/);
  assert.match(observationText(null),/관측 없음/);
});

import {readFileSync} from 'node:fs';
import {decodeArenaGLB} from '../robot_dashboard/static/features/mission_route/arena_preview.js';
test('published GLB is decoded from its actual geometry with bounded finite vertices',()=>{
  const bytes=readFileSync(new URL('../assets/competition-arena/revisions/rulebook-20261015/arena.glb',import.meta.url));
  const triangles=decodeArenaGLB(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  assert.ok(triangles.length>100); assert.ok(triangles.length<50000);
  assert.ok(triangles.every(t=>t.vertices.flat().every(Number.isFinite)));
  assert.throws(()=>decodeArenaGLB(new ArrayBuffer(32)),/Invalid GLB/);
});
