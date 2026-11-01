// C1 0.1/0.2 canonical SceneSnapshotService consumer. C1 owns wire validation.
// JSON integers carrying host nanoseconds must never pass through a JS Number.
export function parseC1SceneJSON(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 128 * 1024) throw new Error('C1_DOCUMENT_LIMIT');
  // Tokenize strings as a whole: digits inside quoted text are never rewritten.
  const tokens = raw.match(/"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|\s+|./gs) || [];
  let field = '', colon = false;
  const ns = new Set(['received_monotonic_ns','start_monotonic_ns','end_monotonic_ns']);
  return JSON.parse(tokens.map(token => {
    if (/^\s+$/.test(token)) return token;
    if (token.startsWith('"')) { field = JSON.parse(token); colon = false; return token; }
    if (token === ':') { colon = true; return token; }
    const out = colon && ns.has(field) && /^\d+$/.test(token) ? `"${token}"` : token;
    field = ''; colon = false; return out;
  }).join(''));
}
const ns = value => {
  if (typeof value === 'number' && !Number.isSafeInteger(value)) return null;
  if (!/^(0|[1-9]\d*)$/.test(String(value))) return null;
  const n = BigInt(value); return n <= 9223372036854775807n ? n : null;
};
const sameBinding = (a,b) => a && b && ['map_id','revision','generation'].every(k=>a[k]===b[k]);
const refMatches = (ref, value) => ref && value && ['source_epoch','sequence'].every(k=>ref[k]===value[k])
  && ['stamp_ns','clock_domain','host_clock_id','evidence_kind'].every(k=>!(k in ref) || ref[k]===value[k])
  && (!ref.frame_key || ref.frame_key.source_epoch===value.frame_key?.source_epoch && ref.frame_key.frame_id===value.frame_key?.frame_id)
  && (!ref.map_binding || sameBinding(ref.map_binding,value.map_binding));
const geometry = g => g ? {center_m:g.center,extent_m:g.extent,orientation_xyzw:g.orientation_xyzw} : null;

