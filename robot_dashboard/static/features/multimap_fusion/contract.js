// C2 wire contract and UI geometry only. No registration / sensor / collision solver.
export const SCHEMA = 'robot-scope.multimap-ui.v1';
export const CONVENTION = 'row-major,column-vector,p_fused=T_fused_source@p_source';
export const MAX_PREVIEW_POINTS = 6000;
export const MAX_SOURCES = 8;
export const identity = () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
export const clone = (v) => JSON.parse(JSON.stringify(v));
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const text = (v) => typeof v === 'string' && v.length > 0 && v.length <= 256;
export function sourceDescriptor(s) {
  if (!s || s.kind !== 'pointcloud3d' || !text(s.id) || !text(s.name) || !text(s.session_id)
      || !((typeof s.revision==='string'&&text(s.revision))||(Number.isSafeInteger(s.revision)&&s.revision>=0)) || !/^[a-f0-9]{64}$/.test(s.sha256 || '')
      || !text(s.frame_id) || s.units !== 'm' || !Number.isSafeInteger(s.point_count) || s.point_count < 0)
    throw new Error('Unsupported source descriptor: require 3D ID/session/revision/hash/frame/count and meters.');
  if (s.ancestors != null && (!Array.isArray(s.ancestors) || s.ancestors.length > 1024 || s.ancestors.some(v => !text(v))))
    throw new Error('Unsupported ancestor list.');
  return { id:s.id, name:s.name, kind:s.kind, session_id:s.session_id, revision:s.revision,
    sha256:s.sha256, frame_id:s.frame_id, units:'m', point_count:s.point_count,
    axes_verified:s.axes_verified === true, ancestors:[...(s.ancestors || [])],
    ...(s.wire_descriptor ? {wire_descriptor:clone(s.wire_descriptor)} : {}) };
}
export const pin = (s) => ({id:s.id, session_id:s.session_id, revision:s.revision, sha256:s.sha256});
export const pinsEqual = (a,b) => JSON.stringify(a) === JSON.stringify(b);
export function rigidMatrix(m) {
  if (!Array.isArray(m) || m.length !== 16 || !m.every(finite)
      || [m[12],m[13],m[14],m[15]-1].some(v => Math.abs(v)>1e-7)) throw new Error('Invalid rigid transform / convention.');
  const rows = [m.slice(0,3),m.slice(4,7),m.slice(8,11)];
  const dot=(a,b)=>a.reduce((v,x,i)=>v+x*b[i],0);
  if (rows.some((r,i)=>Math.abs(dot(r,r)-1)>1e-4 || rows.some((s,j)=>i!==j && Math.abs(dot(r,s))>1e-4)))
    throw new Error('Scale / non-orthogonal transform rejected.');
  const det=m[0]*(m[5]*m[10]-m[6]*m[9])-m[1]*(m[4]*m[10]-m[6]*m[8])+m[2]*(m[4]*m[9]-m[5]*m[8]);
  if (Math.abs(det-1)>1e-4) throw new Error('Reflected axes rejected.');
  return m.slice();
}
export function poseMatrix({x=0,y=0,z=0,roll=0,pitch=0,yaw=0}={}) {
  if (![x,y,z,roll,pitch,yaw].every(finite)) throw new Error('Pose must use finite meters / radians.');
  const a=Math.cos(yaw),b=Math.sin(yaw),c=Math.cos(pitch),d=Math.sin(pitch),e=Math.cos(roll),f=Math.sin(roll);
  return [a*c,a*d*f-b*e,a*d*e+b*f,x, b*c,b*d*f+a*e,b*d*e-a*f,y, -d,c*f,c*e,z, 0,0,0,1];
}
export const transformPoint = (m,p) => [0,1,2].map(r=>m[r*4]*p[0]+m[r*4+1]*p[1]+m[r*4+2]*p[2]+m[r*4+3]);
export function boundedPreview(payload, source, limit=MAX_PREVIEW_POINTS) {
  if (payload?.schema !== SCHEMA || !pinsEqual(payload.input_pin,pin(source)) || payload.units !== 'm'
      || !Array.isArray(payload.points) || payload.points.length % 3 || payload.points.length > 3_000_000)
    throw new Error('Unsupported or stale preview schema.');
  const count=payload.points.length/3, stride=Math.max(1,Math.ceil(count/limit)), points=[];
  for (let i=0;i<payload.points.length;i+=3*stride) {
    const p=payload.points.slice(i,i+3);
    if (!p.every(finite)) throw new Error('Non-finite preview point.');
    points.push(p);
  }
  return {points,sampled:true,source_points:source.point_count};
}
export function validateCorrespondences(pairs) {
  if (!pairs.length) return ['No 3D correspondences; server must assess ambiguity.'];
  if (pairs.length < 3) throw new Error('At least 3 non-collinear XYZ pairs required.');
  for (const field of ['source_xyz','anchor_xyz']) {
    const pts=pairs.map(p=>p[field]);
    if (pts.some(p=>!Array.isArray(p)||p.length!==3||!p.every(finite))) throw new Error('XYZ triples must be finite.');
    let spread=0, area=0;
    for (let i=1;i<pts.length;i++) for(let j=i+1;j<pts.length;j++) {
      const a=pts[i].map((v,k)=>v-pts[0][k]),b=pts[j].map((v,k)=>v-pts[0][k]);
      spread=Math.max(spread,Math.hypot(...a),Math.hypot(...b));
      area=Math.max(area,Math.hypot(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]));
    }
    if (spread<0.1 || area<0.01*spread*spread) throw new Error('Correspondences are collinear or insufficiently dispersed.');
    if (pts.some((p,i)=>pts.some((q,j)=>j<i && Math.hypot(...p.map((v,k)=>v-q[k]))<0.01)))
      throw new Error('Duplicate / clustered correspondence points.');
  }
  return pairs.length<4 ? ['Add a fourth dispersed pair to check ambiguity.'] : [];
}
export function selectionWarnings(sources) {
  const warnings=['Independent session origins even when frame names match. Identity guesses and scale are unverified.'];
  if(sources.some(s=>!s.axes_verified)) warnings.push('Unverified source axes: inspect orientation and units.');
  const revisions=new Set(), ancestry=new Set();
  for(const s of sources) {
    const key=`${s.session_id}:${s.revision}:${s.sha256}`;
    if(revisions.has(key)) warnings.push(`Duplicate revision input: ${s.name}`);
    revisions.add(key);
    for(const a of [s.id,...s.ancestors]) { if(ancestry.has(a)) warnings.push(`Duplicate ancestor: ${a}`); ancestry.add(a); }
  }
  return warnings;
}
// One uniformly scaled, rotated XY projection in CSS pixels; +Y points up.
export function xyProjection(bounds,width,height,rotation=0) {
  const c=Math.cos(rotation),s=Math.sin(rotation),cx=(bounds.min[0]+bounds.max[0])/2,cy=(bounds.min[1]+bounds.max[1])/2;
  const corners=[[bounds.min[0],bounds.min[1]],[bounds.max[0],bounds.min[1]],[bounds.max[0],bounds.max[1]],[bounds.min[0],bounds.max[1]]];
  const r=corners.map(([x,y])=>[c*(x-cx)-s*(y-cy),s*(x-cx)+c*(y-cy)]);
  const scale=Math.min(Math.max(1,width-64)/Math.max(1,...r.map(p=>p[0]))/2, Math.max(1,height-64)/Math.max(1,...r.map(p=>p[1]))/2);
  return {scale,project:([x,y])=>[width/2+(c*(x-cx)-s*(y-cy))*scale,height/2-(s*(x-cx)+c*(y-cy))*scale],
    delta:(dx,dy)=>[(c*dx-s*dy)/scale,(-s*dx-c*dy)/scale]};
}
export function createHttpPorts(request,basePath='/api/v1/extensions/multimap') {
  if(typeof request!=='function' || !/^\/api\/v1\/extensions\/multimap\/?$/.test(basePath)) throw new Error('Extension-only base required.');
  const base=basePath.replace(/\/$/,''),get=p=>request(base+p,{method:'GET'}),post=(p,body)=>request(base+p,{method:'POST',body});
  const id=v=>{if(!text(v))throw new Error('Identity required.');return encodeURIComponent(v);};
  return {catalogue:{list:()=>get('/sources'),preview:s=>get(`/sources/${id(s.id)}/preview?revision=${id(String(s.revision))}`)},
    jobs:{start:body=>post('/jobs',body),get:job=>get(`/jobs/${id(job)}`),cancel:job=>post(`/jobs/${id(job)}/cancel`,{}),
      accept:body=>post(`/proposals/${id(body.proposal_id)}/review`,body),save:body=>post('/exports',body)}};
}
