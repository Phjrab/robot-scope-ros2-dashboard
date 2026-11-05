// Display profile only. No classification, state owner, transport or collision geometry.
export const CONE_PROFILE = 'cone-flat-demo.v1';
export function coneDimensions(object) {
  const p=object?.provenance,g=object?.geometry;
  if(p?.display_profile!==CONE_PROFILE || p.position_basis!=='FLAT_DEMO_ONLY'
    || p.geometry_usage!=='DISPLAY_ONLY' || object.class_name!=='traffic_cone')return null;
  const r=p.radius_m,h=p.height_m;
  if(typeof r!=='number'||typeof h!=='number'||!Number.isFinite(r)||!Number.isFinite(h)
    ||r<.01||r>2||h<.01||h>3||!g
    ||g.extent_m[0]!==2*r||g.extent_m[1]!==2*r||g.extent_m[2]!==h
    ||g.orientation_xyzw.some((v,i)=>v!==[0,0,0,1][i])||g.center_m[2]!==h/2)return null;
  return {radius:r,height:h};
}
export function coneStatus(view,enabled) {
  const display=view.availability?.obstacle_display;
  if(display?.display_profile!==CONE_PROFILE)return 'CONES · UNAVAILABLE · PAIRED_REAL_PRODUCER_INPUT_REQUIRED';
  const layer=view.obstacles;
  const source=view.evidence_kind==='SYNTHETIC'?'SIMULATED':view.evidence_kind||'UNKNOWN';
  const freshness=layer?.value&&!layer.value.suppressed&&source==='SIMULATED'?'VALID':/STALE|EXPIRED|INVALIDATED/.test(layer?.reason||'')?'STALE':'UNAVAILABLE';
  const aligned=source==='SIMULATED'&&view.map_identity?.space_kind==='ISOLATED_SIMULATION'&&view.map_identity?.map_id==='c0dec0dec0dec0dec0dec0de';
  const count=freshness==='VALID' ? layer.value.obstacles.length : '—';
  return `CONES ${enabled?'ON':'OFF'} · ${source} · ${freshness} · ${aligned?'ISOLATED_DEMO_ONLY':'UNALIGNED'} · FLAT_DEMO_ONLY / HEIGHT_UNVERIFIED · ${count}개 · frame ${view.map_identity?.frame_id||'UNKNOWN'} · 실제 위치·주행 안전 미검증`;
}
