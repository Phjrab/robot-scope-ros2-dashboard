# C1 expansion contract 0.1

Implementation: `robot_dashboard/expansion_contracts/messages.py`; executable examples:
`robot_dashboard/expansion_contracts/fixtures.py`. Exact bootstrap SHA is the first
`feat(expansion): publish v0.1 contracts and synthetic fixtures` commit on
`review/20261029-x-c1-services` (also recorded in C1/HANDOFF.md).

All messages carry schema_version=0.1, evidence_kind, producer, sequence and
source_epoch. Map pins include opaque map ID, revision, SHA256 and frame ID;
sessions sharing camera_init are distinct. T_A_B uses row-major SE3 and column
vectors, metres/radians; quaternion consumers use xyzw. stamp_ns is a decimal
string; received_monotonic_ns is meaningful only inside host_clock_id. Without a
clock mapping, sensor age/fusion time is UNKNOWN. Epoch resets require an explicit
sink reset; a different frame string never implies a known transform.

Only trusted catalogue injection supplies private full-source paths. HTTP accepts
no paths, URLs, point buffers or commands. Request bounds: 128 KiB, 2–8 sources,
256 correspondences, 8 transforms, explicit bounded options. Missing live data is
null. This release's observation sink cannot claim Nav2/controller ingestion.

D1 port: callable(request: FusionRequest, sources: tuple[ResolvedSource, ...],
cancel: threading.Event, progress: Callable[[float], None], *, job_id: str) -> FusionProposal.
ResolvedSource supplies descriptor, private read-only snapshot SourceAsset and
lineage. Snapshots have a configurable aggregate 256 MiB job limit; original
source paths are never passed to D1 and snapshot hashes are checked after it
returns. Worker
must honor configured bounds/cancellation; manager rejects late/mismatched pins.
D1 owns alignment/quality algorithms. SYNTHETIC fixture transforms demonstrate
plumbing only and never assert registration quality. Manual review accepts an
explicit complete proposal transform set, with expected proposal_revision.

D2/C4 port: SceneSnapshotService.ingest("obstacle_frame", ObstacleFrame.to_dict()).
Scene defaults to 16 KiB/sample, 80 KiB across latest slots and 16 metadata
history entries; it rejects admission over the aggregate limit.
D3 port: ingest("collision_assessment", CollisionAssessment.to_dict()). Other
read-only ports: robot_pose, global_path, controller_local_trajectory,
costmap_snapshot, with the same observation clock/epoch/map envelope. No motion,
goal, lease or activation port. All components start explicitly, never at import.

Map-family v1 requires a non-null mapping session. A merged artifact does not
invent one: service emits an explicit deferred family link until a future legacy
adapter can represent synthetic provenance honestly. Multimap-fusion.v1 retains
all real source sessions and transforms separately. UNKNOWN occupancy is the
default; no free space is inferred from missing PCD points.

Changes to fields require a version bump, backward behavior, consumer impact and
updated examples. Version 0.1 is the first implemented release (no prior wire
compatibility). C2 consumes sources/jobs/review/export snapshots; C3 consumes
ScenePacket; C4 supplies observations; D1/D2/D3 implement the injected algorithms.

The final C1 implementation retains the v0.1 field set from the bootstrap commit.
Validation clarifications: pairwise edges are named-metric objects; a supplied
collision validity interval carries host_clock_id, start_monotonic_ns and
end_monotonic_ns. An empty interval means UNKNOWN, so scene omits it as a current
assessment. Consumers sending only an empty interval remain accepted. Scene
publishes collision only with a current exact obstacle epoch/sequence reference
and a valid same-host interval. No transform/clock correspondence is inferred.
