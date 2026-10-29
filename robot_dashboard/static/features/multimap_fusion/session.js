import {SCHEMA,CONVENTION,MAX_SOURCES,clone,sourceDescriptor,pin,pinsEqual,poseMatrix,rigidMatrix,identity,validateCorrespondences,selectionWarnings} from './contract.js';
const empty=()=>({sources:[],anchor:null,priors:{},correspondences:[]});
export function createSession() {
  let draft=empty(),revision=0,history=[],future=[],proposal=null,accepted=null,status='EMPTY',nonce=0,token=null,jobRevision=-1,jobId=null,stale=0;
  function edit(next,record=true) {
    if(record) { history.push(clone(draft)); if(history.length>60)history.shift(); future=[]; }
    draft=clone(next);revision++;proposal=null;accepted=null;token=null;jobRevision=-1;jobId=null;status=draft.sources.length?'DRAFT':'EMPTY';
  }
  const selected=()=>draft.sources;
  return {
    snapshot:()=>clone({draft,revision,proposal,accepted,status,stale,canUndo:!!history.length,canRedo:!!future.length,warnings:selectionWarnings(selected())}),
    select(sources) {
      if(sources.length>MAX_SOURCES)throw new Error(`At most ${MAX_SOURCES} sources.`);
      const ss=sources.map(sourceDescriptor);
      if(new Set(ss.map(s=>s.id)).size!==ss.length)throw new Error('Duplicate source ID.');
      edit({sources:ss,anchor:ss[0]?.id||null,priors:Object.fromEntries(ss.map(s=>[s.id,{x:0,y:0,z:0,roll:0,pitch:0,yaw:0}])),correspondences:[]});
    },
    anchor(id) {if(!selected().some(s=>s.id===id))throw new Error('Unknown anchor.');edit({...draft,anchor:id,correspondences:[]});},
    prior(id,pose) {
      if(id===draft.anchor || !selected().some(s=>s.id===id))throw new Error('Select a non-anchor source.');
      const next={...draft.priors[id],...pose};poseMatrix(next);edit({...draft,priors:{...draft.priors,[id]:next}});
    },
    addPair(id,source_xyz,anchor_xyz,provenance='explicit-xyz') {
      if(id===draft.anchor || !selected().some(s=>s.id===id))throw new Error('Select a non-anchor source.');
      if([source_xyz,anchor_xyz].some(p=>!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite)))throw new Error('Finite XYZ required.');
      if(draft.correspondences.length>=64)throw new Error('At most 64 pairs.');
      edit({...draft,correspondences:[...draft.correspondences,{source_id:id,anchor_id:draft.anchor,source_xyz,anchor_xyz,provenance}]});
    },
    invalidate(){edit(draft,false);},
    clearPairs(){edit({...draft,correspondences:[]});},
    undo(){if(history.length){future.push(clone(draft));edit(history.pop(),false);}},
    redo(){if(future.length){history.push(clone(draft));edit(future.pop(),false);}},
    reset(){edit({...draft,priors:Object.fromEntries(selected().map(s=>[s.id,{x:0,y:0,z:0,roll:0,pitch:0,yaw:0}])),correspondences:[]});},
    begin() {
      if(selected().length<2)throw new Error('Select at least two 3D maps.');
      for(const id of new Set(draft.correspondences.map(p=>p.source_id)))validateCorrespondences(draft.correspondences.filter(p=>p.source_id===id));
      const pins=selected().map(pin);token={draft_revision:revision,nonce:++nonce,input_pins:pins};jobRevision=-1;jobId=null;status='RUNNING';proposal=null;accepted=null;
      return {token:clone(token),request:{schema:SCHEMA,draft_revision:revision,sources:clone(selected()),anchor:draft.anchor,
        convention:CONVENTION,units:'m',angles:'rad',input_pins:pins,
        initial_guesses:Object.fromEntries(selected().map(s=>[s.id,s.id===draft.anchor?identity():poseMatrix(draft.priors[s.id])])),
        correspondences:clone(draft.correspondences),options:{input_mode:'synthetic-or-replay',activate:false}}};
    },
    receive(ticket,r) {
      if(!token || ticket.nonce!==token.nonce || ticket.draft_revision!==revision){stale++;return false;}
      if(r?.schema!==SCHEMA || r.draft_revision!==revision || !pinsEqual(r.input_pins,token.input_pins)
          || !Number.isSafeInteger(r.job_revision) || r.job_revision<jobRevision || !r.job_id)throw new Error('Unsupported / stale job identity or schema.');
      if(jobId && jobId!==r.job_id)throw new Error('Job identity changed.');
      if(!['RUNNING','CANCELLED','FAILED','SOLVED_CANDIDATE','NEEDS_PRIOR','DISCONNECTED','REJECTED'].includes(r.state))throw new Error('Unsupported job state.');
      if(['SOLVED_CANDIDATE','NEEDS_PRIOR','DISCONNECTED','REJECTED'].includes(r.state)) {
        if(!r.proposal_id || !Number.isSafeInteger(r.proposal_revision) || r.proposal_revision<0 || !r.transforms
            || (r.state==='SOLVED_CANDIDATE' && Object.keys(r.transforms).length!==selected().length) || Object.keys(r.transforms).some(id=>!selected().some(s=>s.id===id)))throw new Error('Incomplete proposal identity / transforms.');
        for(const transform of Object.values(r.transforms))rigidMatrix(transform);
        if(r.transforms[draft.anchor] && !pinsEqual(r.transforms[draft.anchor],identity()))throw new Error('Anchor transform must remain identity.');
        if(!Array.isArray(r.connected_components) || !r.connected_components.length
            || !pinsEqual([...r.connected_components.flat()].sort(),selected().map(s=>s.id).sort()))throw new Error('Invalid connected components.');
        if(!Array.isArray(r.warnings)||!Array.isArray(r.accepted_edges)||!Array.isArray(r.rejected_edges))throw new Error('Proposal diagnostics required.');
        if(proposal && (r.proposal_revision<proposal.proposal_revision || (r.proposal_revision===proposal.proposal_revision && !pinsEqual(r.transforms,proposal.transforms))))throw new Error('Stale / mutated proposal revision.');
        proposal=clone(r);
      }
      jobRevision=r.job_revision;jobId=r.job_id;status=r.state;return true;
    },
    fail(){if(status==='RUNNING')status='FAILED';},
    cancel(){token=null;status='CANCELLED';proposal=null;accepted=null;},
    reviewRequest() {
      if(!proposal || status!=='SOLVED_CANDIDATE')throw new Error('Solve a current candidate first.');
      if(proposal.connected_components.length!==1)throw new Error('Disconnected components cannot be accepted.');
      return {schema:SCHEMA,proposal_id:proposal.proposal_id,proposal_revision:proposal.proposal_revision,draft_revision:revision,input_pins:clone(proposal.input_pins),decision:'accept',warnings_acknowledged:true};
    },
    reviewed(request,result) {
      if(!proposal || request.draft_revision!==revision || request.proposal_id!==proposal.proposal_id || request.proposal_revision!==proposal.proposal_revision || !pinsEqual(request.input_pins,proposal.input_pins)
          || result?.proposal_id!==proposal.proposal_id || (!Number.isSafeInteger(result.proposal_revision) || result.proposal_revision<proposal.proposal_revision || (result.proposal_revision!==proposal.proposal_revision && result.reviewed_candidate_revision!==request.proposal_revision)) || !result.review_id)throw new Error('Stale review acknowledgement.');
      proposal.proposal_revision=result.proposal_revision;accepted=clone(result);status='ACCEPTED';
    },
    saveRequest(name) {
      if(status!=='ACCEPTED'||!accepted)throw new Error('Explicit review required.');
      if(!/^[A-Za-z0-9_-]{1,64}$/.test(name) || selected().some(s=>s.name===name))throw new Error('Use a new name (letters/numbers/_/-, 1–64).');
      return {schema:SCHEMA,name,proposal_id:accepted.proposal_id,proposal_revision:accepted.proposal_revision,review_id:accepted.review_id,draft_revision:revision,input_pins:selected().map(pin),format:'pcd',activate:false};
    },
    saved(request,result) {
      if(status!=='ACCEPTED'||request.draft_revision!==revision || request.proposal_id!==accepted?.proposal_id || request.proposal_revision!==accepted?.proposal_revision || request.review_id!==accepted?.review_id || !pinsEqual(request.input_pins,selected().map(pin)))throw new Error('Stale save response.');
      const map=sourceDescriptor(result?.map);
      if(result.runtime_installed!==false || selected().some(s=>s.id===map.id || s.sha256===map.sha256) || map.name!==request.name)throw new Error('Save must confirm a new ID/revision/hash and no runtime installation.');
      status='SAVED';return map;
    }
  };
}
