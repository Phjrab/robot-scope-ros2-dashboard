"""D0 independent offline review: polygon clipping, not the C3 SAT/helper.
No native/ROS execution. Original expected_collision fields are never an oracle.
"""
import argparse, base64, hashlib, importlib.util, json, math, struct, zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('d0_prior', HERE.parent/'footprint_costfield_audit_20261026/audit.py')
prior=importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
C3='d33d2efc3a9bc25e21f45889c18b13ce543b2850'
ZIP='68dc02a516bf4f98354e7f14d1930dfe4321a619ce72f25f16b7b4a865acf107'

def clip(poly, box):
    """Sutherland-Hodgman intersection with closed axis-aligned cell."""
    for axis,limit,sign in [(0,box[0],1),(0,box[2],-1),(1,box[1],1),(1,box[3],-1)]:
        output=[]
        if not poly: return []
        a=poly[-1]; inside_a=sign*(a[axis]-limit)>=0
        for b in poly:
            inside_b=sign*(b[axis]-limit)>=0
            if inside_a != inside_b:
                t=(limit-a[axis])/(b[axis]-a[axis])
                output.append([a[k]+t*(b[k]-a[k]) for k in (0,1)])
            if inside_b: output.append(b)
            a=b; inside_a=inside_b
        poly=output
    return poly

def area(poly):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if poly else 0

def f32(x): return struct.unpack('f',struct.pack('f',x))[0]
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def case_geometry(case,h=.02):
    pose=list(map(f32,case['pose'])); poly=prior.corners(pose)
    outside=any(x<=0 or y<=0 or x>=4 or y>=6 for x,y in poly)
    hits=[]
    cells=[tuple(c) for c in case.get('raw_cells',[])]
    cells += [(x,y,254) for x in case.get('wall_columns',[]) for y in range(300)]
    for x,y,raw in cells:
        if raw!=254 and not(raw==255 and not case.get('allow_unknown',False)): continue
        clipped=clip(poly,[x*h,y*h,(x+1)*h,(y+1)*h])
        if clipped: hits.append({'cell':[x,y],'raw':raw,'area_m2':area(clipped)})
    return {'id':case['id'],'pose_f32':pose,'collision':outside or bool(hits),'outside':outside,'hits':hits}

