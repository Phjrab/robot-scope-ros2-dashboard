export const MAX_BYTES = 64 * 1024 * 1024;
const ns = v => typeof v === 'string' && /^(0|[1-9]\d{0,24})$/.test(v);
// Private bundles come from the bounded Python adapters. Never JSON.parse raw C1 ns integers.
export function parseReview(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > MAX_BYTES) throw new Error('REVIEW_SIZE_LIMIT');
  const run = JSON.parse(raw);
  if (run?.schema !== 'robot-scope.run-review.v1' || run.mode !== 'REPLAY'
    || !['REAL','SIMULATION','SYNTHETIC','UNKNOWN'].includes(run.provenance?.data_kind)
    || !Array.isArray(run.events) || !run.events.length || run.events.length > 20000
    || !Array.isArray(run.frames) || run.frames.length > 20000) throw new Error('REVIEW_SCHEMA');
  function check(value, depth=0) {
    if (depth > 32) throw new Error('DEPTH_LIMIT');
    if (typeof value === 'number' && (!Number.isFinite(value) || Number.isInteger(value) && !Number.isSafeInteger(value))) throw new Error('UNSAFE_NUMBER');
    if (value && typeof value === 'object') for (const [k,v] of Object.entries(value)) {
      if (k.endsWith('_ns') && v !== null && !ns(v)) throw new Error('NS_MUST_BE_STRING');
      check(v,depth+1);
    }
  }
  check(run);
  let previous = 0n;
  run.events.forEach((e,i) => {
    if (e.index !== i || !ns(e.replay_ns) || BigInt(e.replay_ns) < previous || !e.time) throw new Error('EVENT_ORDER');
    previous = BigInt(e.replay_ns);
  });
  if (previous > 86400000000000n) throw new Error('REPLAY_DURATION_LIMIT');
  for (const f of run.frames) if (!ns(f.replay_ns) || !Number.isSafeInteger(f.event_index)
    || f.event_index < 0 || f.event_index >= run.events.length || !['0.1','0.2'].includes(f.packet?.schema_version)
    || !f.context) throw new Error('FRAME_SCHEMA');
  return run;
}

export function createReplay(run, changed=()=>{}) {
  const end = BigInt(run.events.at(-1).replay_ns);
  let playhead = 0n, playing = false, speed = 1, generation = 0;
  function state() {
    let index=0;
    for (let i=0;i<run.events.length;i++) { if (BigInt(run.events[i].replay_ns)>playhead) break; index=i; }
    return {mode:'REPLAY',playhead:playhead.toString(),index,playing,speed,generation,end:end.toString()};
  }
  function seek(value) { const n=BigInt(value);playhead=n<0n?0n:n>end?end:n;generation++;changed(state(),true); }
  return {state, seek,
    pause() {playing=false;changed(state(),false);},
    play() {playing=true;changed(state(),false);},
    speed(value) {if (![.25,.5,1,2,4,-1].includes(value))throw new Error('SPEED_INVALID');speed=value;changed(state(),false);},
    step(direction=1) {playing=false;const i=Math.max(0,Math.min(run.events.length-1,state().index+direction));seek(run.events[i].replay_ns);},
    tick(ms) {
      if (!playing || !Number.isFinite(ms) || ms<0 || ms>1000) return;
      const next=playhead+BigInt(Math.round(ms*1e6*speed));
      if (next<=0n || next>=end) playing=false;
      playhead=next<0n?0n:next>end?end:next;
      if(speed<0)generation++;
      changed(state(),speed<0);
    },
  };
}

export function frameAt(run, state) {
  let frame=null;
  for (const f of run.frames) {
    if (f.event_index>state.index || BigInt(f.replay_ns)>BigInt(state.playhead)) break;
    frame=f;
  }
  return frame;
}
export function replayPacket(frame, state, adapt) {
  const age=Number(BigInt(state.playhead)-BigInt(frame.replay_ns))/1e6;
  if (age<0) throw new Error('FUTURE_FRAME');
  const wire=structuredClone(frame.packet);
  // A display projection only. Original canonical bytes stay untouched in the bundle.
  function mark(value) {
    if (!value || typeof value!=='object') return;
    for(const [key,v] of Object.entries(value)) {if(key==='evidence_kind')value[key]='REPLAY';else mark(v);}
  }
  mark(wire);
  const result=adapt(wire,frame.context,{transportAgeMs:age,displayAssets:[]});
  if(result.packet) {result.packet.evidence_kind='REPLAY';result.packet.source_mode='ARCHIVED_C1_REPLAY';}
  return result;
}
export function compareRuns(a,b) {
  const keys=['code_sha','parameters_revision','parameters_digest','map_id','map_revision','goal_id','data_kind','source_id'];
  const differences=keys.filter(k=>a.provenance[k]==null || b.provenance[k]==null || a.provenance[k]!==b.provenance[k]);
  if(!a.precision.requested || JSON.stringify(a.precision.requested)!==JSON.stringify(b.precision.requested))differences.push('goal_pose');
  return {classification:differences.length?'참고 비교 · 동일 조건 A/B 아님':'기록된 메타데이터 일치 · 인과 개선 증거 아님',differences,algorithm_improvement_rate:null};
}
