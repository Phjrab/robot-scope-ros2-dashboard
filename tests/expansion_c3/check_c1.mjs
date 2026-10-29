import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {adaptC1ScenePacket} from '../../robot_dashboard/static/features/obstacle_scene/c1_adapter.js';
import {createSceneConsumer} from '../../robot_dashboard/static/features/obstacle_scene/consumer.js';
import {makeContext} from '../../experiments/expansion_20261029/c3_scene_ui/fixture.js';
const wire=JSON.parse(readFileSync(process.argv[2],'utf8'));
const context=makeContext({map_id:wire.map_binding.map_id,revision:wire.map_binding.revision,generation:0});
const adapted=adaptC1ScenePacket(wire,context);assert.equal(adapted.reason,'');
const consumer=createSceneConsumer({getMap:()=>context,clock:()=>0});
assert.equal(consumer.ingest(adapted.packet),true);const v=consumer.snapshot();
assert.equal(v.obstacles.value.obstacles.length,3);assert.ok(v.pose.value);assert.ok(v.joints.value);
assert.ok(v.path.value);assert.ok(v.costmaps[0].value);assert.equal(v.collision.value.contact_state,'CONTACT_UNCONFIRMED');
assert.equal(adaptC1ScenePacket(wire,{...context,generation:1}).packet,null);
const old=structuredClone(wire);old.obstacle_frame.frame_key.frame_id='odom';
assert.equal(adaptC1ScenePacket(old,context).packet.obstacle_frame,null);
const missing=structuredClone(wire);missing.sources={};assert.equal(adaptC1ScenePacket(missing,context).reason,'C1_DISPLAY_PROFILE_REQUIRED');
const report={result:'PASS',kind:'SYNTHETIC',dependency_sha:'2402c02c6f91ba54064894b21735e01b98610acd',
  actual_calls:['C1 ObstacleFrame','C1 CollisionAssessment','C1 ScenePacket.from_dict','C3 adaptC1ScenePacket','C3 consumer.ingest'],
  limitations:['C1 wire validation plus explicit C3 nested display fixture only','No D2/D3 geometry solver or native replay','Not product wiring'],
  displayed:{objects:v.obstacles.value.obstacles.length,path:v.path.value.generation,costmaps:v.costmaps.length,contact:v.collision.value.contact_state},
  checks:['map generation mismatch rejected','odom layer without transform withheld','missing display profile withheld']};
console.log(JSON.stringify(report,null,2));if(process.argv[3])writeFileSync(process.argv[3],JSON.stringify(report,null,2)+'\n');
