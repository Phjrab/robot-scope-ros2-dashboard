// Display consumer guards only. C1 owns wire validation; inject its validator at
// the subscription boundary. No transport, TF lookup, fusion or collision work.
export const LIMITS = Object.freeze({ sources: 4, points: 4096, objects: 128,
  pathPoints: 2048, pathHistory: 3, costCells: 4096, primitives: 64, inspectorChars: 12000 });
export const TTL_MS = Object.freeze({ source: 1200, pose: 500, joints: 1200,
  obstacles: 1200, path: 5000, costmap: 1500, collision: 500, skew: 250 });
const text = value => typeof value === 'string' ? value.slice(0, 256) : '';
const finite = x => typeof x === 'number' && Number.isFinite(x);
const vector = (v, n) => Array.isArray(v) && v.length === n && v.every(finite);
const stamp = x => typeof x === 'string' && /^(0|[1-9]\d{0,24})$/.test(x);
const sequence = x => Number.isSafeInteger(x) && x >= 0;
const quaternion = q => vector(q, 4) && Math.abs(Math.hypot(...q) - 1) < 0.001;
const key = c => c ? [c.map_id, c.revision, c.frame_id, c.source_epoch,
  c.stream_epoch, c.clock_domain, c.calibration_id, c.units, c.generation].join('|') : '';
const mapMatches = (a, b) => a && b && ['map_id', 'revision', 'frame_id'].every(k => a[k] === b[k]);
const withinSkew = values => values.every(a => values.every(b => {
  const delta = BigInt(a.stamp_ns) - BigInt(b.stamp_ns);
  return delta <= BigInt(TTL_MS.skew) * 1000000n && delta >= -BigInt(TTL_MS.skew) * 1000000n;
}));
const contextValid = c => c && ['map_id', 'revision', 'frame_id', 'source_epoch',
  'stream_epoch', 'clock_domain', 'calibration_id'].every(k => text(c[k])) && c.units === 'm';
const strings = value => Array.isArray(value) ? value.slice(0, 8).map(text) : [];
const metadata = value => ({ producer: text(value.producer), evidence_kind: text(value.evidence_kind),
  stamp_ns: text(value.stamp_ns), clock_domain: text(value.clock_domain), source_epoch: text(value.source_epoch),
  calibration_id: text(value.calibration_id), sequence: value.sequence,
  frame_key: value.frame_key ? { map_id: text(value.frame_key.map_id), revision: text(value.frame_key.revision), frame_id: text(value.frame_key.frame_id) } : null,
  provenance: value.canonical ? structuredClone(value.provenance) : strings(value.provenance),
  sensor_age_ms: value.sensor_age_ms ?? null, host_clock_id: text(value.host_clock_id), receipt_source_ns: text(value.receipt_source_ns) });
function copyGeometry(g) {
  if (!g || !vector(g.center_m, 3) || !vector(g.extent_m, 3)
    || !g.extent_m.every(x => x > 0) || !quaternion(g.orientation_xyzw)) return null;
  return { center_m: g.center_m.slice(), extent_m: g.extent_m.slice(), orientation_xyzw: g.orientation_xyzw.slice() };
}
function points(value, limit, dimensions = 3) {
  return Array.isArray(value) && value.length <= limit && value.every(p => vector(p, dimensions))
    ? value.map(p => p.slice()) : null;
}

