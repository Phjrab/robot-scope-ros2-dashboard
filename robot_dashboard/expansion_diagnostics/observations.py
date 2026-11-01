"""Real owner code, generated geometry, observed byte budgets; no validator substitute."""
import copy
from dataclasses import asdict
import hashlib
import os
from .measure import encoded, breakdown


def owners():
    from robot_dashboard.expansion_contracts import canonical, ObstacleFrame
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    from robot_dashboard.obstacle_fusion_core.consumer_port import C4CorePort, compact_frame
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import C1ObstacleProjection
    return canonical, ObstacleFrame, SceneSnapshotService, C4CorePort, compact_frame, C1ObstacleProjection


def sample(deps, family, count):
    from robot_dashboard.obstacle_runtime_adapter.messages import Identity, pointcloud2
    from tests.expansion_services.followup_composition import point_message
    from experiments.expansion_20261029.d2_perception.scenarios import scene
    if family == 'sparse':
        # Run the existing D2 representative input generator, unchanged.
        os.environ['D2_DEPENDENCY_ROOT'] = str(deps)
        from tests.expansion_d2.test_round2_ports import sample as sparse_sample
        s, raw = sparse_sample(count)
        return s, raw, None
    points, ground, _ = scene(cones=count, wall=False, body=False)
    identity = Identity('lidar', 'synthetic-1', 1, '1000000000', 'fixture-clock',
                        'odom', 1_000_000_000, 'fixture-host', 'tf-synthetic', 'a'*24, 'b'*64)
    raw = point_message(points, identity)
    return pointcloud2(raw, identity, origin_m=(0, 0, 0)), raw, ground


def attempt(function, *args, **kwargs):
    try:
        value = function(*args, **kwargs)
        return {'status': 'ACCEPTED' if value is not False else 'REJECTED', 'reason': None}
    except (ValueError, TypeError, KeyError) as exc:
        return {'status': 'REJECTED', 'reason': str(exc), 'exception': type(exc).__name__}


