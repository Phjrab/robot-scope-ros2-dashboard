// Actual endpoint response + explicit trusted context, no sources.display profile.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {adaptC1ScenePacket,parseC1SceneJSON} from '../../robot_dashboard/static/features/obstacle_scene/c1_adapter.js';
import {createSceneConsumer} from '../../robot_dashboard/static/features/obstacle_scene/consumer.js';
const wire=parseC1SceneJSON(readFileSync(process.argv[2],'utf8'));
const context=JSON.parse(readFileSync(process.argv[3],'utf8'));
const adapted=adaptC1ScenePacket(wire,context);assert.equal(adapted.reason,'');
const consumer=createSceneConsumer({getMap:()=>context,clock:()=>0});
assert.equal(consumer.ingest(adapted.packet),true);const v=consumer.snapshot();
assert.equal(v.source_mode,'ACTUAL_C1_SERVICE');assert.equal(v.obstacles.value?.obstacles.length,wire.obstacle_frame?.obstacles.length);
assert.equal(adaptC1ScenePacket(wire,{...context,generation:context.generation+1}).packet,null);
console.log(JSON.stringify({result:'PASS',kind:wire.evidence_kind,objects:v.obstacles.value?.obstacles.length,risk:v.collision.value?.severity ?? 'UNAVAILABLE'}));