export function adaptC1ScenePacket(wire, context, { transportAgeMs = 0, displayAssets = [] } = {}) {
  const failure = reason => ({packet:null,reason});
  if (!['0.1','0.2'].includes(wire?.schema_version)) return failure('C1_VERSION_UNSUPPORTED');
  if (!sameBinding(wire.map_binding,context)) return failure('C1_MAP_GENERATION_MISMATCH');
  if (wire.stream_epoch !== context.stream_epoch || wire.source_epoch !== wire.stream_epoch) return failure('C1_STREAM_MISMATCH');
  if (!Number.isFinite(transportAgeMs) || transportAgeMs < 0) return failure('C1_TRANSPORT_AGE_UNKNOWN');
  displayAssets=displayAssets.filter(a=>wire.sources?.assets?.some(ref=>['id','revision','role','source','media_type','bytes','usage'].every(k=>ref[k]===a.ref?.[k])));
  const errors = displayAssets.filter(a=>a.status!=='READY').map(a=>`asset:${a.ref.role}:${a.status}`);
  function observation(value, slot) {
    if (!value) return null;
    if (wire.schema_version === '0.2' && wire.sources?.[slot]?.status !== 'ready') {
      errors.push(`${slot}:SERVER_NOT_READY`); return null;
    }
    if (value.frame_key?.frame_id !== context.frame_id || value.frame_key?.source_epoch !== value.source_epoch
      || value.source_epoch !== context.source_epoch || value.clock_domain !== context.clock_domain
      || !sameBinding(value.map_binding,wire.map_binding)) { errors.push(`${slot}:IDENTITY_OR_CLOCK_MISMATCH`); return null; }
    const source = wire.sources?.[slot];
    if (!source || !refMatches(source,value) || source.host_clock_id !== value.host_clock_id
      || source.stamp_ns !== value.stamp_ns || source.clock_domain !== value.clock_domain
      || !Number.isFinite(source.received_age_ms) || source.received_age_ms < 0 || ns(value.received_monotonic_ns) === null) {
      errors.push(`${slot}:HOST_AGE_OR_PRECISION_UNKNOWN`); return null;
    }
    return {...value.data,...value, canonical:true,
      frame_key:{map_id:context.map_id,revision:context.revision,frame_id:context.frame_id},
      age_ms:source.received_age_ms + transportAgeMs, sensor_age_ms:source.sensor_age_ms,
      receipt_source_ns:String(value.received_monotonic_ns),
      calibration_id:value.calibration_id ?? value.data?.calibration_id,
      ref:`${value.source_epoch}:${value.sequence}`, provenance:value.data?.provenance || value.health || {}};
  }
  const pose = observation(wire.robot_pose,'robot_pose');
  // C1 does not define a joint slot or generic data geometry profile. Only an
  // explicitly supplied pose.data.joint_state can animate the visual model.
  const jointData = pose?.data?.joint_state;
  const joints = jointData ? {...pose,...jointData,ref:jointData.stamp_ns} : null;
  const obstacles = observation(wire.obstacle_frame,'obstacle_frame');
  if (obstacles) obstacles.obstacles = wire.obstacle_frame.obstacles.map(o=>({...o,
    geometry:geometry(o.geometry), sensor_support:Array.isArray(o.sensor_support) ? o.sensor_support : [o.sensor_support]}));
  const sensors = [];
  for (const input of wire.obstacle_frame?.input_sources || []) {
    // Optional producer-supplied bounded geometry; absent geometry stays absent.
    if (!input || typeof input !== 'object' || !Array.isArray(input.points_m)) continue;
    if (!obstacles || !sameBinding(input.map_binding,wire.map_binding) || input.source_epoch !== obstacles.source_epoch
      || input.frame_key?.frame_id !== context.frame_id || input.clock_domain !== obstacles.clock_domain
      || input.host_clock_id !== obstacles.host_clock_id || String(input.received_monotonic_ns) !== obstacles.receipt_source_ns) continue;
    sensors.push({...obstacles,...input,frame_key:obstacles.frame_key,canonical:true,
      age_ms:obstacles.age_ms,id:input.sensor_id,kind:input.kind,origin_m:input.origin_m,
      health:input.health,receipt_source_ns:String(input.received_monotonic_ns)});
  }
  const path = observation(wire.global_path,'global_path');
  const local = observation(wire.controller_local_trajectory,'controller_local_trajectory');
  let costmap = observation(wire.costmap_snapshot,'costmap_snapshot');
  const costRef=wire.costmap_snapshot?.data?.asset_ref;
  if(costmap && costRef){
    const asset=displayAssets.find(a=>a.status==='READY' && a.ref.role==='costmap' && a.ref.source==='costmap_snapshot'
      && a.ref.id===costRef.id && a.ref.revision===costRef.revision && sameBinding(a.value?.map_binding,wire.map_binding));
    if(asset?.value?.costmap)costmap={...costmap,
      // Only geometry is decoded: bytes cannot replace canonical identity/time.
      ...Object.fromEntries(['id','width','height','cells','origin','resolution_m','plane_z_m','representation','cell_encoding'].map(k=>[k,asset.value.costmap[k]])),
      provenance:{...costmap.provenance,display_asset:asset.ref,display_transform:asset.value.display_transform}};
    else {errors.push('costmap_snapshot:DISPLAY_ASSET_UNAVAILABLE');costmap=null;}
  }
  let assessment = observation(wire.collision_assessment,'collision_assessment');
  if (assessment) {
    const interval = assessment.validity_interval, start=ns(interval?.start_monotonic_ns), end=ns(interval?.end_monotonic_ns);
    const received=ns(assessment.received_monotonic_ns);
    const age=wire.sources.collision_assessment.received_age_ms;
    const nowOffset=age*1e6;
    const valid = start !== null && end !== null && received !== null && end >= start
      && interval.host_clock_id === assessment.host_clock_id
      && Number(start-received) <= nowOffset && Number(end-received) >= nowOffset;
    if (!valid) { errors.push('collision_assessment:VALIDITY_OR_CLOCK_UNKNOWN'); assessment=null; }
    else {
      const original=assessment;
      assessment={...original,calibration_id:pose?.calibration_id ?? obstacles?.calibration_id,
        references_verified:refMatches(original.robot_pose_ref,wire.robot_pose)
          && original.joint_state_ref?.stamp_ns === joints?.stamp_ns
          && refMatches(original.obstacle_frame_ref,wire.obstacle_frame)
          && (original.path_ref === null ? path === null : refMatches(original.path_ref,wire.global_path)),
        min_clearance_m:original.min_clearance,modeled_ttc_s:original.modeled_ttc,
        contact_state:original.reason==='PREDICTED_COLLISION' ? 'PREDICTED_CONTACT' : original.reason==='MODEL_OVERLAP' ? 'MODEL_OVERLAP' : 'CONTACT_UNCONFIRMED',
        validity_interval:original.validity_interval,
        remaining_ms:Number(end-received)/1e6-age-transportAgeMs,
        coverage:original.freshness?.coverage ?? 'UNAVAILABLE',
        protection_mode:original.freshness?.protection_mode ?? 'UNAVAILABLE',
        // D3 scalar envelopes are NOT drawable box geometry.
        envelopes:[],envelope_geometry_status:'UNAVAILABLE'};
    }
  }
  const slots=[pose,obstacles,path,local,costmap,assessment].filter(Boolean);
  const stamps=[...slots,...Object.values(wire.sources || {})].map(x=>x?.stamp_ns).filter(s=>typeof s==='string' && /^\d{1,25}$/.test(s));
  const newest=stamps.reduce((a,b)=>BigInt(a)>BigInt(b)?a:b,'0');
  return {reason:'',packet:{schema_version:'robot-scope.scene-packet.v1',canonical:true,
    invalidated_sources:Object.fromEntries(Object.entries({pose:'robot_pose',joints:'robot_pose',obstacles:'obstacle_frame',global_path:'global_path',local_trajectory:'controller_local_trajectory','costmap:0':'costmap_snapshot',collision:'collision_assessment'}).filter(([,slot])=>wire.schema_version==='0.2' && wire.sources?.[slot]?.status!=='ready' && Number.isSafeInteger(wire.sources?.[slot]?.sequence)).map(([slot,source])=>[slot,wire.sources[source]])),
    invalidated_assessment:!wire.collision_assessment && (wire.sources?.collision_assessment?.health?.state==='REFERENCE_OR_VALIDITY_UNKNOWN' || wire.schema_version==='0.2' && ['expired','unavailable'].includes(wire.sources?.collision_assessment?.status)) ? {source_epoch:wire.sources.collision_assessment.source_epoch,sequence:wire.sources.collision_assessment.sequence} : null,
    source_mode:'ACTUAL_C1_SERVICE',evidence_kind:wire.evidence_kind,producer:wire.producer,sequence:wire.sequence,
    source_epoch:context.source_epoch,stream_epoch:wire.stream_epoch,stamp_ns:newest,clock_domain:context.clock_domain,
    map_identity:{...context},calibration_id:context.calibration_id,provenance:{c1_source_epoch:wire.source_epoch},
    robot_pose:pose,joint_state:joints,obstacle_frame:obstacles,global_path:path,local_trajectory:local,
    costmaps:costmap?[costmap]:[],collision_assessment:assessment,sources:sensors,
    availability:{reference_cloud:displayAssets.some(a=>a.status==='READY' && a.ref.role==='saved_reference_cloud' && sameBinding(a.value?.map_binding,wire.map_binding))?'SUPPLIED_DISPLAY_ASSET':'UNAVAILABLE',sensor_clouds:sensors.length?'SUPPLIED_SYNTHETIC_OR_REPLAY':'UNAVAILABLE',sensor_origins:sensors.some(s=>s.origin_m)?'SUPPLIED':'UNAVAILABLE',
      bulk_references:wire.schema_version==='0.2'?'C1_AUTHENTICATED_ASSETS':'NO_C1_RESOLVER_CONTRACT',asset_count:wire.sources?.assets?.length || 0,
      source_status:wire.schema_version==='0.2'?Object.fromEntries(Object.entries(wire.sources || {}).filter(([k])=>k!=='assets').map(([k,v])=>[k,v.status])):null,
      collision:wire.sources?.collision_assessment?.health ?? null,errors}}};
}
