import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createReplay,parseReview,replayPacket,compareRuns} from '../../robot_dashboard/static/features/run_review/replay.js';
const run=()=>({schema:'robot-scope.run-review.v1',mode:'REPLAY',provenance:{data_kind:'SYNTHETIC'},precision:{requested:null},events:[0,1000000000,2000000000].map((n,i)=>({index:i,kind:'pose',replay_ns:String(n),time:{value:'9007199254740993'}})),frames:[]});
test('pause, seek, reverse, step, speed use independent clock',()=>{
  const r=createReplay(run());r.play();r.tick(500);assert.equal(r.state().playhead,'500000000');r.pause();r.tick(500);assert.equal(r.state().playhead,'500000000');
  r.step();assert.equal(r.state().index,1);r.speed(2);r.play();r.tick(250);assert.equal(r.state().playhead,'1500000000');r.speed(-1);r.tick(500);assert.equal(r.state().index,1);r.seek('0');assert.equal(r.state().mode,'REPLAY');
});
test('mock adapter receives archived age; source bytes/time never rewritten',()=>{
  const f={replay_ns:'0',context:{},packet:{schema_version:'0.2',evidence_kind:'LIVE',source:{stamp_ns:'9007199254740993',evidence_kind:'LIVE'}}};
  const before=JSON.stringify(f);let options;
  const result=replayPacket(f,{playhead:'2000000000'},(wire,c,o)=>{options=o;return {packet:wire};});
  assert.equal(options.transportAgeMs,2000);assert.equal(result.packet.evidence_kind,'REPLAY');assert.equal(result.packet.source.stamp_ns,'9007199254740993');assert.equal(before,JSON.stringify(f));
});
test('unsafe ns, huge files and unordered events fail closed',()=>{
  const r=run();r.events[0].time.stamp_ns=9007199254740992;assert.throws(()=>parseReview(JSON.stringify(r)),/NS/);
  const q=run();q.events[1].replay_ns='3000000000';assert.throws(()=>parseReview(JSON.stringify(q)),/ORDER/);
});
test('different or missing conditions are reference comparison without improvement rate',()=>{
  const a=run(),b=run();a.provenance.goal_id='a';b.provenance.goal_id='b';const c=compareRuns(a,b);assert.ok(c.differences.includes('goal_id'));assert.equal(c.algorithm_improvement_rate,null);
});
