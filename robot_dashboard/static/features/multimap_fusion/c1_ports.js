import {SCHEMA,pin,sourceDescriptor,clone} from './contract.js';
import {fromC1Source,toC1Request,fromC1Proposal} from './c1_contract.js';
// Published C1 API normalization. Request transport (auth/origin) belongs to host.
export function createC1Ports(request){
 const base='/api/v1/extensions/multimap',contexts=new Map();let sequence=0;
 const get=p=>request(base+p,{method:'GET'}),post=(p,body)=>request(base+p,{method:'POST',body});
 const key=id=>encodeURIComponent(id);
 function status(raw,context){
   if(raw.operational_installed!==false)throw new Error('C1 operational flag must be false.');
   context.counter++;
   if(raw.proposal)return fromC1Proposal(raw.proposal,context.ui,{job_revision:context.counter});
   return {schema:SCHEMA,job_id:raw.job_id,job_revision:context.counter,draft_revision:context.ui.draft_revision,input_pins:context.ui.sources.map(pin),
     state:['QUEUED','RUNNING'].includes(raw.state)?'RUNNING':raw.state==='CANCELED'?'CANCELLED':'FAILED',progress:(raw.progress||0)*100,reason:raw.error||raw.state};
 }
 const catalogue={async list(){const r=await get('/sources');if(!Array.isArray(r.sources))throw new Error('Invalid C1 source list.');return{schema:SCHEMA,sources:r.sources.map(s=>fromC1Source(s,{name:s.acquisition?.display_name||s.map_id}))};},
  async preview(s){const r=await get(`/sources/${key(s.id)}/preview`);if(!r.preview)throw new Error('C1 bounded preview provider unavailable.');return r.preview;}};
 const jobs={async start(ui){const wire=toC1Request(ui,{request_id:`c2-${Date.now()}-${++sequence}`,sequence}),raw=await post('/jobs',wire),context={ui:clone(ui),counter:0};contexts.set(raw.job_id,context);return status(raw,context);},
  async get(id){const context=contexts.get(id);if(!context)throw new Error('Unknown C1 job.');return status(await get(`/jobs/${key(id)}`),context);},
  cancel:id=>post(`/jobs/${key(id)}/cancel`,{}),
  async accept(req){const raw=await post(`/jobs/${key(req.proposal_id)}/review`,{expected_proposal_revision:req.proposal_revision,accepted:true,manual_selection:null});
    if(raw.state!=='REVIEWED'||raw.review?.accepted!==true||raw.proposal_revision!==req.proposal_revision+1||raw.job_id!==req.proposal_id)throw new Error('Invalid C1 review acknowledgement.');
    return{proposal_id:raw.job_id,proposal_revision:raw.proposal_revision,reviewed_candidate_revision:req.proposal_revision,review_id:`${raw.job_id}@${raw.proposal_revision}`};},
  async save(req){const manifest=await post(`/jobs/${key(req.proposal_id)}/exports`,{name:req.name,expected_proposal_revision:req.proposal_revision});
    if(manifest.schema!=='robot-scope.multimap-fusion.v1'||manifest.job_id!==req.proposal_id||manifest.proposal_revision!==req.proposal_revision||manifest.operational_installed!==false)throw new Error('Invalid C1 export acknowledgement.');
    const loaded=await get(`/exports/${key(manifest.id)}`);
    if(loaded.revision!==manifest.revision||loaded.output_hashes?.['map.pcd']!==manifest.output_hashes?.['map.pcd'])throw new Error('C1 exported identity reload mismatch.');
    return{runtime_installed:false,map:sourceDescriptor({id:loaded.id,name:loaded.name,kind:'pointcloud3d',session_id:`unverified:${loaded.id}`,revision:loaded.revision,sha256:loaded.output_hashes['map.pcd'],frame_id:loaded.frame_id,units:'m',point_count:loaded.point_count,ancestors:loaded.sources.map(s=>s.map_id)})};}
 };
 return{catalogue,jobs};
}
