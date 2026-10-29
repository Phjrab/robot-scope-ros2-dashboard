import {SCHEMA,pin,identity,poseMatrix,clone} from '../../../robot_dashboard/static/features/multimap_fusion/contract.js';
import {generatePoints} from './generator.mjs';
const source=(id,name,index,extras={})=>({id,name,kind:'pointcloud3d',session_id:`synthetic-session-${index}`,revision:`r${index+1}`,sha256:String(index+1).repeat(64),frame_id:'map',units:'m',point_count:250000+index*50000,axes_verified:false,ancestors:[],...extras});
export function createFixture({scenario='normal',delay=80}={}) {
  let maps=[source('map-a','West hall',0),source('map-b','East hall',1),source('map-c','Upper wing',2),source('map-merged','Previous merge',3,{ancestors:['map-a','map-b']}),source('map-duplicate','West hall same revision',0,{id:'map-duplicate'})];
  let sequence=0,failures=0,previewFailures=0;const records=new Map(),calls=[];
  const log=(operation,body)=>calls.push({operation,body:clone(body??null)});
  const wait=()=>new Promise(resolve=>setTimeout(resolve,delay));
  const catalogue={
    async list(){log('sources');await wait();if(scenario==='loading-failure'&&failures++===0)throw new Error('Synthetic catalogue failure');if(scenario==='unsupported')return{schema:'unsupported',sources:maps};return{schema:SCHEMA,sources:scenario==='empty'?[]:clone(maps)};},
    async preview(s){log('preview',pin(s));await wait();if(scenario==='preview-failure'&&previewFailures++===0)throw new Error('Synthetic preview failure');return{schema:SCHEMA,input_pin:pin(s),units:'m',points:generatePoints(Math.max(0,maps.findIndex(m=>m.id===s.id)),scenario==='large'?100000:2400)};}
  };
  function response(record,solved=false){
    const r=record.request;
    const common={schema:SCHEMA,job_id:record.id,job_revision:solved?2:1,draft_revision:r.draft_revision,input_pins:r.input_pins,state:solved?'SOLVED_CANDIDATE':'RUNNING',progress:35,message:'UI_FIXTURE · scripted job; no solver executed'};
    if(!solved)return common;
    const transforms=Object.fromEntries(r.sources.map((s,i)=>[s.id,s.id===r.anchor?identity():poseMatrix({x:-i*1.5,y:i*.7,yaw:-i*.32})]));
    const ids=r.sources.map(s=>s.id),disconnected=scenario==='disconnected';
    return{...common,proposal_id:`proposal-${record.id}`,proposal_revision:1,transforms,accepted_edges:[[ids[0],ids[1]]],rejected_edges:disconnected?[[ids[1],ids[2]]]:[],connected_components:disconnected?[[ids[0],ids[1]],[ids[2]]]:[ids],
      warnings:['UI_FIXTURE: transforms scripted, registration accuracy untested.','Identity / scale / axes require review.',...(scenario==='ambiguous'?['AMBIGUOUS: repeated corridor; low RMSE is insufficient.']:[])],
      metrics:{pairwise:[{pair:ids.slice(0,2),overlap:.68,rmse_m:.018,warning:scenario==='ambiguous'?'Ambiguous corridor':'Inspect residuals'}]},
      heatmap:[{position:[2,1,.5],distance_m:.34},{position:[-1,2,.2],distance_m:.1}],
      derived_2d:{width:12,height:8,resolution_m:.5,cells:Array.from({length:96},(_,i)=>i%12<2?-1:i%12===2||i<12||i>84?100:0)}};
  }
  const jobs={
    async start(request){log('job',request);await wait();const id=`job-${++sequence}`;records.set(id,{id,request:clone(request)});return response(records.get(id));},
    async get(id){log('job-status',{id});await wait();if(scenario==='job-failure'&&failures++===0)return{...response(records.get(id)),state:'FAILED',reason:'Synthetic registration failure / insufficient overlap'};return response(records.get(id),true);},
    async cancel(id){log('cancel',{id});await wait();return{cancelled:true};},
    async accept(request){log('review',request);await wait();return{proposal_id:request.proposal_id,proposal_revision:request.proposal_revision,review_id:`review-${sequence}`};},
    async save(request){log('export',request);await wait();if(scenario==='save-failure'&&failures++===0)throw new Error('Synthetic export failure');const map=source(`new-map-${sequence}`,request.name,5,{sha256:'a'.repeat(64),revision:'saved-r1',ancestors:request.input_pins.map(s=>s.id)});maps=[...maps,map];return{map,runtime_installed:false};}
  };
  return{catalogue,jobs,calls,setDelay(v){delay=v;},setScenario(v){scenario=v;},get maps(){return clone(maps);}};
}
