"""Independent, offline D0 cost-field audit. No ROS import or runtime route output."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
RAW = (0.81, 0.56)
PADDED = (0.87, 0.62)
RI = PADDED[1] / 2
RC = math.hypot(PADDED[0] / 2, PADDED[1] / 2)
H = 0.02
SOURCE = '2a1b1f172f30d010fa33d9b7f247a9163f175e82'
ARCHIVE_SHA = '43580b9a3ced0b6bba00211a14a6398650fb7018c2794243f2af092cc5c34c29'
EXPECTED_HASHES = {
    'trace.jsonl': 'f672cb64b19bb4c7d8f8f5faf59738bf7490a7a828346288947dd0a45f4e4423',
    'observations.jsonl': '0261358be0277a0a0ceb32ef91e5ef87903bae2083228f9e544a244c9e7009ae',
    'fixture.json': '7f6104bf116e83de4be5882fef6ca15a3270bc90df606a3c73e8576b116a2bf5',
    'params.yaml': '46b62dc644cd4f1e5087759202ffe2a7d760924be34e2bfcc185d8637c4b8d00',
    'environment.json': 'e9c6d26ea9dd664ed44b0430902ca99d80a10e68614bb278e705821e1408cc1a',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corners(pose, size=PADDED):
    x, y, a = pose
    c, s = math.cos(a), math.sin(a)
    return [[x + c*u - s*v, y + s*u + c*v]
            for u, v in [(-size[0]/2, -size[1]/2), (size[0]/2, -size[1]/2),
                         (size[0]/2, size[1]/2), (-size[0]/2, size[1]/2)]]


def segment_box(a, b, box):
    """Closed Liang-Barsky clipping, independent of Nav2 raster checker."""
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        delta = b[axis] - a[axis]
        if abs(delta) < 1e-15:
            if not box[0][axis] <= a[axis] <= box[1][axis]:
                return False
        else:
            t0 = (box[0][axis] - a[axis]) / delta
            t1 = (box[1][axis] - a[axis]) / delta
            lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
            if lo > hi + 1e-12:
                return False
    return True


def grid_cell(xy, origin, resolution):
    return [math.floor((xy[i]-origin[i])/resolution) for i in (0, 1)]


def box_at(cell, origin, resolution):
    p = [origin[i]+cell[i]*resolution for i in (0, 1)]
    return [p, [v+resolution for v in p]]


def perimeter_cells(poly, origin, resolution):
    """Conservative continuous edge/closed-cell overlap, NOT native Bresenham."""
    low = grid_cell([min(p[i] for p in poly) for i in (0, 1)], origin, resolution)
    high = grid_cell([max(p[i] for p in poly) for i in (0, 1)], origin, resolution)
    # Include both sides of an exactly aligned boundary.
    cells = []
    for y in range(low[1]-1, high[1]+1):
        for x in range(low[0]-1, high[0]+1):
            box = box_at([x, y], origin, resolution)
            edges = [i for i in range(4) if segment_box(poly[i], poly[(i+1)%4], box)]
            if edges:
                cells.append(([x, y], edges))
    return cells


def published_snapshot(record, pose):
    assert record['frame'] in ('map', 'odom'), 'Unproved frame transform'
    data = zlib.decompress(base64.b64decode(record['data_zlib_base64']))
    assert len(data) == record['width'] * record['height']
    center = grid_cell(pose[:2], record['origin'], record['resolution'])
    def value(cell):
        x, y = cell
        if not (0 <= x < record['width'] and 0 <= y < record['height']):
            return None
        v = data[y*record['width']+x]
        return v if v < 128 else v-256
    hits = []
    for cell, edges in perimeter_cells(corners(pose), record['origin'], record['resolution']):
        if value(cell) == 100:
            hits.append({'cell': cell, 'occupancy': 100, 'box': box_at(cell, record['origin'], record['resolution']), 'edges': edges})
    return {k: record[k] for k in ('kind', 'source_sim_s', 'sim_t', 'receipt_monotonic', 'frame', 'resolution', 'origin')} | {
        'center_cell': center, 'center_occupancy': value(center), 'padded_lethal_edge_cells': hits,
        'format': 'nav_msgs/OccupancyGrid int8; NOT raw uint8 costmap',
    }


def inflation_cost(distance_m, scaling=5.0):
    if distance_m == 0:
        return 254
    if distance_m <= RI:
        return 253
    return int(252*math.exp(-scaling*(distance_m-RI)))


def emitted_cost(distance_m, radius):
    return inflation_cost(distance_m) if distance_m <= math.ceil(radius/H)*H + 1e-12 else 0


def gate(center_cost, threshold=82):
    return {'smac_full_check_eligible': not (center_cost < threshold and threshold > 0),
            'mppi_full_check_eligible': center_cost >= 1 and (center_cost >= threshold or threshold < 1)}


def occupancy(raw):
    if raw in (0, 253, 254, 255):
        return {0: 0, 253: 99, 254: 100, 255: -1}[raw]
    return 1 + (97*(raw-1))//251


def audit(run_dir):
    p = Path(run_dir)
    hashes = {name: digest(p/name) for name in EXPECTED_HASHES}
    if hashes != EXPECTED_HASHES:
        raise ValueError('Pinned artifact input hash mismatch; do not substitute data')
    tr = [json.loads(x) for x in (p/'trace.jsonl').read_text().splitlines()]
    obs = [json.loads(x) for x in (p/'observations.jsonl').read_text().splitlines()]
    fixture = json.loads((p/'fixture.json').read_text())
    env = json.loads((p/'environment.json').read_text())
    assert env['source_sha'] == SOURCE
    assert fixture['clearance_m'] == .03 and fixture['resolution_m'] == H
    assert fixture['parking_allowed'] is False
    assert fixture['footprint'] == [[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]]
    assert all(math.isclose(abs(c[0]), .435) and math.isclose(abs(c[1]), .31) for c in fixture['effective_footprint'])
    floor = fixture['d0_bundle']['truth']['boundary_polygon'][0][1]
    assert floor == .491
    first = next(i for i,x in enumerate(tr) if x['boundary_count'] > 0)
    samples = []
    for label, record in [('previous',tr[first-1]), ('first_failure',tr[first])]:
        sample = {'label':label, 'trace_index':tr.index(record), 'sim_t':record['sim_t'], 'receipt_monotonic':record['monotonic'],
                  'pose':record['pose'], 'raw_corners':corners(record['pose'],RAW), 'padded_corners':corners(record['pose']),
                  'raw_floor_clearance_m':min(c[1] for c in corners(record['pose'],RAW))-floor,
                  'padded_floor_clearance_m':min(c[1] for c in corners(record['pose']))-floor, 'maps':[]}
        for kind in ['costmap','local_costmap']:
            records = [r for r in obs if r['kind'] == kind]
            before = [r for r in records if r['receipt_monotonic'] <= record['monotonic']]
            after = [r for r in records if r['receipt_monotonic'] > record['monotonic']]
            for relation, r in [('last_received_before', before[-1] if before else None), ('first_received_after', after[0] if after else None)]:
                if r:
                    sample['maps'].append({'relation':relation, 'source_age_sim_s':record['sim_t']-r['source_sim_s'], **published_snapshot(r,record['pose'])})
        samples.append(sample)
    bad = [x for x in tr if x['boundary_count'] > 0]
    return {'schema':'d0-footprint-costfield-audit.v1', 'classification':'INDEPENDENT_RECONSTRUCTION',
            'native_source_sha':SOURCE, 'artifact_id':12590081484, 'run_id':40168963222, 'artifact_sha256':ARCHIVE_SHA,
            'verified_input_hashes': hashes, 'scene': {'raw_size_m':RAW, 'padded_size_m':PADDED, 'margin_once_m':.03,
                'floor_y':floor, 'boundary_polygon':fixture['d0_bundle']['truth']['boundary_polygon'],
                'parking_allowed':False, 'forbidden_polygons':fixture['d0_bundle']['truth']['forbidden_polygons'],
                'obstacles':fixture['obstacles'], 'geometry_sha256':fixture['d0_bundle']['truth']['geometry_sha256']},
            'samples':samples, 'boundary_positive_sample_count':len(bad), 'distinct_crossing_events':sum(x['boundary_count']>0 and (i==0 or tr[i-1]['boundary_count']==0) for i,x in enumerate(tr)),
            'post_first_failure_nonzero_actuator_count':sum(any(abs(v)>1e-12 for v in x['actuator']) for x in tr[first:]),
            'source_supported_inference':'Center-cost fast paths may skip padded footprint checks with insufficient inflation coverage; actual executed internal branch not captured.',
            'frame_alignment': {'classification':'SOURCE_SUPPORTED_INFERENCE', 'map_to_odom':'identity; zero default translation, unit quaternion', 'source':SOURCE, 'path':'experiments/competition_nav2/native_runner.py', 'lines':'404-425', 'source_file_sha256':'fdff344a0d10403195ab68121b18ba069ab1e3f02f525df740597ca75556f56f', 'limitation':'Published by pinned source; no atomic TF buffer snapshot recorded'},
            'native_checker':'NATIVE_NOT_RUN', 'atomic_checker_packet':'INPUT_REQUIRED',
            'notes':['Published map receipts bracket trace samples, not atomic checker snapshots.',
                     'Effective margin breach is not raw-body contact.', '64 retained samples are not 64 independent impacts.',
                     'No map, path or scan is exported as runtime input.']}


def make_cases(result):
    cases = []
    for sample in result['samples']:
        local = next(m for m in sample['maps'] if m['kind']=='local_costmap' and m['relation']=='last_received_before')
        cases.append({'id':'retained_'+sample['label'], 'classification':'INDEPENDENT_RECONSTRUCTION',
                      'pose':sample['pose'], 'floor_y':.491, 'raw_size_m':RAW,'padded_size_m':PADDED,
                      'expected_raw_contact':False, 'expected_padded_floor_violation':sample['padded_floor_clearance_m']<0,
                      'published_snapshot':local,
                      'expected_native_checker_result':None,
                      'note':'Sparse observed cell evidence; not atomic raw costmap or runtime map.'})
    # A fixed sparse synthetic field is an isolated regression input, not an arena modification.
    p=[.5,2.0,math.pi/2]
    cases.append({'id':'valid_narrow_corridor', 'classification':'INDEPENDENT_RECONSTRUCTION', 'pose':p,
                  'raw_size_m':RAW, 'padded_size_m':PADDED,
                  'corridor_x':[.16,.84], 'grid':{'resolution':H,'origin':[0,0], 'lethal_wall_columns':[7,42], 'height_rows':200},
                  'expected_padded_collision':False, 'expected_circle_collision':True,
                  'expected_full_footprint_collision':False, 'raw_field_recipe':{'inflation_radius_m':.58,'cost_scaling_factor':5,'inscribed_radius_m':.31,'source_cost':254,'other_costs':'max distance-inflated source wall cost; no OccupancyGrid inversion'}, 'expected_reconstructed_max_perimeter_raw_cost':253, 'expected_native_checker_result':None,
                  'note':'0.68m corridor fits .62m lateral rectangle but not 1.068m circle. Do not convert inflation cost into lethal collision.'})
    return {'schema':'d0-small-native-checker-cases.v1','usage':'EVALUATION_ONLY; never runtime route/hidden obstacle prior',
            'native_checker_status':'NATIVE_NOT_RUN','cases':cases}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-dir',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=HERE/'results')
    args=ap.parse_args()
    result=audit(args.run_dir)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.output/'checker_cases.json').write_text(json.dumps(make_cases(result),indent=2)+'\n')
    print(json.dumps({'raw_clearance':result['samples'][-1]['raw_floor_clearance_m'],
                      'padded_clearance':result['samples'][-1]['padded_floor_clearance_m'],
                      'sample_count':result['boundary_positive_sample_count']}))

if __name__=='__main__':
    main()
