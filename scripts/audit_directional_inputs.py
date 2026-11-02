"""Audit archived current-scan representations and LIO continuity, not accuracy.

Dense body clouds are undistorted IMU-frame observations, not raw driver scans.
Their count ratio to voxelized registered clouds is not a point survival rate.
No map fitting, ROS output, sensor changes or device I/O occurs here.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.compare_directional_localization import load_case, phase_names, quantiles  # noqa: E402
from robot_dashboard.relocalization.directional_weighting import sector_counts, sector_ids, SECTORS  # noqa: E402
from robot_dashboard.relocalization.experimental_se3 import from_translation_quaternion, inverse, rotation_error_rad, transform_points, validate_transform  # noqa: E402
from robot_dashboard.relocalization.operational import digest  # noqa: E402


def audit_case(archive, case, imu_base, intervals):
    data = load_case(archive, case)
    rows, poses = [], []
    for ci, stamp in enumerate(data['cloud_stamp_ns']):
        oi = int(np.searchsorted(data['odom_stamp_ns'], stamp))
        if oi >= len(data['odom_stamp_ns']) or data['odom_stamp_ns'][oi] != stamp:
            raise ValueError('EXACT_STAMP_ODOMETRY_REQUIRED')
        body = from_translation_quaternion(data['odom_xyz'][oi], data['odom_quat'][oi]) @ imu_base
        poses.append(body)
        cloud = data['cloud_xyz'][data['cloud_offsets'][ci]:data['cloud_offsets'][ci+1]]
        finite = cloud[np.isfinite(cloud).all(axis=1)]
        selected = finite[::max(1, math.ceil(len(finite)/1024))]
        before, after = sector_counts(finite, body), sector_counts(selected, body)
        rows.append(dict(phases=phase_names(intervals, case, int(data['cloud_receipt_ns'][ci]),
            int(data['cloud_receipt_ns'][0])), before=before, after=after,
            relative_height_m=float(body[2, 3]-poses[0][2, 3]),
            pitch_deg=math.degrees(math.asin(float(np.clip(-body[2, 0], -1, 1)))),
            roll_deg=math.degrees(math.atan2(body[2, 1], body[2, 2])), finite_removed=len(cloud)-len(finite)))
    dt = np.diff(data['cloud_stamp_ns'])*1e-9
    steps = [float(np.linalg.norm(b[:3, 3]-a[:3, 3])) for a,b in zip(poses, poses[1:])]
    rotation = [rotation_error_rad(b,a) for a,b in zip(poses, poses[1:])]
    travel = []
    for i, (a,b) in enumerate(zip(poses, poses[1:])):
        velocity = a[:3, :3].T @ (b[:3, 3]-a[:3, 3])/dt[i]
        travel.append('stationary' if np.linalg.norm(velocity) <= .03 else SECTORS[int(sector_ids(velocity[None, :])[0])])
    dense = []
    for bi, stamp in enumerate(archive[case+'_body_stamp_ns']):
        ci = int(np.searchsorted(data['cloud_stamp_ns'], stamp))
        if ci >= len(poses) or data['cloud_stamp_ns'][ci] != stamp:
            raise ValueError('EXACT_DENSE_REGISTERED_STAMP_REQUIRED')
        offset = archive[case+'_body_offsets']
        points = archive[case+'_body_xyz'][offset[bi]:offset[bi+1]]
        points = transform_points(inverse(imu_base), points[np.isfinite(points).all(axis=1)])
        counts = dict(zip(SECTORS, map(int, np.bincount(sector_ids(points), minlength=4))))
        dense.append(dict(phases=rows[ci]['phases'], dense=counts, registered=rows[ci]['before']))
    phases = sorted({p for r in rows for p in r['phases']})
    stages = []
    for phase in phases:
        rs = [r for r in rows if phase in r['phases']]
        ds = [r for r in dense if phase in r['phases']]
        stages.append(dict(phase=phase, frames=len(rs), dense_pairs=len(ds),
            relative_height_m=quantiles([r['relative_height_m'] for r in rs]),
            pitch_deg=quantiles([r['pitch_deg'] for r in rs]), roll_deg=quantiles([r['roll_deg'] for r in rs]),
            directions={name:dict(registered=quantiles([r['before'][name] for r in rs]),
                estimator_selected=quantiles([r['after'][name] for r in rs]),
                dense=quantiles([r['dense'][name] for r in ds]),
                registered_to_dense_count_ratio=quantiles([r['registered'][name]/r['dense'][name]
                    for r in ds if r['dense'][name]])) for name in SECTORS}))
    return dict(case=case, current_scans=len(rows), dense_pairs=len(dense),
        all_pairs_exact_stamp=True, nonfinite_points_removed=sum(r['finite_removed'] for r in rows),
        estimator_stride_removed=sum(sum(r['before'].values())-sum(r['after'].values()) for r in rows),
        source_gap_s=quantiles(list(dt)), source_gaps_above_500ms=int((dt > .5).sum()),
        relative_step_m=quantiles(steps), relative_rotation_step_rad=quantiles(rotation),
        original_lio_jump_threshold_exceedances=int(sum(s/t>3. or r/t>4. for s,r,t in zip(steps,rotation,dt))),
        movement_direction_body_axes={k:travel.count(k) for k in ['stationary',*SECTORS]}, stages=stages)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['arrays', 'body-contract', 'stage-intervals', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.resolve() in [x.resolve() for x in [a.arrays,a.body_contract,a.stage_intervals]]:
        p.error('output must be new and distinct from inputs')
    contract = json.loads(a.body_contract.read_text())
    if contract.get('verified') is not True or not contract.get('evidence'):
        raise ValueError('VERIFIED_BODY_AXES_REQUIRED')
    imu_base = validate_transform(contract['T_imu_base'])
    intervals = json.loads(a.stage_intervals.read_text())
    with np.load(a.arrays, allow_pickle=False) as archive:
        result = dict(schema='c0-directional-input-audit.v1',
            scope='CURRENT_REGISTERED_AND_SELECTED_DENSE_IMU_SCANS; NO_MAP_FIT_OR_GROUND_TRUTH',
            direction_basis='FULL_EXACT_STAMP_BODY_AXES_NOT_TRAVEL_DIRECTION',
            count_ratios_are_not_point_survival_rates=True,
            scan_costmap_and_operating_map_correction='NOT_RECORDED',
            cases=[audit_case(archive,c,imu_base,intervals) for c in 'ABC'],
            input_sha256={x.name:digest(x) for x in [a.arrays,a.body_contract,a.stage_intervals]})
    payload = json.dumps(result,indent=2,allow_nan=False)+'\n'
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as stream:
        a.output.chmod(0o600)
        stream.write(payload)
    print(json.dumps({k:sum(c[k] for c in result['cases']) for k in ['current_scans','dense_pairs','estimator_stride_removed','original_lio_jump_threshold_exceedances']}))


if __name__ == '__main__':
    main()
