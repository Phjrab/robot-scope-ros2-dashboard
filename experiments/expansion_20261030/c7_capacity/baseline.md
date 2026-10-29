# C7 offline capacity diagnostics

READ_ONLY_DIAGNOSTIC_NOT_DRIVING_AUTHORIZATION. Synthetic inputs; no robot/native execution.

Profile: `baseline`; generated: 2026-10-29T18:18:29.288596+00:00

## Status

| Check | Result |
|---|---|
| baseline | PASS |
| protected_sources | PASS |

## Exact source pins

| Owner | SHA |
|---|---|
| main | `5154761bba6fa4f171881e61f986901e2b415ed9` |
| C1 | `50600c7bce6f5fae743cd836ca1d8ee68d91b05a` |
| C2 | `7625c87ede2489143c44862d883e10fc1791df28` |
| C3 | `5bf58097f4a67806f5515b931a3b8013d65bf01e` |
| C4 | `7ac0d55b07abd20902d6d756c6b225733613fea7` |
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` |

## Payload boundaries

| Input | Objects | Metadata | Full B | Compact B | + reserve B | C4 projected B | Delivery |
|---|---:|---:|---:|---:|---:|---:|---|
| cone | 1 | 0 | 3544 | 2706 | 4754 | 2823 | ACCEPTED  |

Compaction rejection retains all core geometry; NOT_SENT does not claim C1/C3 received it.
Each full/compact partition is additive: geometry values, provenance values, input_sources, health, and remaining JSON bytes.

## Timings

Nearest-rank p50/p95, warm-up excluded. Small n is diagnostic, not a stable capacity estimate.

| Exact case / stage | n | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| baseline/cone/1/metadata0/D2_C4CorePort_process_including_compaction | 1 | 1.556 | 1.556 | 1.556 |
| baseline/cone/1/metadata0/D2_provenance_compaction | 1 | 0.128 | 0.128 | 0.128 |
| baseline/cone/1/metadata0/C1_full_frame_wire_validation | 1 | 0.201 | 0.201 | 0.201 |
| baseline/cone/1/metadata0/C4_projection | 1 | 0.121 | 0.121 | 0.121 |
| baseline/cone/1/metadata0/C1_service_ingest | 1 | 0.411 | 0.411 | 0.411 |
| baseline/cone/1/metadata0/C1_snapshot_and_contract_serialization | 1 | 0.489 | 0.489 | 0.489 |
| baseline/cone/1/metadata0/C1_canonical_response_encoding | 1 | 0.045 | 0.045 | 0.045 |
| baseline/cone/1/metadata0/D3_assess_full_retained_geometry | 1 | 9264.769 | 9264.769 | 9264.769 |

## process

```json
{
  "peak_rss_bytes": 92323840,
  "user_cpu_s": 0.7902739999999999,
  "system_cpu_s": 0.44675499999999996,
  "scope": "Whole diagnostic process including imports; cumulative high-water RSS, not per-stage memory"
}
```

## clocks

```json
{
  "operation_duration": "python.perf_counter_ns measured around the named real call",
  "CPU": "python.process_time_ns (process aggregate, excludes child processes)",
  "scenario": "explicit synthetic source/host clocks; never used as benchmark duration",
  "sensor_to_render_latency": "UNKNOWN: no measured source-host-browser clock mapping",
  "controller_execution": "NOT_RUN; receive intervals are not controller execution time"
}
```

## environment

```json
{
  "python": "3.13.2 (v3.13.2:4f8bb3947cf, Feb  4 2025, 11:51:10) [Clang 15.0.0 (clang-1500.3.9.4)]",
  "platform": "macOS-26.3-arm64-arm-64bit-Mach-O",
  "machine": "arm64",
  "node": "v22.17.1",
  "packages": {
    "numpy": "2.5.4",
    "scipy": "1.18.1",
    "fastapi": "0.162.0",
    "pydantic": "2.14.2",
    "httpx": "0.28.1"
  },
  "thread_environment": {
    "OPENBLAS_NUM_THREADS": "UNSET",
    "OMP_NUM_THREADS": "UNSET",
    "MKL_NUM_THREADS": "UNSET"
  },
  "load_average": [
    5.60107421875,
    4.77099609375,
    3.7275390625
  ],
  "concurrent_external_work": "NOT_CONTROLLED_OR_MEASURED; other chats/processes may overlap"
}
```

## configuration

```json
{
  "d2": {
    "max_points": 30000,
    "max_objects": 64,
    "voxel_m": 0.06,
    "range_m": 30.0,
    "ground_band_m": 0.025,
    "track_ttl_ns": 1000000000,
    "max_delay_ns": 150000000
  },
  "wire_bytes": 131072,
  "c4_frame_bytes": 524288,
  "scene_defaults": {
    "stream_epoch": "scene-0",
    "host_clock_id": "c1-host",
    "max_history": 16,
    "max_sample_bytes": 16384,
    "schema_version": "0.1",
    "max_age_ns": 500000000
  },
  "asset_defaults": {
    "max_bytes": 8388608,
    "max_asset_bytes": 2097152,
    "max_items": 8
  },
  "catalogue_defaults": {
    "preview": null,
    "max_sources": 128,
    "max_bytes": 268435456
  },
  "export_defaults": {
    "max_bytes": 268435456,
    "max_points": 20000000,
    "chunk_points": 16384,
    "max_cells": 1000000,
    "resolution": 0.25
  },
  "source_inspected_constants": {
    "c1_latest_bytes": 81920,
    "c1_response_reserve": 16384,
    "d2_service_reserve": 2048,
    "c3_asset_bytes": 2097152,
    "c3_asset_total_bytes": 8388608,
    "c3_asset_count": 8
  },
  "config_sha_note": "Constants cite pinned owner sources; no runtime thresholds changed."
}
```

## not measured

```json
[
  "ROS/native/device",
  "Jetson or real-time qualification",
  "physical disk I/O (logical reads only)",
  "sensor capture/transport latency",
  "controller function execution",
  "peak concurrent browser heap"
]
```
