"""Independent closed-cell oracle: exhaustive cells, long-double normalized SAT.

This file imports only Snapshot from the candidate. It never uses its polygon,
SAT, tolerance, broadphase, or spatial indexing helpers. Run as a script.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LD = np.longdouble


def oracle(pose, footprint, mask, res, origin):
    """Return exact-representation collision and signed smallest separation.

Positive separation is free distance along a separating unit SAT axis; negative
means penetration. Boundary contact on either map edge is collision. All occupied
cells are visited, irrespective of footprint bounds. Arithmetic uses longdouble
and no geometric tolerance, to expose conservative candidate-only classifications.
    """
    p = np.asarray(footprint, dtype=LD)
    x, y, theta = map(LD, pose)
    c, s = np.cos(theta), np.sin(theta)
    q = np.column_stack((x+c*p[:, 0]-s*p[:, 1], y+s*p[:, 0]+c*p[:, 1]))
    lo = np.asarray(origin, dtype=LD)
    hi = lo+np.array([mask.shape[1], mask.shape[0]], dtype=LD)*LD(res)
    edge_clearance = min(np.min(q-lo), np.min(hi-q))
    if edge_clearance <= 0:
        return True, float(edge_clearance)
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        return False, float(edge_clearance)
    # Center coordinates avoid global-coordinate projection cancellation.
    centers = np.column_stack((lo[0]+(cols.astype(LD)+LD('.5'))*LD(res),
                               lo[1]+(rows.astype(LD)+LD('.5'))*LD(res)))
    edges = np.roll(q, -1, axis=0)-q
    axes = np.concatenate((np.array([[1,0],[0,1]], dtype=LD),
                           np.column_stack((-edges[:,1],edges[:,0]))))
    axes = axes[np.any(axes != 0, axis=1)]
    axes /= np.sqrt(np.sum(axes*axes, axis=1))[:,None]
    relative = q[None,:,:]-centers[:,None,:]
    projections = relative @ axes.T
    radius = LD(res)/2*np.sum(np.abs(axes),axis=1)
    gaps = np.maximum(np.min(projections,axis=1)-radius,
                      -radius-np.max(projections,axis=1))
    per_cell = np.max(gaps,axis=1)
    minimum = min(edge_clearance, np.min(per_cell))
    return bool(np.any(per_cell <= 0)), float(minimum)


def main():
    path = ROOT/'collision.py'
    spec = importlib.util.spec_from_file_location('reviewed_closed_cell_collision', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    rng = np.random.default_rng(20261025)
    stats = {}; issues = []; conservative = []
    def check(group, pose, footprint, mask, res, origin=(0.,0.), expected=None):
        actual = bool(mod.Snapshot(mask,res,origin=origin).collides(pose,footprint))
        reference, gap = oracle(pose,footprint,mask,res,origin)
        row = stats.setdefault(group, {'cases':0,'oracle_collisions':0,'false_clears':0,'conservative_differences':0})
        row['cases'] += 1; row['oracle_collisions'] += int(reference)
        details = dict(group=group, pose=list(map(float,pose)), footprint=np.asarray(footprint).tolist(),
                       resolution=res,origin=origin,gap_m=gap,actual=actual,oracle=reference,
                       occupied_cells=np.argwhere(mask).tolist())
        if reference and not actual:
            row['false_clears'] += 1; issues.append(details)
        if actual and not reference:
            scale=max(1.,float(np.max(np.abs(np.asarray(pose[:2]))))+float(np.max(np.abs(footprint))),float(np.max(np.abs(origin))),float(max(mask.shape)*res))
            details['documented_tolerance_m']=1e-12+64*np.finfo(float).eps*scale
            row['conservative_differences'] += 1
            conservative.append(details)
        if expected is not None and actual != expected:
            issues.append(dict(details,expected=expected))
    square=np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    for origin in [(0.,0.),(-8.,-12.),(1e8,-1e8)]:
        mask=np.zeros((12,12),bool);mask[5,5]=True
        for angle in [0, math.pi/2, math.pi/4, -math.pi/4, math.pi, .123, 1.234, 2*math.pi]:
            # Align one extremal footprint vertex/edge with each occupied-cell side.
            rotated=square@np.array([[math.cos(angle),math.sin(angle)],[-math.sin(angle),math.cos(angle)]])
            for axis in [0,1]:
                for side in [-1,1]:
                    for gap in [0.,-1e-8,-1e-12,1e-14,1e-12,1e-10,1e-7,.01]:
                        center=np.array(origin)+5.5
                        edge=origin[axis]+(5 if side<0 else 6)
                        center[axis]=edge-(max(rotated[:,axis]) if side<0 else min(rotated[:,axis]))+side*gap
                        check('cell_edge_gap',(*center,angle),square,mask,1.,origin)
        empty=np.zeros((12,12),bool)
        for axis in [0,1]:
            for side in [-1,1]:
                for gap in [0.,-1e-8,1e-14,1e-12,1e-10,1e-7,.01]:
                    center=np.array(origin)+6
                    center[axis]=origin[axis]+(.25+gap if side<0 else 11.75-gap)
                    check('map_edge_gap',(*center,0.),square,empty,1.,origin)
    mask=np.zeros((12,12),bool);mask[5,5]=True
    for origin in [(0.,0.),(-8.,-12.)]:
        for dx in [-1,1]:
            for dy in [-1,1]:
                for gap in [0.,-1e-12,1e-14,1e-12,1e-10,.01]:
                    center=np.array(origin)+[5 if dx<0 else 6,5 if dy<0 else 6]+np.array([dx,dy])*(.25+gap)
                    check('cell_corner_gap',(*center,0.),square,mask,1.,origin)
    for i in range(12000):
        res=float(rng.choice([.01,.05,.1,.3,1.,2.]))
        origin=tuple(rng.uniform(-100,100,2))
        mask=rng.random((12,13))<rng.choice([0.,.02,.15,.5,1.])
        n=int(rng.choice([3,4,5,8])); theta=np.arange(n)*2*math.pi/n
        footprint=np.column_stack((np.cos(theta),np.sin(theta)))*rng.uniform(.03,2.,2)*res
        pose=(* (np.array(origin)+rng.uniform(-1,14,2)*res), rng.uniform(-20,20))
        check('random_convex',pose,footprint,mask,res,origin)
    # Snapshot source mutation and distinct occupancy generations.
    source=np.zeros((10,10),bool)
    old=mod.Snapshot(source,1.)
    clear_before=not old.collides((5.5,5.5,0),square)
    source[5,5]=True
    old_unchanged=not old.collides((5.5,5.5,0),square)
    new_blocked=mod.Snapshot(source,1.).collides((5.5,5.5,0),square)
    guard_blocked=mod.polygon_collision((5.5,5.5,0),square,source,1.)
    source[5,5]=False
    guard_cleared=not mod.polygon_collision((5.5,5.5,0),square,source,1.)
    new_clear=not mod.Snapshot(source,1.).collides((5.5,5.5,0),square)
    lifecycle=dict(clear_before=clear_before,source_mutation_does_not_change_snapshot=old_unchanged,
                   new_snapshot_sees_added_obstacle=bool(new_blocked),new_snapshot_sees_removed_obstacle=new_clear,borrowed_guard_sees_added_obstacle=bool(guard_blocked),
                   borrowed_guard_sees_removed_obstacle=bool(guard_cleared))
    a=np.arange(5)*2*np.pi/5
    star=np.column_stack([np.cos(a),np.sin(a)])[[0,2,4,1,3]]
    invalid_inputs = [star, 'bad', [[0,0],[1,0],[0,1,2]], [[0,0],[1,0],[2,0]],
                      [[0,0],[1,0],[1,0],[0,1]], [[0,0],[1,0],[float('nan'),1]]]
    malformed=[]
    for shape in invalid_inputs:
        try:
            answer=mod.Snapshot(np.zeros((10,10),bool),1.).collides((5,5,0),shape)
            malformed.append({'input':repr(shape),'fails_closed':bool(answer),'exception':None})
        except Exception as error:
            malformed.append({'input':repr(shape),'fails_closed':False,'exception':type(error).__name__})
    result=dict(candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),seed=20261025,
                groups=stats,total_cases=sum(v['cases'] for v in stats.values()),
                false_clears=sum(v['false_clears'] for v in stats.values()),
                conservative_differences=len(conservative),
                max_conservative_gap_m=max((x['gap_m'] for x in conservative),default=0),
                lifecycle=lifecycle,malformed=malformed,issues=issues,conservative_examples=sorted(conservative,key=lambda x:x['gap_m'],reverse=True)[:30],
                max_conservative_gap_to_tolerance_ratio=float(max((x['gap_m']/x['documented_tolerance_m'] for x in conservative),default=0)),
                conservative_beyond_tolerance=int(sum(x['gap_m']>x['documented_tolerance_m'] for x in conservative)),
                oracle='Exhaustive occupied-cell SAT, normalized axes, longdouble arithmetic, no broadphase or geometric tolerance',
                limitations='Finite sampled validation, not a formal proof. Input float representation and trigonometric rounding can shift intended mathematical contacts.')
    (Path(__file__).parent/'geometry_review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('issues','conservative_examples')},indent=2))
    return int(bool(issues) or not all(lifecycle.values()) or not all(x['fails_closed'] for x in malformed) or result['conservative_beyond_tolerance']>0)

if __name__=='__main__':
    raise SystemExit(main())
