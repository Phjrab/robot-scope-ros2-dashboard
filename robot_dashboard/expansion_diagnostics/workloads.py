"""Bounded queue, canonical composition and logical PCD I/O probes."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from .measure import encoded, fingerprint, stats
from .observations import owners, sample


async def queue_probe(deps):
    from robot_dashboard.obstacle_runtime_adapter.runtime import RuntimeAdapter
    from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
    from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
    from robot_dashboard.obstacle_runtime_adapter.c1_ports import C1SceneSink
    canonical, Frame, Service, Port, _, Projection = owners()
    value, raw, ground = sample(deps, 'cone', 1)
    started, release = threading.Event(), threading.Event()
    timings = []
    core = Port(canonical=canonical, validate_frame=Frame.from_dict,
                geometry_context=lambda _: {'ground': ground})

    class DelayedCore:
        def process(self, item):
            entered = time.monotonic_ns()
            started.set()
            if not release.wait(2):
                raise RuntimeError('C7_DELAY_GATE_TIMEOUT')
            begin = time.monotonic_ns()
            result = core.process(item)
            timings.append(dict(sequence=item.identity.sequence, injected_wait_ms=(begin-entered)/1e6,
                                real_core_ms=(time.monotonic_ns()-begin)/1e6))
            return result

    identity = replace(value.identity, received_ns=time.monotonic_ns(), receipt_clock_id='c7-monotonic')
    svc = Service(identity.packet()['map_binding'], schema_version='0.2', host_clock_id='c7-monotonic')
    runtime = RuntimeAdapter(d2=DelayedCore(), scene_sink=C1SceneSink(svc, obstacle_projection=Projection(Frame)),
        validate_obstacle=Frame.from_dict, source_epochs={'lidar': identity.source_epoch}, binding=identity.binding,
        receipt_clock_id='c7-monotonic', config=RuntimeConfig(mode='synthetic'))
    pending_max = accepted = 0
    runtime.start()
    try:
        for i in range(60):
            item = replace(identity, sequence=i+1, stamp_ns=str(10**9+i), received_ns=time.monotonic_ns())
            message = dict(raw, header=dict(raw['header'], stamp=dict(sec=1, nanosec=i)))
            accepted += runtime.offer_raw(message, item, pointcloud2, origin_m=(0,0,0))
            pending_max = max(pending_max, runtime.worker.queue.qsize())
            if i == 0:
                deadline = time.monotonic()+2
                while not started.is_set():
                    if time.monotonic() > deadline:
                        raise TimeoutError('worker did not start')
                    await asyncio.sleep(.001)
        release.set()
        await asyncio.wait_for(runtime.worker.queue.join(), 5)
        health = runtime.health()
        packet = svc.snapshot()
        result = dict(evidence_kind='ACTUAL_C4_WORKER_AND_D2_CORE_WITH_EXPLICIT_DELAY_GATE',
            input=60, accepted_at_ingress=accepted, processed=len(timings),
            replaced_pending=runtime.worker.dropped, invalid=runtime.worker.invalid,
            rejected=runtime.rejected, stale_or_superseded_results=runtime.late_results,
            latest_replacements=svc.snapshot()['sequence'], pending_max=pending_max,
            executing_limit=1, pending_limit=runtime.worker.queue.maxsize,
            displayed_sequence=packet['sources']['obstacle_frame'].get('sequence'),
            timings=timings, latest_health=health, history=svc.metrics(),
            end_to_end_latency='UNKNOWN_SOURCE_CLOCK_MAPPING',
            accounting='60 ingress = 58 pending replacements + 2 processed; first result superseded, one service replacement')
    finally:
        release.set()
        await runtime.close()
    result['queue_after_close'] = runtime.worker.queue.qsize()
    result['latest_after_close'] = runtime.latest_scene
    return result


def canonical_composition(deps, measure, node):
    from tests.expansion_runtime import latest_fixtures as fixtures
    records, snapshots = [], []
    measure.case = 'current_C4_D2_D3_C1'
    for i in range(4):
        measure.warmup = i == 0
        runtime, packet, state, clock = fixtures.setup(active=False)
        # Observe public port calls, forwarding unchanged arguments/results. Owner source is immutable.
        for name in ('perceive', 'assess', 'canonical_assessment'):
            original = getattr(runtime.ports, name)
            setattr(runtime.ports, name, lambda *a, _fn=original, _stage=name, **kw:
                    measure.call('C4_port_' + _stage, _fn, *a, **kw))
        result = measure.call('C4_Runtime_process', fixtures.run, runtime, packet, state)
        if result.assessment is None:
            measure.warmup = False
            return dict(status='FAIL', reason=result.intent.reason, stage='C4 Runtime', evidence_kind='ACTUAL_CODE')
        try:
            service = measure.call('C4_compact_and_C1_ingest_scene', fixtures.scene, runtime, result, clock)
            raw = measure.call('C1_ASGI_HTTP_response_including_fixture_setup', fixtures.http_snapshot, service)
        except (ValueError, TypeError, KeyError, AssertionError) as exc:
            measure.warmup = False
            return dict(status='FAIL', reason=str(exc), stage='C4_C1_SCENE_HTTP', evidence_kind='ACTUAL_CODE')
        snapshots.append(raw)
        import hashlib
        records.append(dict(bytes=len(raw.encode()), sha256=hashlib.sha256(raw.encode()).hexdigest(), canonical_sha256=fingerprint(json.loads(raw)),
                            severity=result.intent.severity, reason=result.intent.reason,
                            fixture_timing=result.timing, fixture_timing_is_benchmark=False))
    measure.warmup = False
    js = subprocess.run([node, str(Path(__file__).with_name('consumer.mjs'))],
        input=json.dumps({'deps':str(deps),'raw':snapshots[-1]}), text=True, capture_output=True, timeout=30)
    consumer = json.loads(js.stdout) if js.stdout else {'status':'FAIL','reason':js.stderr}
    if consumer.get('timings'):
        consumer['timing_summary'] = {stage:stats([e[stage] for e in consumer['timings'] if not e['warmup']])
                                     for stage in ('parse_ms','adapt_ms','consume_ms')}
    return dict(status=consumer['status'], actual_http='ASGI_IN_PROCESS_NO_TCP',
        input='C4 existing latest_fixtures; actual numerical cores; explicit generated clock mapping',
        results=records, c3=consumer, product_enforcement=False,
        end_to_end_latency='UNKNOWN; Python and JS clocks have no mapping',
        full_render='NOT_RUN_FOR_THIS_COMMAND_ASSESSMENT; absent pose/joints/path must stay unavailable')


def map_probe(measure):
    """Count actual logical source reads via transparent stream wrapper; no I/O cache patch."""
    from experiments.expansion_20261029.d1_multimap.generate import fixture
    from tests.expansion_services.composition import records
    from robot_dashboard.expansion_contracts.fixtures import source, request
    from robot_dashboard.expansion_contracts import FusionProposal
    from robot_dashboard.expansion_services.catalogue import CatalogueAdapter, ResolvedSource
    from robot_dashboard.expansion_services.export import BundleStore
    from robot_dashboard.multimap_core.contract_adapter import solve_contract
    from robot_dashboard.pcd_editing.store import SourceAsset
    import robot_dashboard.pcd_editing.store as io_owner
    import robot_dashboard.expansion_services.export as export_owner
    from contextlib import contextmanager
    results = []
    with tempfile.TemporaryDirectory(prefix='c7-maps-') as tmp:
        for count in (400, 20000, 200000):
            root = Path(tmp).resolve()/str(count)
            root.mkdir()
            raw, resolver, poses = fixture(root, count=count)
            resolved, previews = {}, {}
            for index, d in enumerate(raw[:2]):
                data, n = records(resolver(d))
                descriptor = replace(source(index+1, d['sha256']), revision=d['sha256'], point_count=n,
                    point_schema=[dict(name=k,size=4,type='F',count=1) for k in data.dtype.names])
                previews[descriptor.map_id] = {'evidence_kind':'SYNTHETIC','points_m':data[['x','y','z']][:160].tolist()}
                resolved[descriptor.map_id] = ResolvedSource(descriptor, SourceAsset(descriptor.map_id,
                    descriptor.revision, resolver(d), descriptor.frame_id))
            catalogue = CatalogueAdapter(lambda: list(resolved), lambda key: resolved[key],
                preview=lambda d: previews[d.map_id])
            store = BundleStore(root/'bundles', catalogue)
            req = replace(request([s.descriptor for s in resolved.values()]), options={},
                initial_guesses=[dict(source_key=s.descriptor.key, T_anchor_source=poses[i].reshape(-1).tolist())
                                 for i,s in enumerate(resolved.values()) if i > 0])
            measure.case = f'map/{count}_per_source'
            if count == 400:
                paths = {s.descriptor.map_id:s.asset.path for s in resolved.values()}
                proposal = measure.call('D1_solve_contract_small_only', solve_contract, req,
                    lambda d:paths[d['map_id']], FusionProposal, job_id='0000000000000000000000c7')
            else:
                # Export-only scaling: transforms are supplied fixture truth, not a measured large-map solve.
                proposal = replace(proposal, anchor_source_key=req.anchor_source_key, input_pins=req.source_pins,
                    pairwise_edges=[], connected_components=[], quality={'status':'NOT_MEASURED_EXPORT_ONLY'},
                    ambiguous_candidates=[], warnings=['C7 supplied generator transforms; no large-map solver result'],
                    solver_version='c7-generator-transform-fixture', elapsed_ms=0,
                    T_fused_source={s.descriptor.key:poses[i].reshape(-1).tolist()
                                                          for i,s in enumerate(resolved.values())})
            io = {'read_bytes':0,'opens':0}
            original = io_owner._open_regular

            class CountingStream:
                def __init__(self, stream):
                    self.stream = stream
                def read(self, *args):
                    data = self.stream.read(*args)
                    io['read_bytes'] += len(data)
                    return data
                def readline(self, *args):
                    data = self.stream.readline(*args)
                    io['read_bytes'] += len(data)
                    return data
                def __getattr__(self, name):
                    return getattr(self.stream, name)

            @contextmanager
            def counted(*args, **kwargs):
                with original(*args, **kwargs) as stream:
                    io['opens'] += 1
                    yield CountingStream(stream)

            io_owner._open_regular = counted
            export_owner._open_regular = counted
            measurements = []
            try:
                for operation, fn in (
                    ('source_list', catalogue.list),
                    ('source_preview_160', lambda: catalogue.preview(next(iter(resolved)))),
                    ('full_export', lambda: store.save(req, proposal, 'c7-generated', threading.Event(), {'c7':'SYNTHETIC_EXPORT_ONLY'})),
                    ('bundle_list', store.list)):
                    for rep in range(1 if operation == 'full_export' else 4):
                        measure.warmup = rep == 0 and operation != 'full_export'
                        io.update(read_bytes=0, opens=0)
                        value = measure.call(operation, fn)
                        measurements.append(dict(operation=operation, warmup=measure.warmup, **io,
                            returned_bytes=len(encoded(value)),
                            output_points=value.get('point_count') if isinstance(value,dict) else None))
            finally:
                io_owner._open_regular = original
                export_owner._open_regular = original
                measure.warmup = False
            results.append(dict(points_per_source=count, source_bytes=sum(s.asset.path.stat().st_size for s in resolved.values()),
                input_hashes=[d['sha256'] for d in raw[:2]], measurements=measurements,
                solver='ACTUAL_D1' if count == 400 else 'NOT_RUN_LARGE_MAP; GIVEN_GENERATOR_TRANSFORMS_EXPORT_ONLY',
                limits=dict(max_source_bytes=catalogue.max_bytes,max_export_bytes=store.max_bytes,
                    chunk_points=store.chunk_points,max_points=store.max_points),
                IO='ACTUAL_LOGICAL_READ_BYTES; OS disk cache state uncontrolled; generator time excluded'))
    return results
