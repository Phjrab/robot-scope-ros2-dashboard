#!/usr/bin/env python3
"""Recheck the published Stage 3 packet and diagnose its three rejected map fits.

Only local files and NumPy/SciPy are used. Input bytes must match the published
manifest. No network, ROS, device connection, map export or operational apply.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_dashboard.offline_slam.core import inverse, vector  # noqa: E402
from robot_dashboard.offline_slam.registration_diagnostics import (  # noqa: E402
    inspect_saved_map,
    transfer_local_hypothesis,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--packet", type=Path, default=ROOT / "docs/replay-fixtures/stage3-20261019"
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--all-recorded-candidates",
        action="store_true",
        help="Inspect every archived candidate; do not select or apply a location.",
    )
    parser.add_argument(
        "--cross-scan-seed-check",
        action="store_true",
        help="Diagnose relative-scan propagation of scan 0's ambiguous hypothesis.",
    )
    args = parser.parse_args()
    packet, output = args.packet.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(packet):
        parser.error("output must be a new directory outside the input packet")
    # Load trusted repository verifier code, never execute code from --packet.
    helper = ROOT / "docs/replay-fixtures/stage3-20261019/replay_saved_scans.py"
    spec = importlib.util.spec_from_file_location("stage3_verifier", helper)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    replay.BUNDLE = packet
    map_bytes, scan_bytes, contexts, off, on = replay._inputs()
    stored_scores = replay._score_stored(map_bytes, scan_bytes, on)
    reference = np.frombuffer(map_bytes, dtype="<f8").reshape(-1, 3)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for i, packed in enumerate(scan_bytes):
        archived = on["scans"][i]["backend_result"]
        candidates, selected = archived["candidates"], archived["selected_candidate"]
        indexes = range(len(candidates)) if args.all_recorded_candidates else [selected]
        if not 1 <= len(candidates) <= 32:
            raise ValueError("RECORDED_CANDIDATE_LIMIT")
        for index in indexes:
            seed = np.asarray(candidates[index]["map_from_scan"])
            row = inspect_saved_map(
                np.frombuffer(packed, dtype="<f8").reshape(-1, 3),
                reference,
                seed,
                ambiguity_reasons=archived["gate_reasons"],
            )
            row.update(
                scan_index=i,
                candidate_index=index,
                historically_selected=index == selected,
                source_stamp_ns=contexts[i]["source_stamp_ns"],
                seed_provenance="ARCHIVED_AMBIGUOUS_CANDIDATE_NOT_GROUND_TRUTH",
            )
            rows.append(row)
            print(
                json.dumps(
                    dict(
                        scan=i,
                        candidate=index,
                        selected=index == selected,
                        legacy=row["fits"]["legacy_density"]["metrics"]["failures"],
                        balanced=row["fits"]["balanced_density"]["metrics"]["failures"],
                    )
                ),
                flush=True,
            )
    selected = [row for row in rows if row["historically_selected"]]
    seed_consistency = []
    for i in range(1, len(selected)):
        delta = vector(
            inverse(np.asarray(selected[0]["seed"])) @ np.asarray(selected[i]["seed"])
        )
        seed_consistency.append(
            dict(
                scan_pair=[0, i],
                translation_m=float(np.linalg.norm(delta[:3])),
                rotation_rad=float(np.linalg.norm(delta[3:])),
                meaning="Historical candidate separation; not robot motion.",
            )
        )
    propagated = []
    if args.cross_scan_seed_check:
        # The fixed packet verifier pins all three scans and their contexts.
        identity = [
            (c["observer_id"], c["observer_epoch"], c["source_frame"]) for c in contexts
        ]
        if len(set(identity)) != 1:
            raise ValueError("CROSS_SCAN_CAPTURE_IDENTITY_MISMATCH")
        first = np.frombuffer(scan_bytes[0], dtype="<f8").reshape(-1, 3)
        for i in range(1, len(scan_bytes)):
            source = np.frombuffer(scan_bytes[i], dtype="<f8").reshape(-1, 3)
            hypothesis = transfer_local_hypothesis(first, source, selected[0]["seed"])
            comparison = None
            if hypothesis["map_from_source"] is not None:
                comparison = inspect_saved_map(
                    source,
                    reference,
                    hypothesis["map_from_source"],
                    ambiguity_reasons=on["scans"][0]["backend_result"]["gate_reasons"],
                )
            propagated.append(
                dict(
                    scan_index=i,
                    reference_scan_index=0,
                    hypothesis=hypothesis,
                    comparison=comparison,
                    independent_global_relocalization=False,
                )
            )
    # Reverify originals after all computations; the verifier has no write path.
    replay._inputs()
    result = dict(
        schema="robot-scope.stage3-registration-diagnosis/v1",
        scope="LOCAL_FILES_ONLY",
        map_sha256=hashlib.sha256(map_bytes).hexdigest(),
        scan_sha256=[hashlib.sha256(b).hexdigest() for b in scan_bytes],
        code_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                ROOT / "robot_dashboard/offline_slam/core.py",
                ROOT / "robot_dashboard/offline_slam/registration_diagnostics.py",
            ]
        },
        stored_scores_reverified=stored_scores,
        original_files_unchanged=True,
        seed_consistency=seed_consistency,
        cases=rows,
        cross_scan_seed_diagnostics=propagated,
        pose_graph_optimization="NOT_RUN_NO_CONTINUOUS_TRAJECTORY",
        operational_application="NOT_APPLIED",
        maps_saved=0,
    )
    (output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
