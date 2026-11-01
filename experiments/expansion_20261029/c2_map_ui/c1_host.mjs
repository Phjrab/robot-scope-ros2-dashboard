import {fromC1Source,toC1Request,fromC1Proposal} from '../../../robot_dashboard/static/features/multimap_fusion/c1_contract.js';
import {SCHEMA,pin} from '../../../robot_dashboard/static/features/multimap_fusion/contract.js';
import {generatePoints} from './generator.mjs';
// Exact external DTO fixture displayed by the same mount/test host; no algorithm.
export function createC1Fixture(external){
 const sources=external.request.sources.map((s,i)=>fromC1Source(s,{name:`C1 exact contract source ${i+1}`}));const calls=[];
 return {calls,catalogue:{async list(){return{schema:SCHEMA,sources};},async preview(s){return{schema:SCHEMA,input_pin:pin(s),units:'m',points:generatePoints(sources.findIndex(v=>v.id===s.id),240)};}},
 jobs:{async start(request){const wire=toC1Request(request,{request_id:'c2-exact-contract-check'});calls.push({operation:'job',body:wire});return fromC1Proposal(external.proposal,request);}}};
}