def review(evidence, raw, archive):
    assert digest(archive)==ZIP
    overlay=evidence/'experiments/competition_nav2/overlay'
    cases=json.loads((overlay/'cases.json').read_text())
    lock=json.loads((overlay/'source-lock.json').read_text())
    assert cases['footprint']==[[.435,.31],[.435,-.31],[-.435,-.31],[-.435,.31]]
    assert cases['resolution']==.02
    assert (raw/'source-sha.txt').read_text().strip()==C3
    input_checks={}
    for path,expected in lock['d0_inputs'].items():
        p=HERE.parents[4]/path
        # HERE.parents[4] is repository root.
        copied=overlay/('d0-checker_cases.json' if path.endswith('checker_cases.json') else 'd0-coverage.json')
        input_checks[path]=digest(p)==expected and digest(copied)==expected
    assert all(input_checks.values())
    provenance=json.loads((raw/'overlay/provenance.json').read_text())
    assert digest(overlay/'nav2.patch')==provenance['patch_sha256']
    assert digest(overlay/'c3_exact_footprint.hpp')==provenance['exact_checker_sha256']
    stock=json.loads((raw/'checker/stock.json').read_text())
    fixed=json.loads((raw/'overlay/fixed.json').read_text())
    stock_rows={x['id']:x for x in stock['cases']}; fixed_rows={x['id']:x for x in fixed['cases']}
    rows=[]
    for c in cases['cases']:
        r=case_geometry(c); s=stock_rows[c['id']]; f=fixed_rows[c['id']]
        r['stock']={k:s[k] for k in ['smac_collision','mppi_direct_collision','mppi_score_collision']}
        r['fixed']={k:f[k] for k in ['smac_collision','mppi_direct_collision','mppi_score_collision']}
        r['fixed_matches_independent_geometry']=all(v==r['collision'] for v in r['fixed'].values())
        if 'primitive' in c:
            poses=[[c['pose'][0]+p[0],c['pose'][1]+p[1],p[2]] for p in c['primitive']]
            r['primitive_geometry']=[case_geometry(c|{'pose':p})['collision'] for p in poses]
            r['stock_primitive_valid']=s['lattice_primitive_valid'];r['fixed_primitive_valid']=f['lattice_primitive_valid']
        rows.append(r)
    run=raw/'checked/closed-loop/mppi-d0_feasible1-0/run'
    records=[json.loads(l) for l in (run/'observations.jsonl').read_text().splitlines()]
    paths=[r for r in records if r['kind']=='path']; path=paths[2]
    assert path['frame']=='map' and len(path['points'])==170
    a,b=path['points'][97:99]; q=path['quaternions'][97]
    yaw=math.atan2(2*(q[3]*q[2]+q[0]*q[1]),1-2*(q[1]**2+q[2]**2))
    n=math.ceil(math.dist(a,b)/.002)
    maps=[r for r in records if r['kind']=='costmap' and r['frame']=='map']
    before=max((r for r in maps if r['source_sim_s']<=path['source_sim_s'] and r['receipt_monotonic']<=path['receipt_monotonic']),key=lambda r:r['receipt_monotonic'])
    after=min((r for r in maps if r['receipt_monotonic']>path['receipt_monotonic']),key=lambda r:r['receipt_monotonic'])
    cell=[15,129]; samples=[]
    for i in range(n+1):
        u=i/n; pose=[a[0]+u*(b[0]-a[0]),a[1]+u*(b[1]-a[1]),yaw]
        poly=prior.corners(pose); h=before['resolution']; ox,oy=before['origin']
        box=[ox+15*h,oy+129*h,ox+16*h,oy+130*h]
        intersection=clip(poly,box)
        cone_box=[.05,2.37,.31,2.63]
        samples.append({'u':u,'pose':pose,'grid_intersects':bool(intersection),'area_m2':area(intersection),'cone_intersects':bool(clip(poly,cone_box))})
    selected=[]
    for m in [before,after]:
        data=zlib.decompress(base64.b64decode(m['data_zlib_base64']))
        selected.append({k:m[k] for k in ['source_sim_s','receipt_monotonic','resolution','origin','frame']}|{'cell':cell,'occupancy':data[129*m['width']+15]})
    fixture=json.loads((run/'fixture.json').read_text()); assert fixture['clearance_m']==.03 and fixture['resolution_m']==.02
    assert all(math.isclose(abs(x),.435) and math.isclose(abs(y),.31) for x,y in fixture['effective_footprint'])
    return {'schema':'d0-native-checker-review.v1','classification':'INDEPENDENT_RECONSTRUCTION_OF_RETAINED_NATIVE_EVIDENCE','c3_tested_sha':C3,'artifact_sha256':ZIP,'d0_input_hashes_match':input_checks,'evidence_hashes':{str(p.relative_to(raw)):digest(p) for p in [raw/'checker/stock.json',raw/'overlay/fixed.json',run/'observations.jsonl',run/'fixture.json']},'cases':rows,'returned_segment':{'path_index':2,'segment':97,'path_source_sim_s':path['source_sim_s'],'path_receipt_monotonic':path['receipt_monotonic'],'endpoints':[a,b],'yaw':yaw,'samples':samples,'maps':selected,'grid_format':'published OccupancyGrid; not atomic native raw costmap','native_cause':'INPUT_REQUIRED_ATOMIC_RAW_PACKET'},'native_execution_by_d0':'NOT_RUN','decision':'BOUNDED_CHECKER_COMPARISON_SUPPORTED_NAVIGATION_NOT_ADOPTED'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('evidence',type=Path);p.add_argument('raw',type=Path);p.add_argument('archive',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(review(a.evidence,a.raw,a.archive),indent=2)+'\n')