def capacity_case(deps, measure, family, count, metadata_bytes=0):
    canonical, Frame, Service, Port, compact, Projection = owners()
    s, raw, ground = sample(deps, family, count)
    from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
    normalized = measure.call('C4_PointCloud2_decode', pointcloud2, raw, s.identity, origin_m=s.origin_m)
    if 'metadata' in s.payload:
        normalized.payload['metadata'] = copy.deepcopy(s.payload['metadata'])
    s = normalized
    port = Port(canonical=canonical, validate_frame=Frame.from_dict,
                geometry_context=lambda _: {'ground': ground} if ground else {},
                clock_ns=lambda: 9_000_000_000 if family == 'sparse' else 1_000_000_010,
                processing_clock_id='d2-process-monotonic' if family == 'sparse' else 'fixture-host')
    core_status = attempt(measure.call, 'D2_C4CorePort_process_including_compaction', port.process, s)
    full = copy.deepcopy(port.last_result['obstacle_frame'])
    if metadata_bytes:
        full['health']['c7_explicit_metadata_fixture'] = 'x' * metadata_bytes
    observed = {}

    def observe_encoding(value):
        result = canonical(value)  # Same real wire validator, same default limit.
        observed['candidate'] = value
        return result

    compact_status = attempt(measure.call, 'D2_provenance_compaction', compact,
                             full, canonical=observe_encoding)
    candidate = observed.get('candidate')
    full_wire = attempt(measure.call, 'C1_full_frame_wire_validation', Frame.from_dict, full)
    service = Service(full['map_binding'], host_clock_id=full['host_clock_id'],
                      schema_version='0.2', clock=lambda: 1_050_000_000)
    full_ingest = attempt(service.ingest, 'obstacle_frame', full)
    # Independent service probes demonstrate validator vs ingest. They are not deliveries.
    probe = Service(full['map_binding'], host_clock_id=full['host_clock_id'], schema_version='0.2')
    compact_ingest = attempt(probe.ingest, 'obstacle_frame', candidate) if candidate else {'status': 'NOT_RUN'}
    projection = measure.call('C4_projection', Projection(Frame), candidate).to_dict() if candidate else None
    delivery = Service(full['map_binding'], host_clock_id=full['host_clock_id'],
                       schema_version='0.2', clock=lambda: 1_050_000_000)
    if compact_status['status'] == 'ACCEPTED':
        delivery_status = attempt(measure.call, 'C1_service_ingest', delivery.ingest, 'obstacle_frame', projection)
    else:
        delivery_status = {'status': 'NOT_SENT', 'reason': compact_status['reason']}
    snapshot = measure.call('C1_snapshot_and_contract_serialization', delivery.snapshot)
    wire = measure.call('C1_canonical_response_encoding', canonical, snapshot)
    from robot_dashboard.collision_geometry_core import assess
    from experiments.expansion_20261029.d3_collision_sim.fixtures import model, state
    robot = state()
    for key in ('source_epoch', 'frame_key', 'map_binding', 'clock_domain', 'host_clock_id'):
        robot[key] = copy.deepcopy(full[key])
    assessment = measure.call('D3_assess_full_retained_geometry', assess, model(), robot, full,
                              now_stamp_ns=10**9, now_clock_domain=full['clock_domain'], coverage='SPARSE')
    geometry_same = candidate is not None and [o['geometry'] for o in full['obstacles']] == [o['geometry'] for o in candidate['obstacles']]
    result = dict(family=family, requested_objects=count, objects=len(full['obstacles']),
        input_points=len(s.payload['xyz_m']), metadata_bytes=metadata_bytes,
        metadata_location='health.c7_explicit_metadata_fixture (post-core synthetic metadata)' if metadata_bytes else None,
        input_sha256=hashlib.sha256(raw['data']).hexdigest(), identity=s.identity.packet(),
        schema='C1 0.1 source / 0.2 service', raw_pointcloud_bytes=len(raw['data']),
        full=breakdown(full), compact=breakdown(candidate) if candidate else None,
        reserve_bytes=2048, projected_bytes=len(encoded(projection)) if projection else None,
        projection_added_bytes=len(encoded(projection))-len(encoded(candidate)) if projection else None,
        snapshot_bytes=len(wire), snapshot_sha256=hashlib.sha256(wire).hexdigest(),
        core_port=core_status, full_wire=full_wire, full_service_probe=full_ingest,
        compact_service_probe=compact_ingest, compactor=compact_status, actual_delivery=delivery_status,
        geometry_preserved=geometry_same, retained_core_objects=len(port.last_result['obstacle_frame']['obstacles']),
        d3=dict(severity=assessment['severity'], reason=assessment['reason'], bytes=len(encoded(assessment)),
                evidence='ACTUAL_CORE_INDEPENDENT_OF_DISPLAY_DELIVERY', full_geometry_input=True),
        c1_metrics=delivery.metrics())
    return result, full, candidate, snapshot


def exact_sample_boundary(frame):
    canonical, Frame, Service, *_ = owners()
    # Probe the actual 0.2 post-upgrade size boundary, without a relaxed service.
    from robot_dashboard.expansion_contracts.time_binding import upgrade_observation
    value = upgrade_observation(copy.deepcopy(frame))
    value['health']['c7_padding'] = ''
    target = 16 * 1024
    padding = target - len(canonical(value))
    if padding < 0:
        raise ValueError('SMALL_BOUNDARY_FIXTURE_REQUIRED')
    results = []
    for delta in (-1, 0, 1):
        item = copy.deepcopy(value)
        item['health']['c7_padding'] = 'x' * (padding + delta)
        svc = Service(item['map_binding'], host_clock_id=item['host_clock_id'], schema_version='0.2')
        results.append(dict(bytes=len(canonical(item)), wire=attempt(Frame.from_dict, item),
                            ingest=attempt(svc.ingest, 'obstacle_frame', item), objects=len(item['obstacles'])))
    return results


