// Consumer mapping for C1 0.1 + explicit C3 display payload. The caller MUST run
// the pinned C1 validator first. This is not a wire validator or TF resolver.
export function adaptC1ScenePacket(wire, context) {
  const failure = reason => ({ packet: null, reason });
  if (wire?.schema_version !== '0.1') return failure('C1_VERSION_UNSUPPORTED');
  const binding = wire.map_binding;
  if (!binding || binding.map_id !== context?.map_id || binding.revision !== context.revision
    || binding.generation !== context.generation) return failure('C1_MAP_GENERATION_MISMATCH');
  const display = wire.sources?.display;
  if (display?.schema_version !== 'robot-scope.c3-display.v1') return failure('C1_DISPLAY_PROFILE_REQUIRED');
  if (!display.stamp_ns || !display.clock_domain) return failure('C1_SOURCE_TIME_MAPPING_REQUIRED');
  function observation(value) {
    if (!value) return null;
    if (value.frame_key?.frame_id !== context.frame_id || value.frame_key?.source_epoch !== context.source_epoch
      || value.map_binding?.map_id !== binding.map_id || value.map_binding?.revision !== binding.revision
      || value.map_binding?.generation !== binding.generation) return null;
    return { ...value, frame_key: { map_id:binding.map_id,revision:binding.revision,frame_id:value.frame_key.frame_id } };
  }
  const pose = observation(wire.robot_pose), joints = observation(display.joint_state);
  const obstacles = observation(wire.obstacle_frame);
  let assessment = observation(wire.collision_assessment);
  if (assessment) {
    const contact = ['MODEL_OVERLAP','PREDICTED_COLLISION','CONTACT_UNCONFIRMED'].includes(assessment.reason)
      ? assessment.reason : 'CONTACT_UNCONFIRMED';
    assessment = { ...assessment, calibration_id:display.calibration_id,
      robot_pose_ref:assessment.robot_pose_ref?.ref, joint_state_ref:assessment.joint_state_ref?.ref,
      obstacle_frame_ref:assessment.obstacle_frame_ref?.sequence, path_ref:assessment.path_ref?.generation ?? null,
      min_clearance_m:assessment.min_clearance, modeled_ttc_s:assessment.modeled_ttc,
      contact_state:contact, valid_until_ns:assessment.validity_interval?.valid_until_ns,
      envelopes:[...(assessment.padded_envelope?.envelopes || []),...(assessment.unpadded_envelope?.envelopes || [])] };
  }
  return { reason:'', packet:{ schema_version:'robot-scope.scene-packet.v1', evidence_kind:wire.evidence_kind,
    producer:wire.producer, sequence:wire.sequence, source_epoch:wire.source_epoch, stream_epoch:wire.stream_epoch,
    stamp_ns:display.stamp_ns, clock_domain:display.clock_domain, calibration_id:display.calibration_id,
    map_identity:{map_id:binding.map_id,revision:binding.revision,frame_id:context.frame_id,units:context.units},
    provenance:display.provenance, robot_pose:pose,joint_state:joints,obstacle_frame:obstacles,
    sources:Array.isArray(display.sensors) ? display.sensors.map(observation).filter(Boolean) : [],
    global_path:observation(wire.global_path),local_trajectory:observation(wire.controller_local_trajectory),
    costmaps:wire.costmap_snapshot ? [observation(wire.costmap_snapshot)].filter(Boolean) : [], collision_assessment:assessment } };
}
