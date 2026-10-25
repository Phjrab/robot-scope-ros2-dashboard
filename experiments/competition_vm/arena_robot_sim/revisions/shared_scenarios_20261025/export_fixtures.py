"""Small immutable D0 scene inputs and sensor conformance probes, not a controller.

Only existing D0 geometry/cone/triangle-raycast implementations are reused. The
observations are separate from hidden truth and are NOT a native driving replay.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
REPO = BASE.parents[2]
sys.path.insert(0, str(HERE.parent / 'left_slalom_20261024'))
import simulate_slalom as base  # noqa: E402

SEED = 20261025
C3_SHA = '16c63e08be5a7c10887e9e05cae94e94788e990f'
CLEARANCE = .03
BODY = copy.deepcopy(base.BODY)
START = list(base.START)
GOAL = [*base.GOAL, math.pi / 2]
GEOMETRY_PATH = REPO / 'assets/competition-arena/revisions/rulebook-20261015/geometry.py'
CORRIDOR_PATH = REPO / 'assets/competition-arena/revisions/corridor-parallel-20261024/geometry.py'


def load_geometry(path):
    spec = importlib.util.spec_from_file_location('shared_' + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def design_to_sim(pose):
    """Identity SE(2), only arena_design -> d0_sim_map, never a measured map."""
    return list(pose)


def sim_to_design(pose):
    return list(pose)


def design_to_gltf(point):
    x, y, z = point
    return [x, z, -y]


def gltf_to_design(point):
    x, z, minus_y = point
    return [x, -minus_y, z]


def geometry_record(path, provenance):
    g = load_geometry(path)
    return dict(revision=g.REV, source_path=str(path.relative_to(REPO)),
                source_sha256=file_digest(path), provenance=provenance,
                fence_source_path=str((path.parent/'collision/virtual_fences.json').relative_to(REPO)),
                fence_source_sha256=file_digest(path.parent/'collision/virtual_fences.json'),
                outer_boundary=g.OUTER, holes=g.HOLES, floors=g.FLOORS,
                semantic_zones=g.zones(), map_transform=None,
                navigation_qualified=False)


def scenes():
    """Canonical ground-truth API shared with the independent feasibility audit."""
    g = load_geometry(GEOMETRY_PATH)
    cone = base.cone
    configurations = {
        'empty': [],
        'feasible1': [cone(1, .18, 2.5)],
        'feasible2': [cone(1, .18, 2.), cone(2, .18, 3.5)],
        'original_tight5': base.configs()['slalom_5'],
        'blocked': base.configs()['blocked_5'],
        'sensor_dropout': [],
        'open_diagnostic': [cone(i + 1, x, y) for i, (x, y) in enumerate(
            [(.18, 1.8), (.18, 2.08), (.18, 2.36), (.82, 4.05), (.82, 4.33)])],
    }
    forbidden = [*g.HOLES, g.FLOORS['floor_parking_bay'], g.FLOORS['floor_center_base']]
    forbidden += [z['polygon'] for z in g.zones() if z['type'] in ('RAMP', 'STAIRS')]
    result = {}
    for name, cones in configurations.items():
        result[name] = dict(
            scenario=name, geometry_revision=g.REV,
            boundary_polygon=g.FLOORS['floor_left_straight'],
            forbidden_polygons=copy.deepcopy(forbidden),
            start=list(START), goal=list(GOAL), footprint=copy.deepcopy(BODY),
            clearance_m=CLEARANCE, parking_allowed=False,
            cones=[dict(c, appears_s=0.) for c in cones],
            seed=SEED, frame_id='arena_design', map_transform=None,
            scope='LEFT_SLALOM_PLANAR_ONLY',
            diagnostic_only=name == 'open_diagnostic',
        )
    return result


def cone_polygon(cone):
    x, y = cone['xy']
    h = cone['base_side_m'] / 2
    return [[x-h, y-h], [x+h, y-h], [x+h, y+h], [x-h, y+h]]


def sensor_config(name):
    return dict(
        model='D0 existing ideal four-height triangle first-hit raycast',
        source_path=str((BASE / 'simulate.py').relative_to(REPO)),
        source_sha256=file_digest(BASE / 'simulate.py'),
        frame_id='d0_virtual_laser', origin_xy_body_m=[0., 0.],
        origin_z_ground_m=list(base.sim.HEIGHTS),
        angle_min_rad=-math.pi, angle_increment_rad=2*math.pi/360,
        beams=360, horizontal_fov_rad=2*math.pi,
        range_min_exclusive_m=.02, range_max_exclusive_m=8., no_hit_value_m=8.,
        reduction='minimum first-hit range across four horizontal planes',
        occlusion='nearest positive triangle intersection; hidden geometry never injected as observations',
        noise='none; idealized, not calibrated sensor', sensor_period_s=.2,
        sensor_delay_s=0., dropout_start_s=4. if name == 'sensor_dropout' else None,
        dropout_end_s=None, source_clock='simulation elapsed seconds, epoch=1',
        freshness_limit_s=.25, dropout_behavior='no observation, not an all-clear scan',
    )


def observe(scene, pose, stamp_s):
    """An on-demand observation at the supplied current pose; no planned path."""
    sensor = sensor_config(scene['scenario'])
    if sensor['dropout_start_s'] is not None and stamp_s >= sensor['dropout_start_s']:
        return None
    g = load_geometry(GEOMETRY_PATH)
    previous = base.sim.geometry
    try:
        base.sim.geometry = g
        active = [c for c in scene['cones'] if stamp_s >= c['appears_s']]
        ranges, _ = base.sim.raycast(base.sim.mesh(active), pose)
    finally:
        base.sim.geometry = previous
    return dict(source_stamp_s=stamp_s, receipt_stamp_s=stamp_s, source_epoch=1,
                seed=SEED, source='D0_VIRTUAL_TRIANGLE_RAYCAST',
                frame_id=sensor['frame_id'], acquisition_pose_sim=list(pose),
                ranges_m=ranges.tolist())


def expectation(name):
    if name == 'blocked':
        return dict(outcome='SAFE_WAIT', basis='Three .26 m square bases across x=.15,.50,.85 at y=2.5 form a barrier; preserved goal also conflicts with upper cone. See independent feasibility report.')
    if name == 'original_tight5':
        return dict(outcome='GEOMETRIC_WITNESS_NATIVE_NOT_RUN', prior_controller_outcome='NOT_ADOPTED_SAFE_WAIT', basis='Independent full-body continuous sweep certifies a witness without shrinking geometry. See FEASIBILITY.md and witnesses/original_tight5.json. Geometric witness is audit-only, not a native planner path or controller result.')
    if name == 'sensor_dropout':
        return dict(outcome='SENSOR_STALE_HOLD', basis='Empty route, no new scans at t>=4; stale nonzero commands must not be repeated while planning.')
    if name == 'open_diagnostic':
        return dict(outcome='DIAGNOSTIC_ONLY', basis='Existing OPEN cone spacing gives more turning room, not evidence that original tight5 succeeds; boundary is unchanged.')
    return dict(outcome='GEOMETRIC_WITNESS_NATIVE_NOT_RUN', basis='Independent full-body swept witness certifies empty/same-side full-size cone route. See FEASIBILITY.md and witnesses/. Native Nav2 result NOT_RUN; witness must not be supplied as its path.')


def build_bundle():
    original = geometry_record(GEOMETRY_PATH, 'Preserved rulebook design revision; provisional dimensions, not field survey')
    corrected = geometry_record(CORRIDOR_PATH, 'User-approved right-corridor parallel correction; not official measured map')
    bounds_path = BASE / 'rendering/standing_bounds.json'
    geometry = dict(schema='d0-shared-geometry.v1', units='metre/radian',
        origin='lower-left arena design ground [0,0,0]', handedness='right; Z up',
        simulation_transform=dict(from_frame='arena_design', to_frame='d0_sim_map',
            matrix_xyz=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]], yaw_offset_rad=0.),
        viewer_transform=dict(from_frame='arena_design', to_frame='gltf', formula='(x,y,z)->(x,z,-y)', usage='viewer only; never Nav2 coordinates'),
        map_transform=None, real_map_registration='INPUT_REQUIRED',
        original=original, corridor_parallel=corrected,
        collision_body=dict(polygon=BODY, length_m=.81, width_m=.56,
            source='left_slalom_20261024/simulate_slalom.py BODY; conservative proposed body; not physical qualification'),
        visual_envelope=dict(standing_fk_bounds=json.loads(bounds_path.read_text()),
            source_path=str(bounds_path.relative_to(REPO)), source_sha256=file_digest(bounds_path),
            note='Standing visual mesh envelope is NOT the collision footprint or dynamic gait sweep'),
        clearance_policy=dict(margin_m=CLEARANCE,
            footprint_sweep='Expand each body half-extent by .03 exactly once: .87 x .62 m conservative rectangle',
            obstacle_geometry='Uninflated .26 square base and .12 radius .32 high cone; no shrink',
            circular_diagnostic='Circumscribed body radius hypot(.405,.28), plus .03 only; not the actual body',
            costmap='Adapter must record grid resolution, occupied-cell dilation and Nav2 inflation separately; no claim these equal physical clearance',
            native_configuration='Do not apply both padded footprint and another .03 padding; inflation is a planner cost, not permission to weaken independent sweep'))
    files = {'geometry.json': geometry}
    for name, scene in scenes().items():
        truth = dict(schema='d0-scene-truth.v1', **scene, scene_sha256=digest(scene),
                     geometry_file='geometry.json', geometry_sha256=digest(geometry),
                     obstacles=[dict(id=c['id'], polygon=cone_polygon(c), appears_s=c['appears_s'], cone=c) for c in scene['cones']],
                     sensor=sensor_config(name), expectation=expectation(name),
                     provenance=dict(source_stamp='D0 shared inputs 2026-10-25', seed=SEED,
                         source_path=str((HERE.parent/'left_slalom_20261024/simulate_slalom.py').relative_to(REPO)),
                         source_sha256=file_digest(HERE.parent/'left_slalom_20261024/simulate_slalom.py'),
                         c3_read_only_reference=C3_SHA, native_nav2_status='NOT_RUN'))
        files[f'{name}.truth.json'] = truth
        probes = []
        for seq, (stamp, pose) in enumerate([(0., START), (.2, [START[0], START[1]+.032, START[2]]), (4., [START[0], START[1]+.064, START[2]])]):
            observation = observe(scene, pose, stamp)
            probes.append(dict(probe_sequence=seq, probe_stamp_s=stamp,
                               requested_pose_sim=pose, observation=observation,
                               delivery='DROPPED' if observation is None else 'DELIVERED'))
        files[f'{name}.observations.json'] = dict(schema='d0-sensor-probes.v1',
            scenario=name, truth_sha256=digest(truth),
            usage='Conformance probes at explicit poses, NOT a trajectory or native execution. A live adapter must sample at actual native plant poses.',
            probes=probes)
    return files


def export(output, check=False):
    files = build_bundle()
    manifest = dict(schema='d0-shared-manifest.v1', hash_encoding='SHA256 canonical JSON sorted keys, compact separators, UTF-8, allow_nan=false',
                    files={name:digest(value) for name,value in files.items()},
                    scenarios=list(scenes()), generated_map_grids=False, rosbag=False,
                    native_consumption='ADAPTER_REQUIRED', c3_reference_sha=C3_SHA)
    files['manifest.json'] = manifest
    if check:
        for name, value in files.items():
            if json.loads((output/name).read_text()) != value:
                raise ValueError('Fixture differs from deterministic source: ' + name)
    else:
        output.mkdir(parents=True, exist_ok=True)
        for name, value in files.items():
            (output/name).write_text(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE/'fixtures')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest = export(args.output, args.check)
    print(json.dumps(dict(status='PASS', scenarios=len(manifest['scenarios']), manifest_sha256=digest(manifest), native_consumption='ADAPTER_REQUIRED')))
