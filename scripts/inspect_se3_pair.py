#!/usr/bin/env python3
"""Offline, seed-by-seed inspection of one saved map/query pair.

Recorded inputs retain evaluate_recorded_se3's qualification gates. The explicit
synthetic demo reuses the existing benchmark scene and is never recorded evidence.
Nothing imports ROS, opens a device, applies a pose, or changes input clouds.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_experimental_se3 import scene  # noqa: E402
from scripts.evaluate_recorded_se3 import MAX_MANIFEST_BYTES, qualified_inputs, sha  # noqa: E402
from robot_dashboard.relocalization.experimental_se3 import (  # noqa: E402
    Cloud, ExperimentalSE3Error, MAX_CORRESPONDENCE_M, _nearest,
    from_translation_quaternion, from_translation_rpy, inverse, register_se3,
    transform_points, validate_experimental_result, validate_transform,
)


def alignment_metrics(reference: Cloud, query: Cloud, transform) -> dict:
    """Directional query-to-map metrics using the solver's unchanged distance gate."""
    moved = transform_points(transform, query.points)
    _, squared = _nearest(moved, reference.points)
    mask = squared <= MAX_CORRESPONDENCE_M ** 2
    return {
        "query_points": len(moved), "correspondences": int(mask.sum()),
        "overlap_definition": "fraction_of_query_with_map_neighbor_within_gate",
        "correspondence_gate_m": MAX_CORRESPONDENCE_M,
        "overlap_ratio": float(mask.mean()),
        "inlier_rmse_m": float(math.sqrt(float(squared[mask].mean()))) if mask.any() else None,
        "all_query_nearest_p50_m": float(np.median(np.sqrt(squared))),
        "all_query_nearest_p95_m": float(np.percentile(np.sqrt(squared), 95)),
    }


def synthetic_pair(directory: Path):
    target = scene()
    truth = from_translation_rpy([.15, -.12, .18], [.09, -.07, .11])
    # Separate saved arrays, explicitly derived from one synthetic scene. They
    # are NOT independent real acquisitions, nor a test of global localization.
    source = transform_points(inverse(truth), target)
    identities = {}
    for role, points, frame, kind in (
        ("reference", target, "synthetic_map", "REGISTERED_MAP"),
        ("query", source, "synthetic_query_origin", "REGISTERED_QUERY"),
    ):
        path = directory / (role + '.npy')
        np.save(path, points, allow_pickle=False)
        path.chmod(0o600)
        identities[role] = {"path": path.name, "sha256": sha(path), "frame": frame,
                            "kind": kind, "unit": "m", "points": len(points),
                            "session_id": "SYNTHETIC-" + role,
                            "source_stamp_ns": None if role == "reference" else 1_000_000_000}
    seeds = [from_translation_rpy([0, 0, 0], [0, 0, 0]),
             from_translation_rpy([.08, -.06, .09], [.045, -.035, .055]),
             from_translation_rpy([20, 20, 20], [0, 0, 0])]
    manifest = {"schema": "robot-scope.synthetic-se3-pair.v1", "evidence_type": "synthetic_fixture",
                "independent_real_acquisitions": False, "transform_direction": "T_target_source",
                "lineage": "query derived from existing synthetic benchmark scene; no sensor data",
                **identities, "seeds": [{"source": "fixed_synthetic_test_prior",
                                          "T_target_source": s.tolist()} for s in seeds]}
    return (manifest, Cloud(target, identities['reference']['frame'], 'REGISTERED_MAP'),
            Cloud(source, identities['query']['frame'], 'REGISTERED_QUERY', stamp_ns=1_000_000_000), seeds)


def inspect_pair(reference: Cloud, query: Cloud, seeds: list) -> list[dict]:
    reference = reference.validated(reference=True)
    query = query.validated(reference=False)
    if not 1 <= len(seeds) <= 5:
        raise ExperimentalSE3Error('one to five predeclared seeds required')
    results = []
    for index, seed in enumerate(seeds):
        initial = validate_transform(seed)
        before = alignment_metrics(reference, query, initial)
        result = validate_experimental_result(register_se3(reference, query, initial))
        pose = result['pose']
        final = from_translation_quaternion([pose[k] for k in 'xyz'], pose['quaternion_xyzw'])
        results.append({"seed_index": index, "T_target_source_before": initial.tolist(),
                        "T_target_source_after": final.tolist(), "before": before,
                        "after": alignment_metrics(reference, query, final), "se3": result})
    return results


