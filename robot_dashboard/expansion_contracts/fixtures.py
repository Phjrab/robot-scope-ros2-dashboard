"""Tiny generated synthetic messages, never captured sensor/map assets."""

from .messages import FusionRequest, MapSourceDescriptor, ObstacleFrame


def envelope(sequence=0, epoch="fixture-epoch"):
    return dict(
        schema_version="0.1",
        evidence_kind="SYNTHETIC",
        producer="c1-fixture",
        sequence=sequence,
        source_epoch=epoch,
    )


def source(index=1, sha256=None):
    return MapSourceDescriptor(
        **envelope(),
        map_id=f"{index:024x}",
        revision=f"{index:064x}",
        sha256=sha256 or f"{index:064x}",
        frame_id="camera_init",
        units="m",
        asset_role="full_source",
        mapping_session_id=None,
        gravity_or_plane=None,
        point_count=3,
        point_schema=[dict(name=n, size=4, type="F", count=1) for n in ("x", "y", "z")],
        acquisition={"origin": "generated synthetic fixture"},
    )


def request(sources=None, request_id="fixture-request"):
    sources = sources or [source(1), source(2)]
    return FusionRequest(
        **envelope(),
        request_id=request_id,
        anchor_source_key=sources[0].key,
        sources=[s.to_dict() for s in sources],
        source_pins={s.key: s.sha256 for s in sources},
        initial_guesses=[],
        correspondences=[],
        mode="manual_review",
        options={"max_iterations": 10},
    )


def obstacle(
    sequence=0,
    epoch="fixture-epoch",
    generation=0,
    calibration_id="synthetic-calibration",
):
    return ObstacleFrame(
        **envelope(sequence, epoch),
        frame_key={"source_epoch": epoch, "frame_id": "odom"},
        stamp_ns=str(sequence * 1000000),
        clock_domain="fixture-clock",
        host_clock_id="test-host",
        received_monotonic_ns=sequence * 1000000,
        map_binding={
            "map_id": "1" * 24,
            "revision": "1" * 64,
            "generation": generation,
        },
        calibration_id=calibration_id,
        input_sources=["synthetic"],
        obstacles=[],
        health={"state": "fixture"},
        dropped_counts={},
    )