def fences(frame):
    _, _, Service, *_ = owners()
    now = [1_050_000_000]
    svc = Service(frame['map_binding'], host_clock_id=frame['host_clock_id'], schema_version='0.2', clock=lambda: now[0])
    assert svc.ingest('obstacle_frame', frame)
    good = svc.snapshot()
    rejected = copy.deepcopy(frame)
    rejected['health']['large'] = 'x' * 17000
    attempts = []
    for i in range(3):
        rejected['sequence'] = frame['sequence'] + i + 1
        attempts.append(attempt(svc.ingest, 'obstacle_frame', rejected))
    before = svc.snapshot()
    now[0] = int(frame['received_monotonic_ns']) + svc.max_age_ns + 1
    expired = svc.snapshot()
    svc.reset({**frame['map_binding'], 'revision': 'c'*64, 'generation': 1}, 'c7-map-1')
    map_reject = svc.ingest('obstacle_frame', frame)
    mismatch = Service(frame['map_binding'], host_clock_id='different-host', schema_version='0.2', clock=lambda: now[0])
    assert mismatch.ingest('obstacle_frame', frame)
    wrong_clock = mismatch.snapshot()
    history = Service(frame['map_binding'], host_clock_id=frame['host_clock_id'], schema_version='0.2', clock=lambda: 1_050_000_000)
    max_history = 0
    for i in range(40):
        item = copy.deepcopy(frame)
        item['sequence'] = i + 1
        assert history.ingest('obstacle_frame', item)
        max_history = max(max_history, history.metrics()['history_size'])
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import C1SceneSink, C1ObstacleProjection
    from robot_dashboard.expansion_contracts import ObstacleFrame
    sink_service = Service(frame['map_binding'], schema_version='0.2', host_clock_id=frame['host_clock_id'])
    assert sink_service.ingest('obstacle_frame', frame)
    returned = C1SceneSink(sink_service, obstacle_projection=C1ObstacleProjection(ObstacleFrame)).ingest(
        dict(obstacle_frame=frame, health={}, diagnostics=[], source_observation=None))
    sink_probe = dict(returned=returned, dropped=sink_service.metrics()['dropped'],
                      latest_sequence=sink_service.snapshot()['sources']['obstacle_frame']['sequence'],
                      condition='same source epoch/sequence rejected by actual C1; sink does not propagate False')
    return dict(sink_false_probe=sink_probe, repeated_size_rejects=attempts, initial_status=good['sources']['obstacle_frame']['status'],
        retained_sequence_before_expiry=before['sources']['obstacle_frame']['sequence'],
        receipt_unchanged=before['sources']['obstacle_frame']['received_age_ms'] == good['sources']['obstacle_frame']['received_age_ms'],
        expired_status=expired['sources']['obstacle_frame']['status'], expired_value=expired['obstacle_frame'],
        map_rejected=not map_reject, map_cleared=svc.snapshot()['obstacle_frame'] is None,
        clock_status=wrong_clock['sources']['obstacle_frame']['status'],
        clock_age_ms=wrong_clock['sources']['obstacle_frame']['received_age_ms'],
        history_max=max_history, history_limit=history.metrics()['history_limit'], replacements=40,
        service_dropped_counter=svc.metrics()['dropped'],
        note='Size exceptions occur before service.dropped increments; diagnostic rejection count is independent.')


def configuration():
    from robot_dashboard.obstacle_fusion_core.core import Limits
    from robot_dashboard.expansion_contracts.messages import MAX_DOCUMENT_BYTES
    from robot_dashboard.obstacle_runtime_adapter.runtime import MAX_SCENE_BYTES
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    from robot_dashboard.expansion_services.scene_assets import SceneAssets
    from robot_dashboard.expansion_services.catalogue import CatalogueAdapter
    from robot_dashboard.expansion_services.export import BundleStore
    import inspect
    return dict(d2=asdict(Limits()), wire_bytes=MAX_DOCUMENT_BYTES, c4_frame_bytes=MAX_SCENE_BYTES,
        scene_defaults={k:v.default for k,v in inspect.signature(SceneSnapshotService).parameters.items()
                        if v.default is not inspect.Parameter.empty and k != 'clock'},
        asset_defaults={k:v.default for k,v in inspect.signature(SceneAssets).parameters.items()},
        catalogue_defaults={k:v.default for k,v in inspect.signature(CatalogueAdapter).parameters.items()
                            if v.default is not inspect.Parameter.empty},
        export_defaults={k:v.default for k,v in inspect.signature(BundleStore).parameters.items()
                         if v.default is not inspect.Parameter.empty},
        source_inspected_constants=dict(c1_latest_bytes=81920, c1_response_reserve=16384,
            d2_service_reserve=2048, c3_asset_bytes=2097152, c3_asset_total_bytes=8388608,
            c3_asset_count=8), config_sha_note='Constants cite pinned owner sources; no runtime thresholds changed.')


