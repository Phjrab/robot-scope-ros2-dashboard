"""Translation only: C1 owns validation; D1 owns the numerical implementation.

Inject C1 message classes from a pinned dependency. No schema or validator is
copied here, and importing this module does not require C1 to be installed.
"""

from __future__ import annotations

import copy
import numpy as np

from .solver import solve, source_key
from robot_dashboard.relocalization.experimental_se3 import inverse

C1_TESTED_SHA = "54629c793ad4ae0ea88127f00ed1b7f8805fc4e2"


def to_core_request(request, *, job_id, proposal_revision=1):
    """Accept a C1-validated FusionRequest, not an untrusted HTTP dictionary.

    Unsupported worker budgets are rejected rather than silently ignored. The
    numerical baseline has fixed bounded iterations; C1 owns process deadlines.
    """
    wire = request.to_dict()
    unsupported = set(wire["options"]) - {"voxel_size"}
    if unsupported:
        raise ValueError(
            "D1 does not implement these worker budget options: "
            + ", ".join(sorted(unsupported))
        )
    sources = copy.deepcopy(wire["sources"])
    keys = {
        f"{s['map_id']}:{s['revision']}:{s['frame_id']}": source_key(s) for s in sources
    }
    anchor = keys[wire["anchor_source_key"]]
    poses = {anchor: np.eye(4)}
    for guess in wire["initial_guesses"]:
        poses[keys[guess["source_key"]]] = np.asarray(guess["T_anchor_source"]).reshape(
            4, 4
        )
    guesses = []
    for i, a in enumerate(sources):
        for b in sources[i + 1 :]:
            ka, kb = source_key(a), source_key(b)
            if ka in poses and kb in poses:
                guesses.append(
                    {
                        "target": ka,
                        "source": kb,
                        "T": (inverse(poses[ka]) @ poses[kb]).tolist(),
                    }
                )
    correspondences = {}
    for item in wire["correspondences"]:
        key = keys[item["source_key"]]
        if key == anchor:
            raise ValueError(
                "Anchor self-correspondences are not registration constraints"
            )
        pair = correspondences.setdefault(
            key,
            {"target": anchor, "source": key, "source_points": [], "target_points": []},
        )
        pair["source_points"].append(item["source_xyz"])
        pair["target_points"].append(item["anchor_xyz"])
    # Core's correspondence list follows source ordering; reverse when anchor is
    # later in the list, maintaining the column-vector T_target_source convention.
    order = [source_key(s) for s in sources]
    for item in correspondences.values():
        if order.index(item["target"]) > order.index(item["source"]):
            item["target"], item["source"] = item["source"], item["target"]
            item["source_points"], item["target_points"] = (
                item["target_points"],
                item["source_points"],
            )
    return dict(
        schema_version=wire["schema_version"],
        evidence_kind=wire["evidence_kind"],
        producer=wire["producer"],
        sequence=wire["sequence"],
        source_epoch=wire["source_epoch"],
        request_id=job_id,
        proposal_revision=proposal_revision,
        anchor_source_key=anchor,
        sources=sources,
        source_pins=copy.deepcopy(sources),
        mode=wire["mode"],
        initial_guesses=guesses,
        correspondences=list(correspondences.values()),
        options={"resolution_m": wire["options"].get("voxel_size", 0.05)},
    )


def proposal_to_contract(core, request, proposal_type):
    """Return the injected C1 FusionProposal, validated by its own constructor.

    Full residual samples stay in the core result for download/review; the wire
    proposal retains aggregate independent metrics within C1's document bound.
    """
    wire = request.to_dict()
    keys = {
        source_key(s): f"{s['map_id']}:{s['revision']}:{s['frame_id']}"
        for s in wire["sources"]
    }

    def edges(values):
        result = copy.deepcopy(values)
        for edge in result:
            for name in ("source", "target"):
                if name in edge:
                    edge[name] = keys[edge[name]]
            if "T" in edge:
                edge["T"] = np.asarray(edge["T"]).reshape(16).tolist()
            edge.get("metrics", {}).pop("residual_samples", None)
            for alternative in edge.get("alternatives", []):
                alternative["T"] = np.asarray(alternative["T"]).reshape(16).tolist()
                alternative.get("metrics", {}).pop("residual_samples", None)
        return result

    quality = copy.deepcopy(core["quality"])
    for preview in quality.get("source_previews", []):
        preview["source_key"] = keys[preview["source_key"]]
    quality["residual_samples_location"] = "core proposal, not bounded wire envelope"
    quality["request_id"] = wire["request_id"]
    return proposal_type(
        schema_version=core["schema_version"],
        evidence_kind=core["evidence_kind"],
        producer=core["producer"],
        sequence=core["sequence"],
        source_epoch=core["source_epoch"],
        job_id=core["job_id"],
        proposal_revision=core["proposal_revision"],
        state=core["status"],
        anchor_source_key=keys[core["anchor_source_key"]],
        T_fused_source={
            keys[t["source_key"]]: np.asarray(t["T"]).reshape(16).tolist()
            for t in core["T_fused_source"]
        },
        pairwise_edges=edges(core["pairwise_edges"]),
        connected_components=[
            [keys[k] for k in component] for component in core["connected_components"]
        ],
        quality=quality,
        ambiguous_candidates=edges(core["ambiguous_candidates"]),
        warnings=copy.deepcopy(core["warnings"]),
        input_pins=copy.deepcopy(wire["source_pins"]),
        solver_version=core["solver_version"],
        elapsed_ms=core["elapsed_ms"],
    )


def solve_contract(
    request,
    resolver,
    proposal_type,
    *,
    job_id,
    proposal_revision=1,
    progress=None,
    cancel_token=None,
):
    """Return a C1 FusionProposal. Use the two conversion functions to retain
    the full core proposal for D1 export; never export the lossy wire envelope.
    """
    core_request = to_core_request(
        request, job_id=job_id, proposal_revision=proposal_revision
    )
    result = solve(core_request, resolver, progress, cancel_token)
    return proposal_to_contract(result, request, proposal_type)