export function createSceneConsumer({ getMap, clock = () => performance.now() }) {
  if (typeof getMap !== 'function') throw new TypeError('getMap must return trusted display context');
  let context = null, contextKey = '', latest = null, history = [], lastSequence = -1;
  let offeredSequence = -1, offeredStamp = null, lastArrival = null;
  const anchors = new Map(), geometryCache = new Map(); let geometryCopies = 0;
  let retiredCollisionSequence = -1;
  const retiredSources = new Map();
  let protection = {mode:'UNAVAILABLE',transition:'',recommendation:'UNAVAILABLE'};
  let destroyed = false, receipt = 0, error = 'WAITING', accepted = 0, rejected = 0, resets = 0;
  function syncContext() {
    const next = getMap();
    const nextKey = contextValid(next) ? key(next) : '';
    if (nextKey !== contextKey || !nextKey && latest) {
      contextKey = nextKey; context = nextKey ? { ...next } : null;
      latest = null; history = []; lastSequence = -1; offeredSequence = -1; offeredStamp = null; lastArrival = null; anchors.clear(); geometryCache.clear(); retiredSources.clear(); retiredCollisionSequence=-1; protection={mode:'UNAVAILABLE',transition:'',recommendation:'UNAVAILABLE'}; resets++; error = 'CONTEXT_CHANGED';
      return true;
    }
    context = nextKey ? { ...next } : null;
    return false;
  }
  function reject(reason) { rejected++; error = reason; return false; }
  function guard(value, packet, ttl, requireCalibration = false) {
    if (!value) return 'MISSING';
    if (value.canonical && (!finite(value.age_ms) || value.age_ms < 0)) return 'HOST_AGE_UNKNOWN';
    if (!mapMatches(value.frame_key, context)) return 'FRAME_OR_MAP_MISMATCH';
    if (value.source_epoch !== context.source_epoch) return 'EPOCH_MISMATCH';
    if (value.clock_domain !== context.clock_domain || !stamp(value.stamp_ns)) return 'CLOCK_UNKNOWN';
    if (requireCalibration && value.calibration_id !== context.calibration_id) return 'CALIBRATION_MISMATCH';
    const delta = BigInt(packet.stamp_ns) - BigInt(value.stamp_ns);
    if (delta < 0n) return 'FUTURE_STAMP';
    if (delta > BigInt(ttl) * 1000000n) return 'STALE';
    return '';
  }
  function layer(value, packet, ttl, calibration, copy, slot) {
    const retired = retiredSources.get(slot.startsWith('sensor:')?'obstacles':slot);
    if (packet.canonical && retired && (!value || value.sequence <= retired.sequence)) return {value:null,reason:value?'SERVER_INVALIDATED':`SERVER_${retired.status.toUpperCase()}`,ttl};
    const reason = guard(value, packet, ttl, calibration);
    if (reason) return { value: null, reason, ttl };
    let age = Number(BigInt(packet.stamp_ns) - BigInt(value.stamp_ns)) / 1e6;
    let copied;
    if (packet.canonical) {
      const id = slot;
      const previous = anchors.get(id);
      age = Math.max(age, value.age_ms, previous?.stamp === value.stamp_ns ? previous.age + Math.max(0,receipt-previous.receipt) : 0);
      anchors.set(id,{stamp:value.stamp_ns,age,receipt});
      const revision = `${value.source_epoch}:${value.producer}:${value.id || ''}:${value.sequence}`;
      const cached = geometryCache.get(id);
      copied = id !== 'collision' && cached?.revision === revision ? cached.value : copy(value);
      if (cached?.revision !== revision) { geometryCopies++; geometryCache.set(id,{revision,value:copied}); }
    } else copied = copy(value);
    return { value: copied, reason: copied ? '' : 'GEOMETRY_OR_LIMIT_INVALID', ttl,
      age_ms: age, receipt, canonical: packet.canonical === true };
  }
  // Observe arrivals even while presentation is paused. This is metadata only:
  // no geometry copies or hidden replay queue. A newer offer invalidates its token.
  function offer(packet) {
    if (destroyed) return false;
    syncContext();
    if (!context) return reject('CONTEXT_UNAVAILABLE');
    if (!packet || packet.schema_version !== 'robot-scope.scene-packet.v1'
      || !['SYNTHETIC', 'REPLAY', 'LIVE'].includes(packet.evidence_kind)
      || !sequence(packet.sequence) || !stamp(packet.stamp_ns)) return reject('PACKET_INVALID');
    if (!mapMatches(packet.map_identity, context) || packet.map_identity.units !== 'm') return reject('MAP_OR_UNITS_MISMATCH');
    if (packet.canonical && packet.map_identity.generation !== context.generation) return reject('MAP_GENERATION_MISMATCH');
    if (packet.source_epoch !== context.source_epoch || packet.stream_epoch !== context.stream_epoch) return reject('LATE_EPOCH_OR_STREAM');
    if (packet.clock_domain !== context.clock_domain) return reject('CLOCK_MISMATCH');
    if (packet.sequence < offeredSequence || packet.sequence === offeredSequence && !packet.canonical) return reject('OUT_OF_ORDER');
    if (offeredStamp && packet.stamp_ns !== '0' && BigInt(packet.stamp_ns) < BigInt(offeredStamp)) return reject('STAMP_ROLLBACK');
    const receivedAt = clock();
    offeredSequence = packet.sequence; if (packet.stamp_ns !== '0') offeredStamp = packet.stamp_ns;
    for (const [slot,source] of Object.entries(packet.invalidated_sources || {})) {
      if (source.source_epoch === context.source_epoch && sequence(source.sequence) && ['expired','unavailable','pending'].includes(source.status)
        && source.sequence >= (retiredSources.get(slot)?.sequence ?? -1)) retiredSources.set(slot,{sequence:source.sequence,status:source.status});
    }
    if (packet.canonical && packet.invalidated_assessment?.source_epoch === context.source_epoch
      && sequence(packet.invalidated_assessment.sequence)) retiredCollisionSequence=Math.max(retiredCollisionSequence,packet.invalidated_assessment.sequence);
    if (packet.canonical) {
      const slots = [
        ['pose',packet.robot_pose,TTL_MS.pose,true], ['joints',packet.joint_state,TTL_MS.joints,true],
        ['obstacles',packet.obstacle_frame,TTL_MS.obstacles,true],
        ['global_path',packet.global_path,TTL_MS.path,false], ['local_trajectory',packet.local_trajectory,TTL_MS.path,false],
        ['collision',packet.collision_assessment,TTL_MS.collision,true],
        ...(Array.isArray(packet.sources) ? packet.sources : []).slice(0,LIMITS.sources).map((v,i)=>[`sensor:${i}`,v,TTL_MS.source,true]),
        ...(Array.isArray(packet.costmaps) ? packet.costmaps : []).slice(0,2).map((v,i)=>[`costmap:${i}`,v,TTL_MS.costmap,false]),
      ];
      for (const [slot,value,ttl,calibration] of slots) {
        if (guard(value,packet,ttl,calibration)) continue;
        const previous=anchors.get(slot);
        const age=Math.max(Number(BigInt(packet.stamp_ns)-BigInt(value.stamp_ns))/1e6,value.age_ms,
          previous?.stamp===value.stamp_ns ? previous.age+Math.max(0,receivedAt-previous.receipt) : 0);
        anchors.set(slot,{stamp:value.stamp_ns,age,receipt:receivedAt});
        if (slot==='collision' && finite(value.remaining_ms) && value.remaining_ms>=0) {
          const previousExpiry=anchors.get('collision-expiry');
          anchors.set('collision-expiry',{stamp:value.stamp_ns,expires:Math.min(receivedAt+value.remaining_ms,
            previousExpiry?.stamp===value.stamp_ns ? previousExpiry.expires : Infinity)});
        }
      }
    }
    lastArrival = Object.freeze({receivedAt,contextKey,packet});
    return lastArrival;
  }
  function ingest(packet, arrival = null) {
    if (destroyed) return false;
    syncContext();
    arrival ||= offer(packet);
    if (!arrival) return false;
    if (arrival!==lastArrival || arrival.packet!==packet || arrival.contextKey!==contextKey) return reject('SUPERSEDED_ARRIVAL');
    receipt = arrival.receivedAt; lastArrival = null;
    const pose = layer(packet.robot_pose, packet, TTL_MS.pose, true, v =>
      vector(v.position_m, 3) && vector(v.rpy_rad, 3) && text(v.ref)
        ? { ...metadata(v), ref: text(v.ref), position_m: v.position_m.slice(), rpy_rad: v.rpy_rad.slice() } : null, 'pose');
    const joints = layer(packet.joint_state, packet, TTL_MS.joints, true, v =>
      text(v.ref) && v.positions_rad && Object.keys(v.positions_rad).length === 12
        && ['FR', 'FL', 'RR', 'RL'].every(leg => ['hip', 'thigh', 'calf'].every(j => finite(v.positions_rad[`${leg}_${j}_joint`])))
        ? { ...metadata(v), ref: text(v.ref), positions_rad: { ...v.positions_rad } } : null, 'joints');
    const sources = [];
    if (Array.isArray(packet.sources) && packet.sources.length <= LIMITS.sources) {
      for (const source of packet.sources) {
        const normalized = layer(source, packet, TTL_MS.source, true, v => {
          const xyz = points(v.points_m, LIMITS.points);
          return xyz ? { ...metadata(v), id: text(v.id), kind: text(v.kind), points_m: xyz, origin_m: vector(v.origin_m,3) ? v.origin_m.slice() : null, health: text(v.health) } : null;
        }, `sensor:${sources.length}`);
        sources.push({ id: text(source.id), kind: text(source.kind), ...normalized });
      }
    }
    const sourceHealthy = id => sources.some(s => s.id === id && s.value && s.value.health === 'OK');
    const obstacles = layer(packet.obstacle_frame, packet, TTL_MS.obstacles, true, v => {
      if (!Array.isArray(v.obstacles) || v.obstacles.length > LIMITS.objects) return null;
      const objects = [];
      for (const o of v.obstacles) {
        const geometry = copyGeometry(o.geometry);
        const support = strings(o.sensor_support);
        if (!geometry || !text(o.track_id) || !support.length || (!v.canonical && !support.every(sourceHealthy))
          || !['OBSERVED', 'OCCLUDED', 'STALE'].includes(o.state)) continue;
        const supported = sources.filter(s => support.includes(s.id) && s.value);
        if (!withinSkew([v, ...supported.map(s => s.value)])) continue;
        objects.push({ track_id: text(o.track_id), class_name: text(o.class_name) || 'unknown',
          class_score: finite(o.class_score) ? o.class_score : null, state: o.state,
          novelty: text(o.novelty), sensor_support: support, geometry, provenance: v.canonical ? structuredClone(o.provenance) : strings(o.provenance) });
      }
      return { ...metadata(v), obstacles: objects,
        suppressed: v.obstacles.length - objects.length, published_to_nav2: v.published_to_nav2 === true,
        costmap_ingestion_observed: v.costmap_ingestion_observed === true,
        controller_consumption_observed: v.controller_consumption_observed === true, canonical:v.canonical };
    }, 'obstacles');
    function copyPath(v) {
      const xyz = points(v.points_m, LIMITS.pathPoints, v.dimensions === 2 ? 2 : 3);
      if (!xyz || !text(v.generation) || ![2,3].includes(v.dimensions)
        || !['2D_GROUND_PLANE', 'XYZ'].includes(v.representation)
        || (v.dimensions === 2 && (v.representation !== '2D_GROUND_PLANE' || !finite(v.plane_z_m)))) return null;
      return { ...metadata(v), generation: text(v.generation), reason: text(v.replanning_reason),
        representation: v.representation, points_m: xyz.map(p => p.length === 2 ? [p[0], p[1], v.plane_z_m] : p) };
    }
    const path = layer(packet.global_path, packet, TTL_MS.path, false, copyPath, 'global_path');
    const local = layer(packet.local_trajectory, packet, TTL_MS.path, false, copyPath, 'local_trajectory');
    const costmaps = [];
    for (const value of Array.isArray(packet.costmaps) ? packet.costmaps.slice(0, 2) : []) {
      costmaps.push(layer(value, packet, TTL_MS.costmap, false, v => {
        if (v.cell_encoding && !['OCCUPANCY_PERCENT','NAV2_COST_0_255'].includes(v.cell_encoding)) return null;
        if (!sequence(v.width) || !sequence(v.height) || !v.width || !v.height || v.width * v.height > LIMITS.costCells
          || !vector(v.origin, 3) || !finite(v.resolution_m) || v.resolution_m <= 0 || !finite(v.plane_z_m)
          || v.representation !== '2D_GROUND_PLANE' || !Array.isArray(v.cells)
          || v.cells.length !== v.width * v.height || !v.cells.every(x => Number.isInteger(x) && x >= -1 && x <= (v.cell_encoding === 'OCCUPANCY_PERCENT' ? 100 : 255))) return null;
        return { ...metadata(v), id: text(v.id), width: v.width, height: v.height, origin: v.origin.slice(),
          resolution_m: v.resolution_m, plane_z_m: v.plane_z_m, representation: v.representation, cell_encoding:v.cell_encoding || 'NAV2_COST_0_255', cells: v.cells.slice() };
      }, `costmap:${costmaps.length}`));
    }
    let collision = layer(packet.collision_assessment, packet, TTL_MS.collision, true, v => {
      if (v.canonical) {
        if (v.sequence <= retiredCollisionSequence || !['CLEAR','CAUTION','STOP_REQUIRED','UNKNOWN'].includes(v.severity) || !v.references_verified
          || !finite(v.remaining_ms) || v.remaining_ms < 0 || !pose.value || !joints.value || !obstacles.value) return null;
        return {...metadata(v), canonical:true, severity:v.severity,reason:text(v.reason),contact_state:v.contact_state,
          min_clearance_m:v.min_clearance_m,modeled_ttc_s:v.modeled_ttc_s,robot_geometry_hash:v.robot_geometry_hash,
          validity_interval:structuredClone(v.validity_interval),freshness:structuredClone(v.freshness),
          coverage:structuredClone(v.coverage),protection_mode:v.protection_mode,recommendation:v.recommendation,
          padded_envelope:structuredClone(v.padded_envelope),unpadded_envelope:structuredClone(v.unpadded_envelope),
          envelopes:[],envelope_geometry_status:v.envelope_geometry_status};
      }
      if (!['CLEAR', 'CAUTION', 'STOP_REQUIRED', 'UNKNOWN'].includes(v.severity)
        || !['MODEL_OVERLAP', 'PREDICTED_COLLISION', 'CONTACT_UNCONFIRMED'].includes(v.contact_state)
        || !text(v.robot_geometry_hash) || !pose.value || !joints.value || !obstacles.value
        || v.robot_pose_ref !== pose.value.ref || v.joint_state_ref !== joints.value.ref
        || v.obstacle_frame_ref !== obstacles.value.sequence || obstacles.value.suppressed
        || v.path_ref !== (path.value?.generation ?? null)
        || !withinSkew([v, pose.value, joints.value, obstacles.value])
        || !stamp(v.valid_until_ns) || BigInt(v.valid_until_ns) < BigInt(packet.stamp_ns)
        || !Array.isArray(v.envelopes) || v.envelopes.length > LIMITS.primitives) return null;
      const envelopes = v.envelopes.map(e => ({ id: text(e.id), kind: text(e.kind), geometry: copyGeometry(e.geometry) }));
      if (envelopes.some(e => !e.geometry)) return null;
      return { ...metadata(v), severity: v.severity, reason: text(v.reason), contact_state: v.contact_state,
        robot_pose_ref: text(v.robot_pose_ref), joint_state_ref: text(v.joint_state_ref), obstacle_frame_ref: v.obstacle_frame_ref,
        path_ref: text(v.path_ref), robot_geometry_hash: text(v.robot_geometry_hash), valid_until_ns: v.valid_until_ns,
        min_clearance_m: finite(v.min_clearance_m) ? v.min_clearance_m : null,
        modeled_ttc_s: finite(v.modeled_ttc_s) ? v.modeled_ttc_s : null, envelopes };
    }, 'collision');
    if (packet.canonical && packet.collision_assessment?.sequence <= retiredCollisionSequence) collision={value:null,reason:'SERVER_INVALIDATED',ttl:TTL_MS.collision};
    if (packet.canonical && collision.value) {
      const previous = anchors.get('collision-expiry'), value=packet.collision_assessment;
      collision.expires = Math.min(receipt + value.remaining_ms, previous?.stamp === value.stamp_ns ? previous.expires : Infinity);
      anchors.set('collision-expiry',{stamp:value.stamp_ns,expires:collision.expires});
    }
    if (!pose.value || !joints.value || obstacles.value?.suppressed) collision = { value: null, reason: 'POSE_JOINT_OR_SOURCE_INSUFFICIENT', ttl: TTL_MS.collision };
    if (path.value && history.at(-1)?.value.generation !== path.value.generation) {
      history = history.filter(p => p.value.generation !== path.value.generation);
      history.push(path); history = history.slice(-LIMITS.pathHistory);
    }
    const mode=packet.collision_assessment?.protection_mode;
    if (packet.canonical && ['ADVISORY_ONLY','ACTIVE_CONSTRAINT'].includes(mode)) {
      const transition=protection.mode==='ACTIVE_CONSTRAINT' && mode==='ADVISORY_ONLY' ? 'REPORTED_DOWNGRADE_REQUIRES_HOST_CONFIRMATION' : protection.transition;
      protection={mode,transition,recommendation:packet.collision_assessment.recommendation};
    }
    latest = { ...metadata(packet), sequence: packet.sequence, stream_epoch: text(packet.stream_epoch),
      protection:{...protection}, source_mode:packet.source_mode || 'FIXTURE', availability:packet.availability || null,
      map_identity: { ...context }, pose, joints, sources, obstacles, path, local, costmaps, collision };
    lastSequence = packet.sequence; error = ''; accepted++; return true;
  }
  function fresh(layer, now, slot) {
    const retired=retiredSources.get(slot?.startsWith('sensor:')?'obstacles':slot);
    if (layer?.canonical && layer.value && retired
      && layer.value.sequence<=retired.sequence) return {value:null,reason:'SERVER_INVALIDATED'};
    if (slot==='collision' && layer?.value?.canonical && layer.value.sequence<=retiredCollisionSequence)
      return {value:null,reason:'SERVER_INVALIDATED'};
    if (!layer?.value) return layer || { value: null, reason: 'MISSING' };
    const age_ms = layer.age_ms + Math.max(0, now - layer.receipt);
    return age_ms > layer.ttl ? { value: null, reason: 'STALE', age_ms } : { ...layer, age_ms };
  }
  function snapshot() {
    syncContext();
    if (!latest || destroyed) return { ready: false, reason: error || 'WAITING', contextKey, context, history: [] };
    const now = clock();
    const pose = fresh(latest.pose, now, 'pose'), joints = fresh(latest.joints, now, 'joints');
    if (pose.value && joints.value && !withinSkew([pose.value,joints.value])) {
      joints.value = null; joints.reason = 'POSE_JOINT_TIME_SKEW';
    }
    const sources = latest.sources.map((s,i) => ({ ...s, ...fresh(s, now, `sensor:${i}`) }));
    const obstacles = fresh(latest.obstacles, now, 'obstacles');
    if (obstacles.value) {
      const kept = obstacles.value.obstacles.filter(o => obstacles.value.canonical || o.sensor_support.every(id => sources.some(s => s.id === id && s.value)));
      obstacles.value = { ...obstacles.value, obstacles: kept, suppressed: obstacles.value.suppressed + obstacles.value.obstacles.length - kept.length };
    }
    let collision = fresh(latest.collision, now, 'collision');
    if (!pose.value || !joints.value || !obstacles.value || obstacles.value.suppressed) collision = { value: null, reason: 'POSE_JOINT_OR_SOURCE_INSUFFICIENT' };
    if (collision.value) {
      if (collision.value.canonical) {
        if (now > collision.expires) collision = {value:null,reason:'VALIDITY_EXPIRED'};
      } else {
      const remaining = Number(BigInt(collision.value.valid_until_ns) - BigInt(latest.stamp_ns)) / 1e6;
      if (now - receipt > remaining) collision = { value: null, reason: 'VALIDITY_EXPIRED' };
      }
    }
    return { ...latest, ready: true, contextKey, pose, joints, sources, obstacles, collision,
      path: fresh(latest.path, now, 'global_path'), local: fresh(latest.local, now, 'local_trajectory'), costmaps: latest.costmaps.map((c,i) => fresh(c, now, `costmap:${i}`)),
      history: history.map(p => fresh(p, now, 'global_path')).filter(p => p.value), lastRejection: error };
  }
  return { offer, ingest, snapshot, syncContext,
    diagnostics: () => ({ accepted, rejected, resets, history: history.length, retainedPackets: latest ? 1 : 0, lastSequence, error, geometryCopies, cachedLayers:geometryCache.size }),
    destroy() { destroyed = true; latest = null; lastArrival = null; history = []; anchors.clear(); geometryCache.clear(); retiredSources.clear(); } };
}
