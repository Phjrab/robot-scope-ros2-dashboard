"""Pure legacy-to-C1 adapter for an isolated flat simulation, never a live source.

The existing C1 SceneSnapshotService remains the only latest-state owner.
No IO, automatic refresh, ROS, route, clock inference or frame relabelling here.
"""

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from robot_dashboard.expansion_contracts import ContractError, ObstacleFrame
from .cone_input import ObstacleValidationError, validate_legacy_cones, SCHEMA

PROFILE = "cone-flat-demo.v1"
DEMO_MAP_ID = "c0dec0dec0dec0dec0dec0de"


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ObstacleValidationError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def load_scenario(path):
    """Adapt the teammate's committed arena example, preserving its exact frame."""
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ObstacleValidationError("SCENARIO_PATH")
    with path.open("rb") as stream:
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ObstacleValidationError("SCENARIO_LIMIT")
    doc = json.loads(raw, object_pairs_hook=_unique_pairs)
    if (
        not isinstance(doc, dict)
        or doc.get("schema_version") != "0.1"
        or doc.get("evidence_type") != "SIMULATION_GT"
        or not isinstance(doc.get("obstacles"), list)
    ):
        raise ObstacleValidationError("SCENARIO_SCHEMA")
    cones, names = [], set()
    for i, item in enumerate(doc["obstacles"]):
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "xy", "radius_m", "height_m"}
            or not isinstance(item["id"], str)
            or not item["id"].startswith("cone_")
            or item["id"] in names
            or not isinstance(item["xy"], list)
            or len(item["xy"]) != 2
        ):
            raise ObstacleValidationError("SCENARIO_CONE")
        names.add(item["id"])
        cones.append(
            dict(
                id=i,
                x=item["xy"][0],
                y=item["xy"][1],
                n=0,
                radius_m=item["radius_m"],
                height_m=item["height_m"],
            )
        )
    payload = dict(
        schema_version=SCHEMA,
        stamp=0,
        frame=doc.get("frame_id"),
        model={
            "path": "simulation:scenario",
            "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
        },
        health={"stale": False, "fps": 0},
        cones=cones,
    )
    return validate_legacy_cones(payload)


def demo_context(payload, *, epoch="cone-demo-1", generation=1):
    value = validate_legacy_cones(payload)
    # Full hash is of the scenario display content, explicitly NOT a model hash.
    revision = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return dict(
        map_id=DEMO_MAP_ID,
        revision=revision,
        generation=generation,
        frame_id=value["frame"],
        source_epoch=epoch,
        stream_epoch=f"scene-{epoch}",
        clock_domain="synthetic-cone-clock",
        calibration_id="flat-demo-assumption",
        units="m",
        source_identity="SYNTHETIC_SCENARIO",
        space_kind="ISOLATED_SIMULATION",
    )


def adapt_cones(payload, context, *, sequence, received_monotonic_ns, host_clock_id):
    """An explicit synthetic offer; receipt is supplied by the host, not the input."""
    value = validate_legacy_cones(payload)
    if (
        context.get("map_id") != DEMO_MAP_ID
        or context.get("space_kind") != "ISOLATED_SIMULATION"
        or context.get("source_identity") != "SYNTHETIC_SCENARIO"
        or context.get("units") != "m"
        or context.get("clock_domain") != "synthetic-cone-clock"
        or context.get("calibration_id") != "flat-demo-assumption"
    ):
        raise ContractError("PAIRED_REAL_PRODUCER_INPUT_REQUIRED: isolated demo only")
    if value["frame"] != context["frame_id"]:
        raise ContractError("UNALIGNED: frame rename is not a transform")
    stamp = Decimal(str(value["stamp"])) * 1_000_000_000
    if stamp != stamp.to_integral_value():
        raise ContractError("legacy timestamp has sub-nanosecond precision")
    objects = []
    for cone in value["cones"]:
        radius, height = cone["radius_m"], cone["height_m"]
        objects.append(
            dict(
                track_id=f"cone-{cone['id']}",
                class_name="traffic_cone",
                class_score=None,
                geometry=dict(
                    center=[cone["x"], cone["y"], height / 2],
                    extent=[2 * radius, 2 * radius, height],
                    orientation_xyzw=[0, 0, 0, 1],
                ),
                state="STALE" if value["health"]["stale"] else "OBSERVED",
                novelty="UNRESOLVED",
                sensor_support=["SYNTHETIC_SCENARIO"],
                provenance=dict(
                    display_profile=PROFILE,
                    position_basis="FLAT_DEMO_ONLY",
                    height_status="HEIGHT_UNVERIFIED",
                    radius_m=radius,
                    height_m=height,
                    observation_count=cone["n"],
                    model_digest_hint=value["model"]["sha256_12"],
                    model_hash_verified=False,
                    geometry_usage="DISPLAY_ONLY",
                ),
            )
        )
    return ObstacleFrame(
        schema_version="0.2",
        evidence_kind="SYNTHETIC",
        producer="cone-demo-adapter",
        sequence=sequence,
        source_epoch=context["source_epoch"],
        frame_key=dict(source_epoch=context["source_epoch"], frame_id=value["frame"]),
        stamp_ns=str(int(stamp)),
        clock_domain=context["clock_domain"],
        host_clock_id=host_clock_id,
        received_monotonic_ns=str(received_monotonic_ns),
        map_binding={k: context[k] for k in ("map_id", "revision", "generation")},
        calibration_id=context["calibration_id"],
        input_sources=[],
        obstacles=objects,
        health=dict(
            stale=value["health"]["stale"],
            display_profile=PROFILE,
            source_kind="SIMULATED",
            alignment="ISOLATED_DEMO_ONLY",
            position_basis="FLAT_DEMO_ONLY",
            height_status="HEIGHT_UNVERIFIED",
            inference_fps=None,
            legacy_reported_fps=value["health"]["fps"],
        ),
        dropped_counts={},
    ).to_dict()
