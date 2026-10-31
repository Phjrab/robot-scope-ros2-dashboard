"""One paired offline sweep of frozen C0 scans; no ROS, device or motion I/O.

The same immutable reference, current scan and frozen per-case transform seed
are used for both policies. This is numerical replay, not an operational TF
publisher or an absolute-accuracy evaluation. Both outputs are private: the
summary also contains the supplied frame contract. Public reports must omit
its transforms and must never publish per-frame poses.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robot_dashboard.relocalization.directional_weighting import (  # noqa: E402
    BASELINE, CANDIDATE, DirectionalFrame, SurfaceSupport,
    sector_counts, validate_weighting,
)
from robot_dashboard.relocalization.experimental_se3 import (  # noqa: E402
    from_translation_quaternion, rotation_error_rad, transform_points, validate_transform,
)
from robot_dashboard.relocalization.observation_alignment import ReferenceIndex, solve_prepared  # noqa: E402
from robot_dashboard.relocalization.operational import digest, read_reference  # noqa: E402


def utc_ns(value):
    return round(datetime.datetime.fromisoformat(value).timestamp()*1e9)


def phase_names(intervals, case, receipt, first_receipt):
    names = [x['phase_label'] for x in intervals if x['case_id'] == case
             and utc_ns(x['start_utc']) <= receipt < utc_ns(x['end_utc'])]
    # Batched operator markers cannot establish a physical entry interval.
    if any(x['case_id'] == case and x['phase_label'] == 'ENTRY'
           and abs(receipt-utc_ns(x['start_utc'])) <= 300_000_000 for x in intervals):
        names.append('ENTRY_MARKER_APPROXIMATE')
    if receipt-first_receipt <= 5_000_000_000:
        names.append('START_FLAT_OPERATOR_CONTEXT')
    return sorted(set(names or ['UNLABELLED']))


def quantiles(values):
    values = [x for x in values if x is not None and math.isfinite(x)]
    return None if not values else dict(zip(('min', 'median', 'p95', 'max'),
        map(float, np.quantile(values, [0, .5, .95, 1]))))


def load_case(archive, case):
    required = ['cloud_stamp_ns', 'cloud_receipt_ns', 'cloud_offsets', 'cloud_xyz',
                'odom_stamp_ns', 'odom_xyz', 'odom_quat']
    d = {k: archive[case+'_'+k] for k in required}
    n = len(d['cloud_stamp_ns'])
    if (not n or d['cloud_offsets'].shape != (n+1,) or d['cloud_xyz'].ndim != 2
            or d['cloud_xyz'].shape[1] != 3 or d['cloud_offsets'][0] != 0
            or d['cloud_offsets'][-1] != len(d['cloud_xyz'])
            or np.any(np.diff(d['cloud_offsets']) < 0)
            or np.any(np.diff(d['cloud_stamp_ns']) <= 0)
            or np.any(np.diff(d['odom_stamp_ns']) <= 0)):
        raise ValueError('INVALID_CASE_ARRAY_CONTRACT')
    return d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arrays', type=Path, required=True)
    parser.add_argument('--reference-pcd', type=Path, required=True)
    parser.add_argument('--reference-sha256', required=True)
    parser.add_argument('--body-contract', type=Path, required=True)
    parser.add_argument('--frozen-priors', type=Path, required=True)
    parser.add_argument('--stage-intervals', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--private-rows', type=Path, required=True)
    parser.add_argument('--cases', default='ABC')
    parser.add_argument('--limit-per-case', type=int)
    args = parser.parse_args()
    inputs = [args.arrays, args.reference_pcd, args.body_contract, args.frozen_priors,
              args.stage_intervals, args.policy]
    outputs = [args.summary, args.private_rows]
    if (any(p.exists() for p in outputs) or outputs[0].resolve() == outputs[1].resolve()
            or any(o.resolve() == i.resolve() for o in outputs for i in inputs)):
        parser.error('outputs must be new distinct files, never input paths')
    if args.limit_per_case is not None and args.limit_per_case <= 0:
        parser.error('limit must be positive')
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    contract = json.loads(args.body_contract.read_text())
    if contract.get('verified') is not True or not contract.get('evidence'):
        raise ValueError('VERIFIED_BODY_AXES_REQUIRED')
    imu_base = validate_transform(contract['T_imu_base'])
    priors = json.loads(args.frozen_priors.read_text())
    intervals = json.loads(args.stage_intervals.read_text())
    policy = json.loads(args.policy.read_text())
    config = validate_weighting(policy['directional_weighting'])
    reference, full_count = read_reference(args.reference_pcd, args.reference_sha256)
    indices = {mode: ReferenceIndex(reference) for mode in [BASELINE, CANDIDATE]}
    if indices[BASELINE].tree is None:
        raise ValueError('OFFLINE_CANDIDATE_COMPARISON_REQUIRES_INSTALLED_SCIPY')
    support = SurfaceSupport(indices[CANDIDATE])
    probe_support = SurfaceSupport(indices[BASELINE])
    archive = np.load(args.arrays, allow_pickle=False)
    rows, input_audit = [], []
    started = time.monotonic()
    args.private_rows.parent.mkdir(parents=True, exist_ok=True)
    with args.private_rows.open('x') as stream:
        args.private_rows.chmod(0o600)
        for case in args.cases:
            d = load_case(archive, case)
            prior = validate_transform(priors['cases'][case]['T_map_odom'])
            previous_weight_state = None
            previous_fit = {BASELINE: None, CANDIDATE: None}
            next_stamp, attempted = 0, 0
            positions, rotations = d['odom_xyz'], d['odom_quat']
            for ci, source_stamp in enumerate(d['cloud_stamp_ns']):
                stamp = int(source_stamp)
                oi = int(np.searchsorted(d['odom_stamp_ns'], stamp))
                if oi >= len(d['odom_stamp_ns']) or d['odom_stamp_ns'][oi] != stamp:
                    raise ValueError('EXACT_STAMP_ODOMETRY_REQUIRED')
                odom = from_translation_quaternion(positions[oi], rotations[oi])
                body = odom @ imu_base
                cloud = d['cloud_xyz'][d['cloud_offsets'][ci]:d['cloud_offsets'][ci+1]]
                finite = cloud[np.isfinite(cloud).all(axis=1)]
                selected = finite[::max(1, math.ceil(len(finite)/1024))].copy()
                receipt = int(d['cloud_receipt_ns'][ci])
                phases = phase_names(intervals, case, receipt, int(d['cloud_receipt_ns'][0]))
                audit = dict(case=case, stamp_ns=str(stamp), phases=phases,
                    recorded_points=len(cloud), finite_points=len(finite), estimator_points=len(selected),
                    before_estimator_stride=sector_counts(finite, body),
                    after_estimator_stride=sector_counts(selected, body),
                    body_pitch_rad=math.asin(float(np.clip(-body[2, 0], -1, 1))), body_height_m=float(body[2, 3]))
                input_audit.append(audit)
                if stamp < next_stamp:
                    continue
                if args.limit_per_case and attempted >= args.limit_per_case:
                    continue
                next_stamp = stamp+500_000_000
                attempted += 1
                for mode in [BASELINE, CANDIDATE]:
                    index = indices[mode]
                    tick = time.monotonic()
                    deadline = tick+policy['compute_budget_s']
                    weighting = None
                    if mode == CANDIDATE:
                        weighting = DirectionalFrame(config, support, selected, body, stamp,
                            previous_weight_state, deadline, frame_verified=True)
                    row = dict(case=case, mode=mode, source_stamp_ns=str(stamp), phases=phases,
                        input_sha256=hashlib.sha256(np.asarray(selected, dtype='<f8').tobytes()).hexdigest(),
                        query_points=len(selected), initial_transform_sha256=hashlib.sha256(prior.astype('<f8').tobytes()).hexdigest(),
                        runtime_application='NOT_RUN', full_runtime_tracking_replay=False,
                        absolute_accuracy_m=None, input_audit=audit)
                    try:
                        result, transform = solve_prepared(reference, index, 'camera_init', selected,
                            'camera_init', stamp, prior, deadline, enforce_residual_limit=False,
                            **({'query_weighting': weighting} if weighting is not None else {}))
                        elapsed = time.monotonic()-tick
                        if weighting is not None:
                            previous_weight_state = weighting.next_state
                        moved = transform_points(transform, selected)
                        distance, _ = index.tree.query(moved, k=1, workers=1)
                        metrics = result['metrics']
                        numerical = result['status'] == 'CANDIDATE' and metrics['rmse_m'] <= policy['max_rmse_m']
                        mapped_body = transform @ body
                        previous = previous_fit[mode]
                        jump = None
                        if previous is not None:
                            before = previous @ body
                            jump = dict(xyz_m=float(np.linalg.norm(mapped_body[:3, 3]-before[:3, 3])),
                                z_m=float(mapped_body[2, 3]-before[2, 3]), rotation_rad=rotation_error_rad(mapped_body, before))
                        previous_fit[mode] = transform
                        diagnostic = metrics.get('directional_weighting')
                        if diagnostic is None:
                            probe = DirectionalFrame(config, probe_support, selected, body, stamp, None,
                                time.monotonic()+policy['compute_budget_s'], frame_verified=True)
                            ids, squared = index.nearest(moved)
                            probe(moved, ids, squared, squared <= .75**2)
                            diagnostic = probe.diagnostics
                            diagnostic['mode'] = BASELINE
                            total = sum(x['matched_points'] for x in diagnostic['sectors'])
                            for group in diagnostic['sectors']:
                                group['gain'], group['weight_mass'] = 1., float(group['matched_points'])
                                group['contribution_ratio'] = group['matched_points']/total if total else 0.
                            diagnostic['weighted_objective_rmse_m'] = metrics['rmse_m']
                            diagnostic['normal_information_scope'] = 'COMMON_DENSITY_CONTROLLED_STRUCTURE_PROBE_ONLY_NOT_BASELINE_SOLVER_WEIGHTS'
                        row.update(status=result['status'], reason=result['reason'], numerical_quality_pass=numerical,
                            common_unweighted_rmse_m=metrics['rmse_m'], common_overlap=metrics['overlap_ratio'],
                            common_all_query_capped_rmse_m=float(np.sqrt(np.mean(np.minimum(distance, .75)**2))),
                            common_within_10cm_fraction=float((distance <= .1).mean()),
                            metrics=metrics, directional=diagnostic, fit_elapsed_s=elapsed,
                            within_existing_500ms_fit_cadence=elapsed <= .5,
                            map_from_odom=transform.tolist(), mapped_body=mapped_body.tolist(),
                            candidate_correction_change_from_previous=jump,
                            candidate_changes_are_not_accepted_runtime_poses=True)
                    except Exception as exc:
                        row.update(status='ERROR', reason=str(exc), numerical_quality_pass=False,
                            fit_elapsed_s=time.monotonic()-tick)
                    rows.append(row)
                    stream.write(json.dumps(row, separators=(',', ':'))+'\n')
                    stream.flush()
                if attempted % 100 == 0:
                    print(json.dumps({'case':case,'paired_frames':attempted,'rows':len(rows),'elapsed_s':round(time.monotonic()-started, 1)}), flush=True)
    summary = dict(schema='c0-directional-offline-comparison.v1',
        qualification='PAIRED_NUMERICAL_REPLAY_WITH_FROZEN_ARCHIVED_PRIOR; NOT_ABSOLUTE_ACCURACY_OR_LIVE_TRACKING',
        same_reference_scan_and_per_case_frozen_seed=True, historical_map_prior_reestimated=False,
        body_frame_contract=contract, candidate_config=config, operational_quality_policy=policy,
        device_mutations=0, full_runtime_tracking_replay=False, live_stop_recovery_and_scan_costmap='NOT_RECORDED_IN_THESE_BAGS',
        reference_full_points=full_count, reference_solver_points=len(reference),
        total_rows=len(rows), paired_frames=len(rows)//2, input_clouds_audited=len(input_audit),
        elapsed_s=time.monotonic()-started, stages=[])
    for case in args.cases:
        phases = sorted({p for row in input_audit if row['case']==case for p in row['phases']})
        for phase in phases:
            for mode in [BASELINE, CANDIDATE]:
                subset = [r for r in rows if r['case']==case and r['mode']==mode and phase in r['phases']]
                fits = [r for r in subset if 'common_unweighted_rmse_m' in r]
                audit = [r for r in input_audit if r['case']==case and phase in r['phases']]
                item = dict(case=case, phase=phase, mode=mode, attempts=len(subset), successful_fits=len(fits),
                    numerical_quality_pass=sum(r['numerical_quality_pass'] for r in subset),
                    reasons={k:sum(r['reason']==k for r in subset) for k in sorted({r['reason'] for r in subset})},
                    body_pitch_rad=quantiles([r['body_pitch_rad'] for r in audit]), body_height_m=quantiles([r['body_height_m'] for r in audit]),
                    unweighted_rmse_m=quantiles([r['common_unweighted_rmse_m'] for r in fits]),
                    overlap=quantiles([r['common_overlap'] for r in fits]),
                    all_query_capped_rmse_m=quantiles([r['common_all_query_capped_rmse_m'] for r in fits]),
                    weighted_objective_rmse_m=quantiles([r['directional']['weighted_objective_rmse_m'] for r in fits]),
                    fit_elapsed_s=quantiles([r['fit_elapsed_s'] for r in subset]),
                    candidate_correction_jump_count=sum((r.get('candidate_correction_change_from_previous') or {}).get('xyz_m',0)>policy['max_translation_step_m']
                        or (r.get('candidate_correction_change_from_previous') or {}).get('rotation_rad',0)>policy['max_rotation_step_rad'] for r in fits),
                    structural_support_fraction=float(np.mean([r['directional']['structure_observable'] for r in fits])) if fits else None,
                    directions={})
                for name in ['front','rear','left','right']:
                    ds = [next(g for g in r['directional']['sectors'] if g['sector']==name) for r in fits]
                    item['directions'][name] = {key:quantiles([x[key] for x in ds]) for key in
                        ['input_points','matched_points','independent_query_voxels','gain','weight_mass','contribution_ratio','surface_diversity','boost_quality']}
                    item['directions'][name]['recorded_input_count'] = quantiles([a['before_estimator_stride'][name] for a in audit])
                    item['directions'][name]['after_stride_count'] = quantiles([a['after_estimator_stride'][name] for a in audit])
                summary['stages'].append(item)
    summary['input_sha256'] = {str(p.name):digest(p) for p in [args.arrays,args.reference_pcd,args.body_contract,
        args.frozen_priors,args.stage_intervals,args.policy,args.private_rows]}
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    args.summary.chmod(0o600)
    print(json.dumps({'paired_frames':len(rows)//2,'rows':len(rows),'elapsed_s':round(time.monotonic()-started,1),
        'summary':str(args.summary),'device_mutations':0}), flush=True)


if __name__ == '__main__':
    main()
