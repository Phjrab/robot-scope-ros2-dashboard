"""Small baseline followed by a bounded sequential comparison; no product hooks."""
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
from .dependencies import PINS, activate, verify, git
from .measure import Measurements, fingerprint
from .observations import capacity_case, configuration, exact_sample_boundary, fences, exact_compactor_boundary, aggregate_and_asset_boundaries, exact_wire_boundary


def run_diagnostics(repo, deps, profile, node, browser_report=None, config_snapshot=None):
    sys.dont_write_bytecode = True
    repo, deps = Path(repo).resolve(), Path(deps).resolve()
    verified = verify(repo, deps)
    activate(deps)
    config = configuration()
    if config_snapshot:
        import json
        expected = json.loads(Path(config_snapshot).read_text())
        expected = expected.get('configuration', expected)
        if expected != config:
            raise ValueError('CONFIG_SNAPSHOT_MISMATCH; no limits or clocks were changed')
    measurement = Measurements()
    measurement.case = 'baseline/cone/1/metadata0'
    # Exactly one small baseline before any comparative workload.
    baseline, full, candidate, snapshot = capacity_case(deps, measurement, 'cone', 1)
    result = dict(report_version='c7-diagnostic-1', generated_utc=datetime.now(timezone.utc).isoformat(),
        profile=profile, purpose='READ_ONLY_DIAGNOSTIC_NOT_DRIVING_AUTHORIZATION', pins=PINS,
        verification_before=verified, diagnostic_head=git(repo, 'rev-parse', 'HEAD').decode().strip(),
        diagnostic_source_sha256={}, diagnostic_working_tree=git(repo,'status','--porcelain').decode().strip(),
        environment=dict(python=sys.version, platform=platform.platform(), machine=platform.machine(),
            node=subprocess.check_output([node, '--version'], text=True).strip(),
            packages={n: importlib.metadata.version(n) for n in ('numpy','scipy','fastapi','pydantic','httpx')},
            thread_environment={k:os.environ.get(k, 'UNSET') for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
            load_average=os.getloadavg(), concurrent_external_work='NOT_CONTROLLED_OR_MEASURED; other chats/processes may overlap'),
        configuration=config, config_sha256=fingerprint(config), baseline=baseline, cases=[],
        clocks=dict(operation_duration='python.perf_counter_ns measured around the named real call',
            CPU='python.process_time_ns (process aggregate, excludes child processes)',
            scenario='explicit synthetic source/host clocks; never used as benchmark duration',
            sensor_to_render_latency='UNKNOWN: no measured source-host-browser clock mapping',
            controller_execution='NOT_RUN; receive intervals are not controller execution time'),
        checks={'baseline': 'PASS' if baseline['actual_delivery']['status'] == 'ACCEPTED' else 'FAIL'},
        not_measured=['ROS/native/device', 'Jetson or real-time qualification', 'physical disk I/O (logical reads only)',
                      'sensor capture/transport latency', 'controller function execution', 'peak concurrent browser heap'])
    import hashlib
    for p in sorted(Path(__file__).parent.glob('*')):
        if p.is_file():
            result['diagnostic_source_sha256'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    if profile == 'bounded':
        for family in ('sparse', 'cone'):
            for size in (0, 1, 4, 12, 16, 32):
                for metadata in (0, 4096):
                    measurement.case = f'{family}/{size}/metadata{metadata}'
                    for rep in range(4):
                        measurement.warmup = rep == 0
                        row, _, _, _ = capacity_case(deps, measurement, family, size, metadata)
                    result['cases'].append(row)
        measurement.warmup = False
        # Only two extra object counts around the demonstrated cone 12..16 transition.
        for count in (14,15):
            measurement.case = f'cone/{count}/metadata0_boundary'
            row, _, _, _ = capacity_case(deps,measurement,'cone',count)
            result['cases'].append(row)
        result['first_observed_rejections'] = []
        for family in ('sparse','cone'):
            for metadata in (0,4096):
                rejected = sorted((r for r in result['cases'] if r['family']==family and r['metadata_bytes']==metadata
                                   and r['actual_delivery']['status']!='ACCEPTED'), key=lambda r:r['requested_objects'])
                if rejected:
                    first = rejected[0]
                    result['first_observed_rejections'].append(dict(family=family,metadata_bytes=metadata,
                        first_observed_objects=first['requested_objects'], reason=first['actual_delivery']['reason'],
                        scope='FIRST_SAMPLED_FAILURE; only cone metadata0 has adjacent 15/16 check'))
        result['exact_sample_boundary'] = exact_sample_boundary(candidate)
        result['exact_compactor_boundary'] = exact_compactor_boundary(full)
        result['exact_wire_boundary'] = exact_wire_boundary(candidate)
        result['aggregate_and_assets'] = aggregate_and_asset_boundaries()
        result['fences'] = fences(candidate)
        from .workloads import queue_probe, canonical_composition, map_probe
        import asyncio
        result['queue'] = asyncio.run(queue_probe(deps))
        result['composition'] = canonical_composition(deps, measurement, node)
        result['maps'] = map_probe(measurement)
        import json
        cache = subprocess.run([node,str(Path(__file__).with_name('cache.mjs')),str(deps)],capture_output=True,text=True,timeout=30)
        result['c3_cache'] = json.loads(cache.stdout) if cache.returncode == 0 else dict(status='FAIL',reason=cache.stderr)
        result['checks']['c3_cache'] = result['c3_cache']['status']
        result['counts'] = dict(case_inputs_including_warmup=1+24*4+2, measured_case_inputs=1+24*3+2, core_processing_attempts=1+24*4+2,
            table_cases=len(result['cases']), table_delivered=sum(x['actual_delivery']['status']=='ACCEPTED' for x in result['cases']),
            table_not_sent=sum(x['actual_delivery']['status']=='NOT_SENT' for x in result['cases']),
            note='Table counts are one retained result per case; repetitions include one excluded warm-up. Queue/C4 composition counters separate.')
        result['checks'].update(
            exact_sample_boundary='PASS' if [v['ingest']['status'] for v in result['exact_sample_boundary']] == ['ACCEPTED','ACCEPTED','REJECTED'] else 'FAIL',
            exact_wire_boundary='PASS' if [v['wire']['status'] for v in result['exact_wire_boundary']] == ['ACCEPTED','ACCEPTED','REJECTED'] else 'FAIL',
            exact_compactor_boundary='PASS' if [v['result']['status'] for v in result['exact_compactor_boundary']] == ['ACCEPTED','ACCEPTED','REJECTED'] else 'FAIL',
            aggregate_and_assets='PASS' if result['aggregate_and_assets']['latest_slots'][-1]['ingest']['status']=='REJECTED' and result['aggregate_and_assets']['asset_total'][-1]['result']['status']=='REJECTED' else 'FAIL',
            full_geometry='PASS' if all(r['geometry_preserved'] and r['objects'] == r['retained_core_objects'] for r in result['cases']) else 'FAIL',
            stale_map_clock='PASS' if result['fences']['expired_value'] is None and result['fences']['map_rejected'] and result['fences']['clock_status'] == 'unavailable' else 'FAIL',
            bounded_queue='PASS' if result['queue']['pending_max'] <= 1 and result['queue']['processed'] == 2 else 'FAIL',
            canonical_connection=result['composition']['status'])
    if browser_report:
        import json
        browser = json.loads(Path(browser_report).read_text())
        if browser.get('c3_sha') != PINS['C3']:
            raise ValueError('BROWSER_EVIDENCE_PIN_MISMATCH')
        result['browser'] = dict(evidence=browser, sha256=hashlib.sha256(Path(browser_report).read_bytes()).hexdigest(),
                                kind='SAVED_TRACE_SEPARATE_RUN_NO_CROSS_RUN_SPEEDUP')
        result['checks']['browser_load'] = 'PASS' if browser.get('exit_code') == 0 and not browser.get('failure') else 'FAIL'
    else:
        result['checks']['browser_load'] = 'NOT_RUN'
    result['import_origins'] = {}
    for role, package in [('C1','expansion_contracts'),('C1','expansion_services'),('D1','multimap_core'),
                          ('D2','obstacle_fusion_core'),('D3','collision_geometry_core'),
                          ('C4','expansion_runtime'),('C4','obstacle_runtime_adapter')]:
        module = sys.modules.get('robot_dashboard.'+package)
        if module:
            relative = Path(module.__file__).resolve().relative_to(deps / role)
            result['import_origins'][package] = dict(owner=role, relative_path=str(relative), sha=PINS[role])
    result['timing_events'] = measurement.events
    result['timings'] = measurement.summary()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result['process'] = dict(peak_rss_bytes=usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
        user_cpu_s=usage.ru_utime, system_cpu_s=usage.ru_stime,
        scope='Whole diagnostic process including imports; cumulative high-water RSS, not per-stage memory')
    result['verification_after'] = verify(repo, deps)
    result['checks']['protected_sources'] = 'PASS' if result['verification_after'] == verified else 'FAIL'
    return result
