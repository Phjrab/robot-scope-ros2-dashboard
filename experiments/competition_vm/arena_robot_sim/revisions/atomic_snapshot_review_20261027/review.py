"""D0 bounded independent review of retained C3 atomic packets; no ROS/native run.

Prior D0 polygon clipping is reused, not C3 verdicts/SAT as an oracle.
Raw arrays and returned paths are consumed privately and never exported as routes.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('d0_r6', HERE.parent/'native_checker_review_20261026/review.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
SOURCE = 'cf7662123bf13c9c38d565c03a978a4b9ae357a2'
ARCHIVE_SHA = '91a7d37428dc838e324de82152ff7f84082a0cd618546376e559dfb73fead404'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yaw(q):
    return math.atan2(2*(q[3]*q[2]+q[0]*q[1]), 1-2*(q[1]**2+q[2]**2))


def pose(p):
    return p['position'][:2]+[yaw(p['quaternion'])]


def matched(packet, record):
    return (packet['frame'] == record['frame'] == 'map'
            and packet['path_header_ros_ns'] == round(record['source_sim_s']*1e9)
            and [p['position'][:2] for p in packet['path']] == record['points']
            and [p['position'][2] for p in packet['path']] == record['z']
            and [p['quaternion'] for p in packet['path']] == record['quaternions'])


def validate_packet(packet, data):
    assert packet['source_sha'] == SOURCE
    assert packet['schema'] == 'c3-planner-atomic.v1'
    assert packet['returned_valid_path'] and packet['raw_unchanged_under_lock']
    assert packet['raw_costmap_update_stamp'] is None
    assert len(data) == packet['raw_bytes'] == packet['width']*packet['height']
    assert packet['finish_steady_ns'] >= packet['capture_steady_ns']
    assert packet['finish_ros_ns'] >= packet['lock_capture_ros_ns']
    assert packet['origin'] == [0, 0] and packet['frame'] == 'map'
    assert packet['allow_unknown'] is False
    assert len(packet['footprint']) == 4
    assert all(abs(abs(x)-.435) < 3e-9 and abs(abs(y)-.31) < 3e-9 for x,y in packet['footprint'])


def is_blocked(value, published=False):
    # 253/raw is nonlethal inflation; 255/raw is unknown and rejected here.
    return value in ((100, 255) if published else (254, 255))


def box(cell, grid):
    x,y = cell
    h = grid['resolution']; ox,oy = grid['origin']
    return [ox+x*h,oy+y*h,ox+(x+1)*h,oy+(y+1)*h]


def transformed(body, p):
    c,s = math.cos(p[2]),math.sin(p[2])
    return [[p[0]+c*x-s*y,p[1]+s*x+c*y] for x,y in body]


def grid_hits(poly, grid, data, published=False):
    h=grid['resolution']; ox,oy=grid['origin']; w=grid['width']; height=grid['height']
    lo=[math.floor((min(p[k] for p in poly)-[ox,oy][k])/h)-1 for k in (0,1)]
    hi=[math.floor((max(p[k] for p in poly)-[ox,oy][k])/h) for k in (0,1)]
    hits=[]
    for y in range(lo[1],hi[1]+1):
        for x in range(lo[0],hi[0]+1):
            outside=not(0<=x<w and 0<=y<height)
            v=255 if outside else data[y*w+x]
            if is_blocked(v,published):
                clipped=old.clip(poly,box([x,y],grid))
                if clipped:
                    hits.append({'cell':[x,y],'value':v,'area_m2':old.area(clipped)})
    return hits


def interval(a,b,body):
    da=math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))
    radius=max(math.hypot(*v) for v in body)
    n=max(1,math.ceil((math.dist(a[:2],b[:2])+radius*abs(da))/.002),math.ceil(abs(da)/.005))
    return [[a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n,a[2]+da*i/n] for i in range(n+1)]


def review(root, archive):
    assert digest(archive)==ARCHIVE_SHA
    assert (root/'source-sha.txt').read_text().strip()==SOURCE
    run=root/'atomic/mppi-d0_feasible1-0/run'
    packet_dir=run.parent/'atomic-planner'
    records=[json.loads(l) for l in (run/'observations.jsonl').read_text().splitlines()]
    paths=[r for r in records if r['kind']=='path']
    maps=[r for r in records if r['kind']=='costmap' and r['frame']=='map']
    fixture=json.loads((run/'fixture.json').read_text())
    assert fixture['clearance_m']==.03 and fixture['parking_allowed'] is False
    assert fixture['footprint']==[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]
    assert len(fixture['obstacles'])==1
    cone=fixture['obstacles'][0]['polygon']
    cone_box=[min(p[0] for p in cone),min(p[1] for p in cone),max(p[0] for p in cone),max(p[1] for p in cone)]
    assert all(math.isclose(a,b,abs_tol=1e-14) for a,b in zip(cone_box,[.05,2.37,.31,2.63]))
    packets=[json.loads(p.read_text()) for p in sorted(packet_dir.glob('plan-*.json'),key=lambda p:int(p.stem.split('-')[1]))]
    assert len(packets)==len(paths)==33
    identities=[]; pairs=[]
    for packet in packets:
        data=(packet_dir/packet['raw_file']).read_bytes()
        validate_packet(packet,data)
        matches=[i for i,r in enumerate(paths) if matched(packet,r)]
        assert len(matches)==1
        index=matches[0]; record=paths[index]
        identities.append({'invocation':packet['invocation'],'path_index':index,'pose_count':len(packet['path']),
                           'packet_sha256':digest(packet_dir/f"plan-{packet['invocation']}.json"),
                           'raw_sha256':hashlib.sha256(data).hexdigest(),'raw_unchanged_under_lock_recorded':packet['raw_unchanged_under_lock']})
        # Select the two reported discrepancies; selection is not a verdict oracle.
        if packet['invocation'] not in (3,7): continue
        segment,cell={3:(49,[15,121]),7:(81,[15,130])}[packet['invocation']]
        before=max((m for m in maps if m['source_sim_s']<=record['source_sim_s'] and m['receipt_monotonic']<=record['receipt_monotonic']),key=lambda m:m['receipt_monotonic'])
        after=min((m for m in maps if m['receipt_monotonic']>record['receipt_monotonic']),key=lambda m:m['receipt_monotonic'])
        for m in (before,after):
            assert m['origin']==packet['origin'] and m['resolution']==packet['resolution']
            assert m['width']==packet['width'] and m['height']==packet['height']
        pub=zlib.decompress(base64.b64decode(before['data_zlib_base64']))
        later=zlib.decompress(base64.b64decode(after['data_zlib_base64']))
        assert len(pub)==len(later)==len(data)
        a,b=map(pose,packet['path'][segment:segment+2]); body=packet['footprint']
        samples=interval(a,b,body); raw_hits=[]; published_hits=[]; cone_hits=[]; changed_hits=[]
        changed=bytearray(data); changed[cell[1]*packet['width']+cell[0]]=254
        for i,p in enumerate(samples):
            poly=transformed(body,p)
            for out,grid,values,published in [(raw_hits,packet,data,False),(published_hits,before,pub,True),(changed_hits,packet,changed,False)]:
                hits=grid_hits(poly,grid,values,published)
                if hits: out.append({'sample':i,'hits':hits})
            if old.clip(poly,cone_box): cone_hits.append(i)
        native=next(s for s in packet['segments'] if s['index']==segment)
        assert native['footprint']==body
        assert all(math.isclose(x,y,abs_tol=1e-14) for x,y in zip(native['a'],a))
        assert all(math.isclose(x,y,abs_tol=1e-14) for x,y in zip(native['b'],b))
        pairs.append({'invocation':packet['invocation'],'path_index':index,'segment':segment,'cell':cell,
                      'samples':len(samples),'raw_hits':raw_hits,'preceding_published_hits':published_hits,
                      'cone_hit_samples':cone_hits,'synthetic_254_hit_samples':[r['sample'] for r in changed_hits],
                      'raw_byte':data[cell[1]*packet['width']+cell[0]],'preceding_occupancy':pub[cell[1]*packet['width']+cell[0]],
                      'following_occupancy':later[cell[1]*packet['width']+cell[0]],
                      'native_supplemental_collision_recorded':native['actual_supplemental_checker_collision'],
                      'times':{'capture_ros_ns':packet['lock_capture_ros_ns'],'finish_ros_ns':packet['finish_ros_ns'],
                               'path_receipt':record['receipt_monotonic'],'before_source':before['source_sim_s'],
                               'before_receipt':before['receipt_monotonic'],'after_source':after['source_sim_s'],'after_receipt':after['receipt_monotonic']}})
    assert len({r['path_index'] for r in identities})==33
    trace=[json.loads(l) for l in (run/'trace.jsonl').read_text().splitlines()]
    return {'schema':'d0-atomic-snapshot-review.v1','classification':'INDEPENDENT_RECONSTRUCTION_OF_RETAINED_EVIDENCE',
            'native_source_sha':SOURCE,'archive_sha256':ARCHIVE_SHA,'artifact_id':12638597871,
            'native_execution_by_d0':'NOT_RUN','packet_identity_checks':identities,'selected_interval_checks':pairs,
            'trace_observations':{'samples':len(trace),'recorded_contact_samples':sum(r['collision_count']>0 for r in trace),
                                  'recorded_boundary_samples':sum(r['boundary_count']>0 for r in trace),'final_actuator':trace[-1]['actuator']},
            'evidence_hashes':{f:digest(run/f) for f in ('observations.jsonl','trace.jsonl','fixture.json','params.yaml')},
            'historical_round6_atomic_attribution':'INPUT_REQUIRED_EXACT_HISTORICAL_BYTES',
            'decision':'CURRENT_SELECTED_DISCREPANCIES_EXPLAINED_BY_SNAPSHOTS_NAVIGATION_NOT_ADOPTED',
            'limits':['Full 33-path collision sweep count is C3-reported, not rerun by D0.',
                      'Two intervals are finite sampled checks, not continuous safety proof.',
                      'Recorded lock/immutability assertions are source-supported, not a second capture.',
                      'No runtime path/raw grid is exported; no controller tuning or physical qualification.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output.write_text(json.dumps(review(args.root,args.archive),indent=2)+'\n')
