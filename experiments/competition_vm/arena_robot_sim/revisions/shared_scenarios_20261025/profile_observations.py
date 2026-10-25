"""Bounded offline profile of static fence preparation vs current sensor update.

No planner loop or native integration. Cache demonstration belongs only to this
single pinned geometry invocation; observations are regenerated at each pose/time.
"""
from pathlib import Path
import json,time
import numpy as np
import export_fixtures as e
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    start=time.perf_counter();geometry=e.load_geometry(e.GEOMETRY_PATH);load_s=time.perf_counter()-start
    previous=e.base.sim.geometry
    try:
        e.base.sim.geometry=geometry
        start=time.perf_counter();static=e.base.sim.mesh([]);static_s=time.perf_counter()-start
    finally:e.base.sim.geometry=previous
    scene=e.scenes()['feasible1'];samples=[]
    for stamp,pose in [(0.,scene['start']),(.2,[scene['start'][0],scene['start'][1]+.032,scene['start'][2]]),(.4,[scene['start'][0],scene['start'][1]+.064,scene['start'][2]])]:
        start=time.perf_counter()
        active=[c for c in scene['cones'] if stamp>=c['appears_s']]
        dynamic=np.asarray([t for c in active for t in e.base.sim.cone_mesh(c)],float)
        mesh=np.concatenate((static,dynamic)) if len(dynamic) else static
        update_s=time.perf_counter()-start
        start=time.perf_counter();ranges,_=e.base.sim.raycast(mesh,pose);sensor_s=time.perf_counter()-start
        expected=e.observe(scene,pose,stamp)
        equal=ranges.tolist()==expected['ranges_m'];assert equal
        samples.append(dict(source_stamp_s=stamp,pose=pose,dynamic_triangle_assembly_s=update_s,current_pose_raycast_s=sensor_s,ranges_equal_to_exporter=equal,ranges_sha256=e.digest(ranges.tolist())))
    report=dict(scope='OFFLINE_STATIC_PREPARATION_VS_CURRENT_SENSOR_UPDATE',scene_sha256=e.digest(scene),geometry_sha256=e.file_digest(e.GEOMETRY_PATH),fence_sha256=e.file_digest(e.GEOMETRY_PATH.parent/'collision/virtual_fences.json'),static_geometry_load_s=load_s,static_fence_mesh_s=static_s,static_triangles=len(static),samples=samples,dropout_returns_no_observation=e.observe(e.scenes()['sensor_dropout'],scene['start'],4.) is None,limits=['Not a runtime/global cache or planner benchmark; three probe poses only.','A geometry hash/epoch change must rebuild static data; dynamic active cones and sensor pose/source stamp are recomputed.','No occupancy/command is reused. Sensor freshness, path validity, receiver/source age and watchdog gates remain independent.','Synchronous raycast wrapper temporarily sets frozen simulator geometry; native C3 adapter must isolate or serialize its sensor instance, not share mutable globals between scenes.','No native execution, scheduling deadline, physical stopping or calibrated sensor claim.'])
    (HERE/'observation_profile.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
