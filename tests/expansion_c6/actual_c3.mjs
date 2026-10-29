import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {createReplay,parseReview,replayPacket} from '../../robot_dashboard/static/features/run_review/replay.js';
const root=path.join(process.argv[2],'robot_dashboard/static/features/obstacle_scene');
const {parseC1SceneJSON,adaptC1ScenePacket}=await import(pathToFileURL(path.join(root,'c1_adapter.js')));
const {createSceneConsumer}=await import(pathToFileURL(path.join(root,'consumer.js')));
const run=parseReview(fs.readFileSync(process.argv[3],'utf8'));let current,now=0;
const consumer=createSceneConsumer({getMap:()=>current,clock:()=>now});
for(const frame of run.frames){
  current=frame.context;now=Number(BigInt(frame.replay_ns))/1e6;
  assert.deepEqual(parseC1SceneJSON(JSON.stringify(frame.packet)),frame.packet);
  const {packet,reason}=replayPacket(frame,{playhead:frame.replay_ns},adaptC1ScenePacket);assert.ok(packet,reason);
  assert.ok(consumer.ingest(packet));assert.equal(consumer.snapshot().evidence_kind,'REPLAY');
  if(frame.packet.sources.global_path.status==='expired')assert.equal(consumer.snapshot().path.value,null);
}
consumer.destroy();
const r=createReplay(run);r.seek(run.frames[1].replay_ns);r.pause();
current=run.frames[1].context;
const again=createSceneConsumer({getMap:()=>current,clock:()=>now});
again.ingest(replayPacket(run.frames[1],r.state(),adaptC1ScenePacket).packet);
assert.equal(again.snapshot().path.value,null);assert.equal(again.snapshot().evidence_kind,'REPLAY');again.destroy();
console.log('actual C1 JSON parser / C3 adapter + consumer PASS; no transport mock in this probe');
