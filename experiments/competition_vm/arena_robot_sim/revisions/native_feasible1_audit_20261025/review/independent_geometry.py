#!/usr/bin/env python3
"""Read-only raw-artifact check, independently implemented SAT and segment distances.
No imported simulation helpers, no native execution, no controller-causality claim.
"""
import argparse
import base64
import json
import math
from pathlib import Path
import zlib


def edges(poly):
    return zip(poly, poly[1:] + poly[:1])


def body(pose, half_x, half_y):
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c*a - s*b, y + s*a + c*b)
            for a, b in [(-half_x, -half_y), (half_x, -half_y),
                         (half_x, half_y), (-half_x, half_y)]]


def sat_overlap(a, b):
    """Convex polygon overlap, with contact counted as overlap."""
    for p, q in list(edges(a)) + list(edges(b)):
        n = (p[1]-q[1], q[0]-p[0])
        aa = [x*n[0]+y*n[1] for x, y in a]
        bb = [x*n[0]+y*n[1] for x, y in b]
        if max(aa) < min(bb) or max(bb) < min(aa):
            return False
    return True


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def segment_distance(a, b, c, d):
    if cross(a, b, c)*cross(a, b, d) < 0 and cross(c, d, a)*cross(c, d, b) < 0:
        return 0.0
    return min(point_segment(a,c,d), point_segment(b,c,d),
               point_segment(c,a,b), point_segment(d,a,b))


def border_distance(a, b):
    return min(segment_distance(p,q,r,s) for p,q in edges(a) for r,s in edges(b))


def inside(p, poly):
    result = False
    for a,b in edges(poly):
        if (a[1]>p[1]) != (b[1]>p[1]):
            xx = a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if p[0] < xx:
                result = not result
    return result


def check(pose, half, boundary, obstacles):
    poly = body(pose, *half)
    boundary_clearance = border_distance(poly, boundary)
    boundary_inside = all(inside(p,boundary) for p in poly)
    obstacle_results = []
    for name, obs in obstacles:
        overlap = sat_overlap(poly, obs)
        obstacle_results.append({'name':name, 'overlap':overlap,
                                 'clearance_m':0.0 if overlap else border_distance(poly,obs)})
    return {'boundary_inside':boundary_inside,'boundary_clearance_m':boundary_clearance,
            'obstacles':obstacle_results,
            'minimum_clearance_m':min([boundary_clearance if boundary_inside else 0.0]+[o['clearance_m'] for o in obstacle_results])}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    rows=lambda name:[json.loads(x) for x in (args.run/name).read_text().splitlines()]
    trace=rows('trace.jsonl')
    obs=rows('observations.jsonl')
    fixture=json.loads((args.run/'fixture.json').read_text())
    boundary=fixture['d0_bundle']['truth']['boundary_polygon']
    obstacles=[(o['id'],o['polygon']) for o in fixture['obstacles']]
    obstacles += [('forbidden_'+str(i),p) for i,p in enumerate(fixture['d0_bundle']['truth']['forbidden_polygons'])]
    pre=min(trace,key=lambda r:abs(r['sim_t']-6.4))
    post=min(trace,key=lambda r:abs(r['sim_t']-6.45))
    path=max((o for o in obs if o['kind']=='path' and o['receipt_monotonic']<pre['monotonic']),key=lambda o:o['receipt_monotonic'])
    grid=max((o for o in obs if o['kind']=='costmap' and o['receipt_monotonic']<pre['monotonic']),key=lambda o:o['receipt_monotonic'])
    values=zlib.decompress(base64.b64decode(grid['data_zlib_base64']))
    pp=path['points']; i=21
    # Forward segment tangent: an explicit analytical assumption, not recorded Path yaw.
    yaw=math.atan2(pp[i+1][1]-pp[i][1],pp[i+1][0]-pp[i][0])
    central_yaw=math.atan2(pp[i+1][1]-pp[i-1][1],pp[i+1][0]-pp[i-1][0])
    ppose=pp[i]+[yaw]
    ix=math.floor((pp[i][0]-grid['origin'][0])/grid['resolution'])
    iy=math.floor((pp[i][1]-grid['origin'][1])/grid['resolution'])
    value=values[iy*grid['width']+ix]
    result={'evidence':'Recorded native trace and global path XY; derived geometry only',
            'current_sim_t':pre['sim_t'],'current_pose':pre['pose'],
            'next_recorded_sim_t':post['sim_t'],'next_recorded_pose':post['pose'],
            'path_source_sim_s':path['source_sim_s'],'path_receipt_monotonic':path['receipt_monotonic'],
            'path_index_zero_based':i,'path_derived_pose':ppose,
            'path_yaw_method':'forward segment, not recorded native yaw',
            'central_chord_yaw_sensitivity_rad':central_yaw,
            'global_grid_source_sim_s':grid['source_sim_s'],
            'path_center_grid_cell':[ix,iy],'path_center_occupancy_value':value}
    for name,half in [('raw',(.405,.28)),('padded',(.435,.310))]:
        result[name]={'current':check(pre['pose'],half,boundary,obstacles),
                      'path_point21':check(ppose,half,boundary,obstacles),
                      'central_chord_sensitivity':check(pp[i]+[central_yaw],half,boundary,obstacles)}
    v,w=pre['actuator']; x,y,theta=pre['pose']
    def future(t):
        return [x+v/w*(math.sin(theta+w*t)-math.sin(theta)),
                y-v/w*(math.cos(theta+w*t)-math.cos(theta)),theta+w*t]
    def contact(t):
        return check(future(t),(.435,.310),boundary,obstacles)['minimum_clearance_m']==0
    bracket=None
    for j in range(1,1001):
        if contact(j/1000):
            lo,hi=(j-1)/1000,j/1000
            for _ in range(45):
                mid=(lo+hi)/2
                if contact(mid): hi=mid
                else: lo=mid
            bracket=[lo,hi]
            break
    result['counterfactual']={'not_native_prediction':True,'v':v,'w':w,
                              'constant_twist_horizon_s':1,'padded_contact_bracket_s':bracket}
    result['causal_verdict']='UNCONFIRMED: local costmap, recorded Path yaw, carrot, rejected twist and native collision arc are absent.'
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