def exact_compactor_boundary(frame):
    canonical, _, _, _, compact, _ = owners()
    value = copy.deepcopy(frame)
    value['health']['c7_padding'] = ''
    observed = {}
    def capture(v):
        data = canonical(v)
        observed['bytes'] = len(data)
        return data
    compact(value, canonical=capture)
    padding = 16384 - 2048 - observed['bytes']
    results = []
    for delta in (-1,0,1):
        item = copy.deepcopy(value)
        item['health']['c7_padding'] = 'x'*(padding+delta)
        status = attempt(compact, item, canonical=capture)
        results.append(dict(compact_bytes=observed['bytes'], reserve_bytes=2048,
                            total_bytes=observed['bytes']+2048, result=status))
    return results


def aggregate_and_asset_boundaries():
    from tests.expansion_runtime import latest_fixtures as fixtures
    from robot_dashboard.expansion_services.scene_assets import SceneAssets
    canonical, _, Service, *_ = owners()
    runtime, packet, state, clock = fixtures.setup(active=False)
    result = fixtures.run(runtime, packet, state)
    frame = runtime.ports.scene_obstacle(result.obstacle_frame)
    svc = Service(frame['map_binding'], schema_version='0.2', host_clock_id=frame['host_clock_id'], clock=clock)
    envelope_keys = ('schema_version','evidence_kind','producer','sequence','source_epoch','frame_key',
                     'stamp_ns','clock_domain','host_clock_id','received_monotonic_ns','map_binding')
    rows = []
    for slot in ('robot_pose','global_path','controller_local_trajectory','costmap_snapshot','obstacle_frame','collision_assessment'):
        if slot == 'obstacle_frame':
            item = copy.deepcopy(frame)
            item['health']['padding'] = ''
            destination = item['health']
        elif slot == 'collision_assessment':
            item = copy.deepcopy(result.assessment)
            item['freshness']['padding'] = ''
            destination = item['freshness']
        else:
            item = {k:copy.deepcopy(frame[k]) for k in envelope_keys}
            item.update(data={'padding':''}, health={})
            destination = item['data']
        destination['padding'] = 'x'*(16384-len(canonical(item)))
        response = attempt(svc.ingest,slot,item)
        rows.append(dict(slot=slot, bytes=len(canonical(item)), ingest=response, metrics=svc.metrics()))
    assets = SceneAssets()
    individual = []
    for size in (2097151,2097152,2097153):
        individual.append(dict(bytes=size,result=attempt(assets.publish,'live_cloud','single',b'x'*size)))
    assets.clear()
    aggregate = []
    for i,size in enumerate((2097152,2097152,2097152,2097152,1)):
        status = attempt(assets.publish,'live_cloud',f'asset-{i}',b'x'*size)
        aggregate.append(dict(added_bytes=size,result=status,retained_bytes=sum(r['bytes'] for r in assets.refs()),
                              items=len(assets.refs())))
    assets.clear()
    count = [attempt(assets.publish,'live_cloud',f'asset-{i}',b'x') for i in range(9)]
    assets.clear()
    return dict(latest_slots=rows, per_asset=individual, asset_total=aggregate,
                asset_count=count, after_clear_items=len(assets.refs()),
                classification='SYNTHETIC_METADATA_FILL; ACTUAL_C1_LIMITS; no collision geometry removed')


def exact_wire_boundary(frame):
    canonical, Frame, *_ = owners()
    value = copy.deepcopy(frame)
    value['health']['c7_padding'] = ''
    padding = 131072-len(encoded(value))
    results = []
    for delta in (-1,0,1):
        item = copy.deepcopy(value)
        item['health']['c7_padding'] = 'x'*(padding+delta)
        results.append(dict(bytes=len(encoded(item)), wire=attempt(Frame.from_dict,item)))
    return results
