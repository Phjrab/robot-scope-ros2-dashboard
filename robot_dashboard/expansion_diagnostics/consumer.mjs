// Actual pinned C3 parser/adapter/consumer; no alternate contract or display geometry.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const base=`${input.deps}/C3/robot_dashboard/static/features/obstacle_scene`;
const {parseC1SceneJSON,adaptC1ScenePacket}=await import(pathToFileURL(`${base}/c1_adapter.js`));
const {createSceneConsumer}=await import(pathToFileURL(`${base}/consumer.js`));
const times=[];
let outcome;
for(let i=0;i<4;i++){
  const start=performance.now();
  const wire=parseC1SceneJSON(input.raw), parsed=performance.now();
  const context={...wire.map_binding,stream_epoch:wire.stream_epoch,source_epoch:'synthetic-1',frame_id:'odom',clock_domain:'fixture-clock',calibration_id:wire.obstacle_frame?.calibration_id,units:'m'};
  const adapted=adaptC1ScenePacket(wire,context), end=performance.now();
  if(!adapted.packet){outcome={status:'FAIL',reason:adapted.reason};break;}
  const consumer=createSceneConsumer({getMap:()=>context});
  const accepted=consumer.ingest(adapted.packet), finished=performance.now();
  const view=consumer.snapshot();
  outcome={status:accepted?'PASS':'FAIL',reason:consumer.diagnostics().error,
    obstacleCount:view.obstacles?.value?.obstacles?.length ?? 0,
    collisionAvailable:!!view.collision?.value, collisionReason:view.collision?.reason,
    availability:adapted.packet.availability, diagnostics:consumer.diagnostics()};
  consumer.destroy();
  times.push({warmup:i===0,clock:'Node performance.now',parse_ms:parsed-start,adapt_ms:end-parsed,consume_ms:finished-end});
}
console.log(JSON.stringify({...outcome,timings:times,render:'NOT_RUN_NODE_CONSUMER_ONLY'}));
if(outcome.status==='FAIL')process.exitCode=2;
