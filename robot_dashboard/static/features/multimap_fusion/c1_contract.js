// Translation of published C1 v0.1 wire DTOs only; no service or solver.
import {SCHEMA,clone,sourceDescriptor,pin,rigidMatrix} from './contract.js';
export const C1_CONTRACT_SHA='4e1dd519a707169da5f88cf2a92a20ed3e701cc7';
export const sourceKey=s=>`${s.map_id}:${s.revision}:${s.frame_id}`;
export function fromC1Source(wire,{name,ancestors=[]}={}) {
  if(wire?.schema_version!=='0.1'||!['SYNTHETIC','REPLAY'].includes(wire.evidence_kind)||wire.asset_role!=='full_source')throw new Error('C1 offline full-source v0.1 required.');
  return sourceDescriptor({id:wire.map_id,name:name||wire.map_id,kind:'pointcloud3d',session_id:wire.mapping_session_id||`unverified:${wire.map_id}`,
    revision:wire.revision,sha256:wire.sha256,frame_id:wire.frame_id,units:wire.units,point_count:wire.point_count,
    axes_verified:false,ancestors,wire_descriptor:clone(wire)});
}
export function toC1Request(ui,{request_id,sequence=0,source_epoch='c2-offline-review'}={}) {
  if(ui.schema!==SCHEMA||!request_id)throw new Error('Pinned UI request / request_id required.');
  const sources=ui.sources.map(s=>{if(!s.wire_descriptor)throw new Error('Full C1 descriptor unavailable.');const w=s.wire_descriptor;if(w.map_id!==s.id||w.revision!==s.revision||w.sha256!==s.sha256||w.frame_id!==s.frame_id||w.units!==s.units||(w.mapping_session_id||`unverified:${w.map_id}`)!==s.session_id||!['SYNTHETIC','REPLAY'].includes(w.evidence_kind))throw new Error('C1 source pin changed / live input refused.');return clone(w);});
  const keys=Object.fromEntries(sources.map(s=>[s.map_id,sourceKey(s)]));
  return {schema_version:'0.1',evidence_kind:sources.some(s=>s.evidence_kind==='REPLAY')?'REPLAY':'SYNTHETIC',producer:'c2-ui',sequence,source_epoch,
    request_id,anchor_source_key:keys[ui.anchor],sources,source_pins:Object.fromEntries(sources.map(s=>[sourceKey(s),s.sha256])),
    initial_guesses:ui.sources.map(s=>({source_key:keys[s.id],T_anchor_source:rigidMatrix(ui.initial_guesses[s.id])})),
    correspondences:ui.correspondences.map(p=>({source_key:keys[p.source_id],source_xyz:p.source_xyz,anchor_xyz:p.anchor_xyz})),mode:ui.correspondences.length||ui.sources.some(s=>ui.initial_guesses[s.id].some((v,i)=>Math.abs(v-([0,5,10,15].includes(i)?1:0))>1e-10))?'seeded':'auto',options:{}};
}
export function fromC1Proposal(wire,ui,{job_revision=1}={}) {
  if(wire?.schema_version!=='0.1'||!['SYNTHETIC','REPLAY'].includes(wire.evidence_kind))throw new Error('Offline C1 v0.1 proposal required.');
  const keys=Object.fromEntries(ui.sources.map(s=>{if(!s.wire_descriptor)throw new Error('C1 descriptor required.');return[sourceKey(s.wire_descriptor),s.id];}));
  const expected=Object.fromEntries(ui.sources.map(s=>[sourceKey(s.wire_descriptor),s.sha256]));
  if(Object.keys(expected).length!==Object.keys(wire.input_pins||{}).length||Object.entries(expected).some(([k,v])=>wire.input_pins[k]!==v)||keys[wire.anchor_source_key]!==ui.anchor)throw new Error('C1 proposal input pins / anchor differ.');
  const state=wire.state==='CANCELED'?'CANCELLED':['SOLVED_CANDIDATE','NEEDS_PRIOR','DISCONNECTED','REJECTED','FAILED'].includes(wire.state)?wire.state:'FAILED';
  const transforms=Object.fromEntries(Object.entries(wire.T_fused_source||{}).map(([key,t])=>{if(!keys[key])throw new Error('Unknown C1 transform source.');return[keys[key],rigidMatrix(t)];}));
  const edges=wire.pairwise_edges||[];
  return {schema:SCHEMA,draft_revision:ui.draft_revision,job_revision,job_id:wire.job_id,state,proposal_id:wire.job_id,proposal_revision:wire.proposal_revision,
    input_pins:ui.sources.map(pin),transforms,accepted_edges:edges.filter(e=>e.accepted===true),rejected_edges:edges.filter(e=>e.accepted!==true),
    connected_components:(wire.connected_components||[]).map(c=>c.map(k=>{if(!keys[k])throw new Error('Unknown component source.');return keys[k];})),
    metrics:{pairwise:wire.quality?.pairwise||edges.map(e=>({pair:[keys[e.target]||e.target,keys[e.source]||e.source],overlap:e.metrics?.overlap_ratio??e.metrics?.overlap??(e.metrics?.overlap_source!=null&&e.metrics?.overlap_target!=null?`${e.metrics.overlap_source.toFixed(2)} source / ${e.metrics.overlap_target.toFixed(2)} target`:undefined),rmse_m:e.metrics?.rmse_m,distance_p95_m:e.metrics?.distance_p95_m,warning:e.accepted?'Review accepted edge':'Rejected / ambiguous edge'}))},warnings:[...(wire.warnings||[]),...(wire.ambiguous_candidates?.length?['C1 ambiguous candidates require review.']:[]),`C1 contract ${C1_CONTRACT_SHA}; solver ${wire.solver_version}`],reason:wire.state==='SOLVED_CANDIDATE'?undefined:`C1 terminal state ${wire.state}; inspect warnings.`};
}