def plot_pair(reference: Cloud, query: Cloud, row: dict, path: Path, evidence: str):
    # Optional plotting dependency; neither solver nor recorded qualification
    # requires matplotlib. Keep equal before/after axes and every bounded point.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    before = transform_points(row['T_target_source_before'], query.points)
    after = transform_points(row['T_target_source_after'], query.points)
    fig, axes = plt.subplots(3, 2, figsize=(11, 11), constrained_layout=True)
    for row_index, (x, y) in enumerate(((0, 1), (0, 2), (1, 2))):
        union = np.vstack((reference.points, before, after))
        lo, hi = union.min(axis=0), union.max(axis=0)
        pad = max(float(np.max(hi - lo)) * .03, .01)
        for column, (title, moved, metrics) in enumerate((('Seed', before, row['before']), ('Result', after, row['after']))):
            ax = axes[row_index, column]
            ax.scatter(reference.points[:, x], reference.points[:, y], s=2, c='#355c99', label='reference')
            ax.scatter(moved[:, x], moved[:, y], s=2, c='#d85d39', alpha=.6, label='transformed query')
            ax.set(xlim=(lo[x]-pad, hi[x]+pad), ylim=(lo[y]-pad, hi[y]+pad),
                   xlabel='xyz'[x] + ' (m)', ylabel='xyz'[y] + ' (m)',
                   title=f"{title}: overlap {metrics['overlap_ratio']:.3f}, RMSE {metrics['inlier_rmse_m']}")
            ax.set_aspect('equal', adjustable='box')
            ax.grid(alpha=.2)
            if row_index == 0:
                ax.legend(markerscale=3)
    fig.suptitle(f"{evidence} | seed {row['seed_index']} | {row['se3']['status']}\n"
                 f"T_target_source: {query.frame} -> {reference.frame}\n"
                 'Local hypothesis only; global relocalization / operational application NOT_RUN')
    try:
        with path.open('x') as handle:
            fig.savefig(handle, format='svg')
        path.chmod(0o600)
    finally:
        plt.close(fig)


def write_experiment(output: Path, *, manifest_path: Path | None = None, synthetic_demo=False, plots=False) -> dict:
    if (manifest_path is None) == (not synthetic_demo):
        raise ValueError('choose exactly one recorded manifest or synthetic demo')
    if plots:
        import matplotlib  # noqa: F401 -- fail before creating an output directory
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest, manifest_hash = None, None
    try:
        if synthetic_demo:
            manifest, reference, query, seeds = synthetic_pair(output)
            (output / 'input.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
            manifest_hash = sha(output / 'input.json')
        else:
            if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
                raise ExperimentalSE3Error('manifest size bound exceeded')
            manifest = json.loads(manifest_path.read_text())
            manifest_hash = sha(manifest_path)
            reference, query, seeds = qualified_inputs(manifest, manifest_path.parent)
        results = inspect_pair(reference, query, seeds)
        report = {"schema": "robot-scope.offline-se3-pair-inspection.v1", "status": "EVALUATED",
                  "evidence_type": manifest['evidence_type'], "input": manifest,
                  "input_manifest_sha256": manifest_hash, "transform_direction": "T_target_source",
                  "query_preprocessing_applied_here": False, "reference_modified": False,
                  "query_modified": False, "absolute_position_error_m": None,
                  "absolute_rotation_error_rad": None, "independent_ground_truth": None,
                  "global_relocalization": "NOT_RUN", "operational_application": "NOT_RUN",
                  "measurements": results, "overlay_files": []}
        if plots:
            for row in results:
                path = output / f"seed-{row['seed_index']}-overlay.svg"
                plot_pair(reference, query, row, path, manifest['evidence_type'])
                report['overlay_files'].append({"path": path.name, "sha256": sha(path)})
    except (ExperimentalSE3Error, ValueError, TypeError, KeyError, OSError) as exc:
        report = {"schema": "robot-scope.offline-se3-pair-inspection.v1", "status": "BLOCKED",
                  "reason": str(exc), "global_relocalization": "NOT_RUN",
                  "operational_application": "NOT_RUN", "measurements": [],
                  "input": manifest, "input_manifest_sha256": manifest_hash,
                  "absolute_position_error_m": None, "absolute_rotation_error_rad": None}
    report['source'] = {"commit": subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                        "dirty": bool(subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True).strip()),
                        "files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT/'scripts/evaluate_recorded_se3.py', ROOT/'scripts/benchmark_experimental_se3.py', ROOT/'robot_dashboard/relocalization/experimental_se3.py']},
                        "python": platform.python_version(), "numpy": np.__version__}
    destination = output / 'report.json'
    with destination.open('x') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    for path in output.iterdir():
        if path.is_file():
            path.chmod(0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--manifest', type=Path)
    mode.add_argument('--synthetic-demo', action='store_true')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--plots', action='store_true', help='write SVG overlays using optional matplotlib')
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('output directory must be a new private artifact path')
    report = write_experiment(args.output_dir, manifest_path=args.manifest, synthetic_demo=args.synthetic_demo, plots=args.plots)
    print(json.dumps({'status': report['status'], 'output': str(args.output_dir)}))
    return 0 if report['status'] == 'EVALUATED' else 2


if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())
