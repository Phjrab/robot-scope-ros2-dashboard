# C7 offline capacity diagnostics

READ_ONLY_DIAGNOSTIC_NOT_DRIVING_AUTHORIZATION. Synthetic inputs; no robot/native execution.

Profile: `bounded`; generated: 2026-10-29T18:37:47.149930+00:00

## Status

| Check | Result |
|---|---|
| baseline | PASS |
| c3_cache | PASS |
| exact_sample_boundary | PASS |
| exact_wire_boundary | PASS |
| exact_compactor_boundary | PASS |
| aggregate_and_assets | PASS |
| full_geometry | PASS |
| stale_map_clock | PASS |
| bounded_queue | PASS |
| canonical_connection | PASS |
| browser_load | PASS |
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
| sparse | 0 | 0 | 1838 | 1885 | 3933 | 2002 | ACCEPTED  |
| sparse | 0 | 4096 | 5968 | 6015 | 8063 | 6132 | ACCEPTED  |
| sparse | 1 | 0 | 3331 | 2525 | 4573 | 2642 | ACCEPTED  |
| sparse | 1 | 4096 | 7461 | 6655 | 8703 | 6772 | ACCEPTED  |
| sparse | 4 | 0 | 7813 | 4448 | 6496 | 4565 | ACCEPTED  |
| sparse | 4 | 4096 | 11943 | 8578 | 10626 | 8695 | ACCEPTED  |
| sparse | 12 | 0 | 19768 | 9579 | 11627 | 9696 | ACCEPTED  |
| sparse | 12 | 4096 | 23898 | 13709 | 15757 | 13826 | ACCEPTED  |
| sparse | 16 | 0 | 25748 | 12147 | 14195 | 12264 | ACCEPTED  |
| sparse | 16 | 4096 | 29878 | 16277 | 18325 | 16394 | NOT_SENT FRAME_BUDGET_EXCEEDED:16277+2048>16384 |
| sparse | 32 | 0 | 49668 | 22419 | 24467 | 22536 | NOT_SENT FRAME_BUDGET_EXCEEDED:22419+2048>16384 |
| sparse | 32 | 4096 | 53798 | 26549 | 28597 | 26666 | NOT_SENT FRAME_BUDGET_EXCEEDED:26549+2048>16384 |
| cone | 0 | 0 | 1867 | 1914 | 3962 | 2031 | ACCEPTED  |
| cone | 0 | 4096 | 5997 | 6044 | 8092 | 6161 | ACCEPTED  |
| cone | 1 | 0 | 3544 | 2706 | 4754 | 2823 | ACCEPTED  |
| cone | 1 | 4096 | 7674 | 6836 | 8884 | 6953 | ACCEPTED  |
| cone | 4 | 0 | 8620 | 5127 | 7175 | 5244 | ACCEPTED  |
| cone | 4 | 4096 | 12750 | 9257 | 11305 | 9374 | ACCEPTED  |
| cone | 12 | 0 | 22123 | 11550 | 13598 | 11667 | ACCEPTED  |
| cone | 12 | 4096 | 26253 | 15680 | 17728 | 15797 | NOT_SENT FRAME_BUDGET_EXCEEDED:15680+2048>16384 |
| cone | 16 | 0 | 28876 | 14763 | 16811 | 14880 | NOT_SENT FRAME_BUDGET_EXCEEDED:14763+2048>16384 |
| cone | 16 | 4096 | 33006 | 18893 | 20941 | 19010 | NOT_SENT FRAME_BUDGET_EXCEEDED:18893+2048>16384 |
| cone | 32 | 0 | 55904 | 27631 | 29679 | 27748 | NOT_SENT FRAME_BUDGET_EXCEEDED:27631+2048>16384 |
| cone | 32 | 4096 | 60034 | 31761 | 33809 | 31878 | NOT_SENT FRAME_BUDGET_EXCEEDED:31761+2048>16384 |
| cone | 14 | 0 | 25500 | 13157 | 15205 | 13274 | ACCEPTED  |
| cone | 15 | 0 | 27195 | 13967 | 16015 | 14084 | ACCEPTED  |

Compaction rejection retains all core geometry; NOT_SENT does not claim C1/C3 received it.
Each full/compact partition is additive: geometry values, provenance values, input_sources, health, and remaining JSON bytes.

## Timings

Nearest-rank p50/p95, warm-up excluded. Small n is diagnostic, not a stable capacity estimate.

| Exact case / stage | n | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| baseline/cone/1/metadata0/C4_PointCloud2_decode | 1 | 0.996 | 0.996 | 0.996 |
| baseline/cone/1/metadata0/D2_C4CorePort_process_including_compaction | 1 | 2.056 | 2.056 | 2.056 |
| baseline/cone/1/metadata0/D2_provenance_compaction | 1 | 0.125 | 0.125 | 0.125 |
| baseline/cone/1/metadata0/C1_full_frame_wire_validation | 1 | 0.198 | 0.198 | 0.198 |
| baseline/cone/1/metadata0/C4_projection | 1 | 0.121 | 0.121 | 0.121 |
| baseline/cone/1/metadata0/C1_service_ingest | 1 | 0.406 | 0.406 | 0.406 |
| baseline/cone/1/metadata0/C1_snapshot_and_contract_serialization | 1 | 0.403 | 0.403 | 0.403 |
| baseline/cone/1/metadata0/C1_canonical_response_encoding | 1 | 0.036 | 0.036 | 0.036 |
| baseline/cone/1/metadata0/D3_assess_full_retained_geometry | 1 | 231.617 | 231.617 | 231.617 |
| sparse/0/metadata0/C4_PointCloud2_decode | 3 | 0.009 | 0.010 | 0.010 |
| sparse/0/metadata0/D2_C4CorePort_process_including_compaction | 3 | 0.292 | 0.326 | 0.326 |
| sparse/0/metadata0/D2_provenance_compaction | 3 | 0.068 | 0.070 | 0.070 |
| sparse/0/metadata0/C1_full_frame_wire_validation | 3 | 0.095 | 0.097 | 0.097 |
| sparse/0/metadata0/C4_projection | 3 | 0.081 | 0.087 | 0.087 |
| sparse/0/metadata0/C1_service_ingest | 3 | 0.391 | 0.556 | 0.556 |
| sparse/0/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.337 | 0.364 | 0.364 |
| sparse/0/metadata0/C1_canonical_response_encoding | 3 | 0.028 | 0.029 | 0.029 |
| sparse/0/metadata0/D3_assess_full_retained_geometry | 3 | 0.339 | 0.386 | 0.386 |
| sparse/0/metadata4096/C4_PointCloud2_decode | 3 | 0.009 | 0.009 | 0.009 |
| sparse/0/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 0.272 | 0.272 | 0.272 |
| sparse/0/metadata4096/D2_provenance_compaction | 3 | 0.080 | 0.080 | 0.080 |
| sparse/0/metadata4096/C1_full_frame_wire_validation | 3 | 0.111 | 0.113 | 0.113 |
| sparse/0/metadata4096/C4_projection | 3 | 0.086 | 0.087 | 0.087 |
| sparse/0/metadata4096/C1_service_ingest | 3 | 0.347 | 0.347 | 0.347 |
| sparse/0/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.350 | 0.351 | 0.351 |
| sparse/0/metadata4096/C1_canonical_response_encoding | 3 | 0.045 | 0.048 | 0.048 |
| sparse/0/metadata4096/D3_assess_full_retained_geometry | 3 | 0.285 | 0.290 | 0.290 |
| sparse/1/metadata0/C4_PointCloud2_decode | 3 | 0.010 | 0.010 | 0.010 |
| sparse/1/metadata0/D2_C4CorePort_process_including_compaction | 3 | 0.441 | 0.449 | 0.449 |
| sparse/1/metadata0/D2_provenance_compaction | 3 | 0.113 | 0.118 | 0.118 |
| sparse/1/metadata0/C1_full_frame_wire_validation | 3 | 0.175 | 0.179 | 0.179 |
| sparse/1/metadata0/C4_projection | 3 | 0.116 | 0.117 | 0.117 |
| sparse/1/metadata0/C1_service_ingest | 3 | 0.393 | 0.394 | 0.394 |
| sparse/1/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.389 | 0.391 | 0.391 |
| sparse/1/metadata0/C1_canonical_response_encoding | 3 | 0.033 | 0.038 | 0.038 |
| sparse/1/metadata0/D3_assess_full_retained_geometry | 3 | 0.574 | 0.614 | 0.614 |
| sparse/1/metadata4096/C4_PointCloud2_decode | 3 | 0.010 | 0.010 | 0.010 |
| sparse/1/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 0.471 | 0.476 | 0.476 |
| sparse/1/metadata4096/D2_provenance_compaction | 3 | 0.125 | 0.128 | 0.128 |
| sparse/1/metadata4096/C1_full_frame_wire_validation | 3 | 0.196 | 0.203 | 0.203 |
| sparse/1/metadata4096/C4_projection | 3 | 0.126 | 0.127 | 0.127 |
| sparse/1/metadata4096/C1_service_ingest | 3 | 0.475 | 0.541 | 0.541 |
| sparse/1/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.489 | 2.542 | 2.542 |
| sparse/1/metadata4096/C1_canonical_response_encoding | 3 | 0.056 | 0.056 | 0.056 |
| sparse/1/metadata4096/D3_assess_full_retained_geometry | 3 | 0.623 | 0.628 | 0.628 |
| sparse/4/metadata0/C4_PointCloud2_decode | 3 | 0.012 | 0.025 | 0.025 |
| sparse/4/metadata0/D2_C4CorePort_process_including_compaction | 3 | 0.885 | 0.949 | 0.949 |
| sparse/4/metadata0/D2_provenance_compaction | 3 | 0.229 | 0.232 | 0.232 |
| sparse/4/metadata0/C1_full_frame_wire_validation | 3 | 0.389 | 0.395 | 0.395 |
| sparse/4/metadata0/C4_projection | 3 | 0.218 | 0.218 | 0.218 |
| sparse/4/metadata0/C1_service_ingest | 3 | 0.730 | 0.735 | 0.735 |
| sparse/4/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.673 | 0.676 | 0.676 |
| sparse/4/metadata0/C1_canonical_response_encoding | 3 | 0.056 | 0.056 | 0.056 |
| sparse/4/metadata0/D3_assess_full_retained_geometry | 3 | 1.289 | 1.385 | 1.385 |
| sparse/4/metadata4096/C4_PointCloud2_decode | 3 | 0.013 | 0.013 | 0.013 |
| sparse/4/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 0.883 | 0.903 | 0.903 |
| sparse/4/metadata4096/D2_provenance_compaction | 3 | 0.240 | 0.244 | 0.244 |
| sparse/4/metadata4096/C1_full_frame_wire_validation | 3 | 0.406 | 0.414 | 0.414 |
| sparse/4/metadata4096/C4_projection | 3 | 0.234 | 0.234 | 0.234 |
| sparse/4/metadata4096/C1_service_ingest | 3 | 0.801 | 0.808 | 0.808 |
| sparse/4/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.725 | 0.754 | 0.754 |
| sparse/4/metadata4096/C1_canonical_response_encoding | 3 | 0.072 | 0.073 | 0.073 |
| sparse/4/metadata4096/D3_assess_full_retained_geometry | 3 | 1.291 | 1.336 | 1.336 |
| sparse/12/metadata0/C4_PointCloud2_decode | 3 | 0.018 | 0.018 | 0.018 |
| sparse/12/metadata0/D2_C4CorePort_process_including_compaction | 3 | 2.032 | 2.055 | 2.055 |
| sparse/12/metadata0/D2_provenance_compaction | 3 | 0.539 | 0.540 | 0.540 |
| sparse/12/metadata0/C1_full_frame_wire_validation | 3 | 0.954 | 0.963 | 0.963 |
| sparse/12/metadata0/C4_projection | 3 | 0.494 | 0.500 | 0.500 |
| sparse/12/metadata0/C1_service_ingest | 3 | 1.624 | 1.669 | 1.669 |
| sparse/12/metadata0/C1_snapshot_and_contract_serialization | 3 | 1.440 | 1.465 | 1.465 |
| sparse/12/metadata0/C1_canonical_response_encoding | 3 | 0.106 | 0.110 | 0.110 |
| sparse/12/metadata0/D3_assess_full_retained_geometry | 3 | 3.221 | 3.258 | 3.258 |
| sparse/12/metadata4096/C4_PointCloud2_decode | 3 | 0.019 | 0.022 | 0.022 |
| sparse/12/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 2.219 | 2.439 | 2.439 |
| sparse/12/metadata4096/D2_provenance_compaction | 3 | 0.750 | 1.218 | 1.218 |
| sparse/12/metadata4096/C1_full_frame_wire_validation | 3 | 1.197 | 1.552 | 1.552 |
| sparse/12/metadata4096/C4_projection | 3 | 0.563 | 0.595 | 0.595 |
| sparse/12/metadata4096/C1_service_ingest | 3 | 1.720 | 2.555 | 2.555 |
| sparse/12/metadata4096/C1_snapshot_and_contract_serialization | 3 | 1.563 | 2.365 | 2.365 |
| sparse/12/metadata4096/C1_canonical_response_encoding | 3 | 0.129 | 0.136 | 0.136 |
| sparse/12/metadata4096/D3_assess_full_retained_geometry | 3 | 3.306 | 4.262 | 4.262 |
| sparse/16/metadata0/C4_PointCloud2_decode | 3 | 0.021 | 0.021 | 0.021 |
| sparse/16/metadata0/D2_C4CorePort_process_including_compaction | 3 | 2.580 | 2.614 | 2.614 |
| sparse/16/metadata0/D2_provenance_compaction | 3 | 0.687 | 0.688 | 0.688 |
| sparse/16/metadata0/C1_full_frame_wire_validation | 3 | 1.240 | 1.243 | 1.243 |
| sparse/16/metadata0/C4_projection | 3 | 0.627 | 0.631 | 0.631 |
| sparse/16/metadata0/C1_service_ingest | 3 | 2.148 | 2.186 | 2.186 |
| sparse/16/metadata0/C1_snapshot_and_contract_serialization | 3 | 1.822 | 1.840 | 1.840 |
| sparse/16/metadata0/C1_canonical_response_encoding | 3 | 0.134 | 0.140 | 0.140 |
| sparse/16/metadata0/D3_assess_full_retained_geometry | 3 | 4.158 | 4.167 | 4.167 |
| sparse/16/metadata4096/C4_PointCloud2_decode | 3 | 0.021 | 0.022 | 0.022 |
| sparse/16/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 2.624 | 2.651 | 2.651 |
| sparse/16/metadata4096/D2_provenance_compaction | 3 | 0.703 | 0.705 | 0.705 |
| sparse/16/metadata4096/C1_full_frame_wire_validation | 3 | 1.271 | 1.280 | 1.280 |
| sparse/16/metadata4096/C4_projection | 3 | 0.651 | 0.654 | 0.654 |
| sparse/16/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.061 | 0.063 | 0.063 |
| sparse/16/metadata4096/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| sparse/16/metadata4096/D3_assess_full_retained_geometry | 3 | 4.271 | 4.450 | 4.450 |
| sparse/32/metadata0/C4_PointCloud2_decode | 3 | 0.037 | 0.040 | 0.040 |
| sparse/32/metadata0/D2_C4CorePort_process_including_compaction | 3 | 3.619 | 3.722 | 3.722 |
| sparse/32/metadata0/D2_provenance_compaction | 3 | 1.376 | 1.419 | 1.419 |
| sparse/32/metadata0/C1_full_frame_wire_validation | 3 | 2.611 | 2.628 | 2.628 |
| sparse/32/metadata0/C4_projection | 3 | 1.189 | 1.311 | 1.311 |
| sparse/32/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.068 | 0.077 | 0.077 |
| sparse/32/metadata0/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| sparse/32/metadata0/D3_assess_full_retained_geometry | 3 | 8.205 | 8.289 | 8.289 |
| sparse/32/metadata4096/C4_PointCloud2_decode | 3 | 0.035 | 0.038 | 0.038 |
| sparse/32/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 3.536 | 3.543 | 3.543 |
| sparse/32/metadata4096/D2_provenance_compaction | 3 | 1.326 | 1.330 | 1.330 |
| sparse/32/metadata4096/C1_full_frame_wire_validation | 3 | 2.528 | 2.534 | 2.534 |
| sparse/32/metadata4096/C4_projection | 3 | 1.216 | 1.303 | 1.303 |
| sparse/32/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.064 | 0.066 | 0.066 |
| sparse/32/metadata4096/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| sparse/32/metadata4096/D3_assess_full_retained_geometry | 3 | 8.143 | 8.246 | 8.246 |
| cone/0/metadata0/C4_PointCloud2_decode | 3 | 0.843 | 0.847 | 0.847 |
| cone/0/metadata0/D2_C4CorePort_process_including_compaction | 3 | 0.454 | 0.467 | 0.467 |
| cone/0/metadata0/D2_provenance_compaction | 3 | 0.070 | 0.071 | 0.071 |
| cone/0/metadata0/C1_full_frame_wire_validation | 3 | 0.095 | 0.096 | 0.096 |
| cone/0/metadata0/C4_projection | 3 | 0.075 | 0.075 | 0.075 |
| cone/0/metadata0/C1_service_ingest | 3 | 0.268 | 0.279 | 0.279 |
| cone/0/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.287 | 0.296 | 0.296 |
| cone/0/metadata0/C1_canonical_response_encoding | 3 | 0.027 | 0.028 | 0.028 |
| cone/0/metadata0/D3_assess_full_retained_geometry | 3 | 0.289 | 0.291 | 0.291 |
| cone/0/metadata4096/C4_PointCloud2_decode | 3 | 0.858 | 0.865 | 0.865 |
| cone/0/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 0.458 | 0.473 | 0.473 |
| cone/0/metadata4096/D2_provenance_compaction | 3 | 0.079 | 0.080 | 0.080 |
| cone/0/metadata4096/C1_full_frame_wire_validation | 3 | 0.112 | 0.115 | 0.115 |
| cone/0/metadata4096/C4_projection | 3 | 0.088 | 0.103 | 0.103 |
| cone/0/metadata4096/C1_service_ingest | 3 | 0.355 | 0.370 | 0.370 |
| cone/0/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.355 | 0.369 | 0.369 |
| cone/0/metadata4096/C1_canonical_response_encoding | 3 | 0.045 | 0.047 | 0.047 |
| cone/0/metadata4096/D3_assess_full_retained_geometry | 3 | 0.294 | 0.299 | 0.299 |
| cone/1/metadata0/C4_PointCloud2_decode | 3 | 1.001 | 1.010 | 1.010 |
| cone/1/metadata0/D2_C4CorePort_process_including_compaction | 3 | 1.233 | 1.264 | 1.264 |
| cone/1/metadata0/D2_provenance_compaction | 3 | 0.120 | 0.127 | 0.127 |
| cone/1/metadata0/C1_full_frame_wire_validation | 3 | 0.181 | 0.194 | 0.194 |
| cone/1/metadata0/C4_projection | 3 | 0.121 | 0.122 | 0.122 |
| cone/1/metadata0/C1_service_ingest | 3 | 0.412 | 0.423 | 0.423 |
| cone/1/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.407 | 0.409 | 0.409 |
| cone/1/metadata0/C1_canonical_response_encoding | 3 | 0.036 | 0.038 | 0.038 |
| cone/1/metadata0/D3_assess_full_retained_geometry | 3 | 0.587 | 0.605 | 0.605 |
| cone/1/metadata4096/C4_PointCloud2_decode | 3 | 1.033 | 1.142 | 1.142 |
| cone/1/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 1.215 | 1.447 | 1.447 |
| cone/1/metadata4096/D2_provenance_compaction | 3 | 0.127 | 0.146 | 0.146 |
| cone/1/metadata4096/C1_full_frame_wire_validation | 3 | 0.202 | 0.225 | 0.225 |
| cone/1/metadata4096/C4_projection | 3 | 0.128 | 0.130 | 0.130 |
| cone/1/metadata4096/C1_service_ingest | 3 | 0.482 | 0.492 | 0.492 |
| cone/1/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.478 | 0.478 | 0.478 |
| cone/1/metadata4096/C1_canonical_response_encoding | 3 | 0.055 | 0.056 | 0.056 |
| cone/1/metadata4096/D3_assess_full_retained_geometry | 3 | 0.576 | 0.603 | 0.603 |
| cone/4/metadata0/C4_PointCloud2_decode | 3 | 1.483 | 1.499 | 1.499 |
| cone/4/metadata0/D2_C4CorePort_process_including_compaction | 3 | 2.555 | 2.583 | 2.583 |
| cone/4/metadata0/D2_provenance_compaction | 3 | 0.244 | 0.244 | 0.244 |
| cone/4/metadata0/C1_full_frame_wire_validation | 3 | 0.415 | 0.431 | 0.431 |
| cone/4/metadata0/C4_projection | 3 | 0.230 | 0.235 | 0.235 |
| cone/4/metadata0/C1_service_ingest | 3 | 0.809 | 0.842 | 0.842 |
| cone/4/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.745 | 0.748 | 0.748 |
| cone/4/metadata0/C1_canonical_response_encoding | 3 | 0.064 | 0.066 | 0.066 |
| cone/4/metadata0/D3_assess_full_retained_geometry | 3 | 1.361 | 1.404 | 1.404 |
| cone/4/metadata4096/C4_PointCloud2_decode | 3 | 1.518 | 1.519 | 1.519 |
| cone/4/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 2.648 | 2.708 | 2.708 |
| cone/4/metadata4096/D2_provenance_compaction | 3 | 0.258 | 0.263 | 0.263 |
| cone/4/metadata4096/C1_full_frame_wire_validation | 3 | 0.440 | 0.516 | 0.516 |
| cone/4/metadata4096/C4_projection | 3 | 0.256 | 0.257 | 0.257 |
| cone/4/metadata4096/C1_service_ingest | 3 | 0.893 | 0.896 | 0.896 |
| cone/4/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.807 | 0.807 | 0.807 |
| cone/4/metadata4096/C1_canonical_response_encoding | 3 | 0.084 | 0.087 | 0.087 |
| cone/4/metadata4096/D3_assess_full_retained_geometry | 3 | 1.373 | 1.395 | 1.395 |
| cone/12/metadata0/C4_PointCloud2_decode | 3 | 2.781 | 2.800 | 2.800 |
| cone/12/metadata0/D2_C4CorePort_process_including_compaction | 3 | 6.147 | 6.296 | 6.296 |
| cone/12/metadata0/D2_provenance_compaction | 3 | 0.580 | 0.585 | 0.585 |
| cone/12/metadata0/C1_full_frame_wire_validation | 3 | 1.092 | 1.146 | 1.146 |
| cone/12/metadata0/C4_projection | 3 | 0.535 | 0.596 | 0.596 |
| cone/12/metadata0/C1_service_ingest | 3 | 1.992 | 2.046 | 2.046 |
| cone/12/metadata0/C1_snapshot_and_contract_serialization | 3 | 1.594 | 1.619 | 1.619 |
| cone/12/metadata0/C1_canonical_response_encoding | 3 | 0.138 | 0.140 | 0.140 |
| cone/12/metadata0/D3_assess_full_retained_geometry | 3 | 3.333 | 3.529 | 3.529 |
| cone/12/metadata4096/C4_PointCloud2_decode | 3 | 2.742 | 2.768 | 2.768 |
| cone/12/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 6.343 | 6.614 | 6.614 |
| cone/12/metadata4096/D2_provenance_compaction | 3 | 0.604 | 0.610 | 0.610 |
| cone/12/metadata4096/C1_full_frame_wire_validation | 3 | 1.081 | 1.081 | 1.081 |
| cone/12/metadata4096/C4_projection | 3 | 0.574 | 0.583 | 0.583 |
| cone/12/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.066 | 0.074 | 0.074 |
| cone/12/metadata4096/C1_canonical_response_encoding | 3 | 0.010 | 0.011 | 0.011 |
| cone/12/metadata4096/D3_assess_full_retained_geometry | 3 | 3.309 | 3.423 | 3.423 |
| cone/16/metadata0/C4_PointCloud2_decode | 3 | 3.440 | 3.466 | 3.466 |
| cone/16/metadata0/D2_C4CorePort_process_including_compaction | 3 | 7.186 | 7.234 | 7.234 |
| cone/16/metadata0/D2_provenance_compaction | 3 | 0.728 | 0.781 | 0.781 |
| cone/16/metadata0/C1_full_frame_wire_validation | 3 | 1.339 | 1.512 | 1.512 |
| cone/16/metadata0/C4_projection | 3 | 0.690 | 0.761 | 0.761 |
| cone/16/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.059 | 0.069 | 0.069 |
| cone/16/metadata0/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| cone/16/metadata0/D3_assess_full_retained_geometry | 3 | 4.275 | 4.657 | 4.657 |
| cone/16/metadata4096/C4_PointCloud2_decode | 3 | 3.289 | 3.340 | 3.340 |
| cone/16/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 6.807 | 6.875 | 6.875 |
| cone/16/metadata4096/D2_provenance_compaction | 3 | 0.741 | 0.750 | 0.750 |
| cone/16/metadata4096/C1_full_frame_wire_validation | 3 | 1.351 | 1.363 | 1.363 |
| cone/16/metadata4096/C4_projection | 3 | 0.675 | 0.680 | 0.680 |
| cone/16/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.058 | 0.059 | 0.059 |
| cone/16/metadata4096/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| cone/16/metadata4096/D3_assess_full_retained_geometry | 3 | 4.238 | 4.267 | 4.267 |
| cone/32/metadata0/C4_PointCloud2_decode | 3 | 5.806 | 6.026 | 6.026 |
| cone/32/metadata0/D2_C4CorePort_process_including_compaction | 3 | 13.120 | 13.383 | 13.383 |
| cone/32/metadata0/D2_provenance_compaction | 3 | 1.414 | 1.485 | 1.485 |
| cone/32/metadata0/C1_full_frame_wire_validation | 3 | 2.758 | 2.758 | 2.758 |
| cone/32/metadata0/C4_projection | 3 | 1.266 | 1.266 | 1.266 |
| cone/32/metadata0/C1_snapshot_and_contract_serialization | 3 | 0.064 | 0.066 | 0.066 |
| cone/32/metadata0/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| cone/32/metadata0/D3_assess_full_retained_geometry | 3 | 8.155 | 8.309 | 8.309 |
| cone/32/metadata4096/C4_PointCloud2_decode | 3 | 5.915 | 6.106 | 6.106 |
| cone/32/metadata4096/D2_C4CorePort_process_including_compaction | 3 | 13.716 | 13.825 | 13.825 |
| cone/32/metadata4096/D2_provenance_compaction | 3 | 1.451 | 1.593 | 1.593 |
| cone/32/metadata4096/C1_full_frame_wire_validation | 3 | 2.732 | 2.748 | 2.748 |
| cone/32/metadata4096/C4_projection | 3 | 1.280 | 1.339 | 1.339 |
| cone/32/metadata4096/C1_snapshot_and_contract_serialization | 3 | 0.066 | 0.066 | 0.066 |
| cone/32/metadata4096/C1_canonical_response_encoding | 3 | 0.010 | 0.010 | 0.010 |
| cone/32/metadata4096/D3_assess_full_retained_geometry | 3 | 8.233 | 8.338 | 8.338 |
| cone/14/metadata0_boundary/C4_PointCloud2_decode | 1 | 3.104 | 3.104 | 3.104 |
| cone/14/metadata0_boundary/D2_C4CorePort_process_including_compaction | 1 | 7.071 | 7.071 | 7.071 |
| cone/14/metadata0_boundary/D2_provenance_compaction | 1 | 0.657 | 0.657 | 0.657 |
| cone/14/metadata0_boundary/C1_full_frame_wire_validation | 1 | 1.186 | 1.186 | 1.186 |
| cone/14/metadata0_boundary/C4_projection | 1 | 0.606 | 0.606 | 0.606 |
| cone/14/metadata0_boundary/C1_service_ingest | 1 | 2.133 | 2.133 | 2.133 |
| cone/14/metadata0_boundary/C1_snapshot_and_contract_serialization | 1 | 1.888 | 1.888 | 1.888 |
| cone/14/metadata0_boundary/C1_canonical_response_encoding | 1 | 0.152 | 0.152 | 0.152 |
| cone/14/metadata0_boundary/D3_assess_full_retained_geometry | 1 | 3.952 | 3.952 | 3.952 |
| cone/15/metadata0_boundary/C4_PointCloud2_decode | 1 | 3.553 | 3.553 | 3.553 |
| cone/15/metadata0_boundary/D2_C4CorePort_process_including_compaction | 1 | 7.619 | 7.619 | 7.619 |
| cone/15/metadata0_boundary/D2_provenance_compaction | 1 | 0.716 | 0.716 | 0.716 |
| cone/15/metadata0_boundary/C1_full_frame_wire_validation | 1 | 1.279 | 1.279 | 1.279 |
| cone/15/metadata0_boundary/C4_projection | 1 | 0.644 | 0.644 | 0.644 |
| cone/15/metadata0_boundary/C1_service_ingest | 1 | 2.406 | 2.406 | 2.406 |
| cone/15/metadata0_boundary/C1_snapshot_and_contract_serialization | 1 | 2.090 | 2.090 | 2.090 |
| cone/15/metadata0_boundary/C1_canonical_response_encoding | 1 | 0.170 | 0.170 | 0.170 |
| cone/15/metadata0_boundary/D3_assess_full_retained_geometry | 1 | 4.081 | 4.081 | 4.081 |
| current_C4_D2_D3_C1/C4_port_perceive | 3 | 0.470 | 0.485 | 0.485 |
| current_C4_D2_D3_C1/C4_port_assess | 3 | 1.967 | 2.038 | 2.038 |
| current_C4_D2_D3_C1/C4_port_canonical_assessment | 3 | 0.677 | 0.704 | 0.704 |
| current_C4_D2_D3_C1/C4_Runtime_process | 3 | 3.455 | 3.577 | 3.577 |
| current_C4_D2_D3_C1/C4_compact_and_C1_ingest_scene | 3 | 2.267 | 2.411 | 2.411 |
| current_C4_D2_D3_C1/C1_ASGI_HTTP_response_including_fixture_setup | 3 | 7.906 | 7.959 | 7.959 |
| map/400_per_source/D1_solve_contract_small_only | 1 | 11.485 | 11.485 | 11.485 |
| map/400_per_source/source_list | 3 | 0.415 | 0.425 | 0.425 |
| map/400_per_source/source_preview_160 | 3 | 0.514 | 0.522 | 0.522 |
| map/400_per_source/full_export | 1 | 4.380 | 4.380 | 4.380 |
| map/400_per_source/bundle_list | 3 | 0.798 | 0.813 | 0.813 |
| map/20000_per_source/source_list | 3 | 0.870 | 0.872 | 0.872 |
| map/20000_per_source/source_preview_160 | 3 | 0.740 | 0.752 | 0.752 |
| map/20000_per_source/full_export | 1 | 21.757 | 21.757 | 21.757 |
| map/20000_per_source/bundle_list | 3 | 0.991 | 1.003 | 1.003 |
| map/200000_per_source/source_list | 3 | 5.771 | 5.955 | 5.955 |
| map/200000_per_source/source_preview_160 | 3 | 3.136 | 3.151 | 3.151 |
| map/200000_per_source/full_export | 1 | 195.355 | 195.355 | 195.355 |
| map/200000_per_source/bundle_list | 3 | 6.527 | 6.623 | 6.623 |

## first observed rejections

```json
[
  {
    "family": "sparse",
    "metadata_bytes": 0,
    "first_observed_objects": 32,
    "reason": "FRAME_BUDGET_EXCEEDED:22419+2048>16384",
    "scope": "FIRST_SAMPLED_FAILURE; only cone metadata0 has adjacent 15/16 check"
  },
  {
    "family": "sparse",
    "metadata_bytes": 4096,
    "first_observed_objects": 16,
    "reason": "FRAME_BUDGET_EXCEEDED:16277+2048>16384",
    "scope": "FIRST_SAMPLED_FAILURE; only cone metadata0 has adjacent 15/16 check"
  },
  {
    "family": "cone",
    "metadata_bytes": 0,
    "first_observed_objects": 16,
    "reason": "FRAME_BUDGET_EXCEEDED:14763+2048>16384",
    "scope": "FIRST_SAMPLED_FAILURE; only cone metadata0 has adjacent 15/16 check"
  },
  {
    "family": "cone",
    "metadata_bytes": 4096,
    "first_observed_objects": 12,
    "reason": "FRAME_BUDGET_EXCEEDED:15680+2048>16384",
    "scope": "FIRST_SAMPLED_FAILURE; only cone metadata0 has adjacent 15/16 check"
  }
]
```

## exact sample boundary

```json
[
  {
    "bytes": 16383,
    "wire": {
      "status": "ACCEPTED",
      "reason": null
    },
    "ingest": {
      "status": "ACCEPTED",
      "reason": null
    },
    "objects": 1
  },
  {
    "bytes": 16384,
    "wire": {
      "status": "ACCEPTED",
      "reason": null
    },
    "ingest": {
      "status": "ACCEPTED",
      "reason": null
    },
    "objects": 1
  },
  {
    "bytes": 16385,
    "wire": {
      "status": "ACCEPTED",
      "reason": null
    },
    "ingest": {
      "status": "REJECTED",
      "reason": "document exceeds byte limit",
      "exception": "ContractError"
    },
    "objects": 1
  }
]
```

## exact compactor boundary

```json
[
  {
    "compact_bytes": 14335,
    "reserve_bytes": 2048,
    "total_bytes": 16383,
    "result": {
      "status": "ACCEPTED",
      "reason": null
    }
  },
  {
    "compact_bytes": 14336,
    "reserve_bytes": 2048,
    "total_bytes": 16384,
    "result": {
      "status": "ACCEPTED",
      "reason": null
    }
  },
  {
    "compact_bytes": 14337,
    "reserve_bytes": 2048,
    "total_bytes": 16385,
    "result": {
      "status": "REJECTED",
      "reason": "FRAME_BUDGET_EXCEEDED:14337+2048>16384",
      "exception": "ValueError"
    }
  }
]
```

## exact wire boundary

```json
[
  {
    "bytes": 131071,
    "wire": {
      "status": "ACCEPTED",
      "reason": null
    }
  },
  {
    "bytes": 131072,
    "wire": {
      "status": "ACCEPTED",
      "reason": null
    }
  },
  {
    "bytes": 131073,
    "wire": {
      "status": "REJECTED",
      "reason": "document exceeds byte limit",
      "exception": "ContractError"
    }
  }
]
```

## aggregate and assets

```json
{
  "latest_slots": [
    {
      "slot": "robot_pose",
      "bytes": 16384,
      "ingest": {
        "status": "ACCEPTED",
        "reason": null
      },
      "metrics": {
        "history_size": 1,
        "history_limit": 16,
        "latest_size": 1,
        "dropped": 0,
        "persistent_ledger_writes": 0
      }
    },
    {
      "slot": "global_path",
      "bytes": 16384,
      "ingest": {
        "status": "ACCEPTED",
        "reason": null
      },
      "metrics": {
        "history_size": 2,
        "history_limit": 16,
        "latest_size": 2,
        "dropped": 0,
        "persistent_ledger_writes": 0
      }
    },
    {
      "slot": "controller_local_trajectory",
      "bytes": 16384,
      "ingest": {
        "status": "ACCEPTED",
        "reason": null
      },
      "metrics": {
        "history_size": 3,
        "history_limit": 16,
        "latest_size": 3,
        "dropped": 0,
        "persistent_ledger_writes": 0
      }
    },
    {
      "slot": "costmap_snapshot",
      "bytes": 16384,
      "ingest": {
        "status": "ACCEPTED",
        "reason": null
      },
      "metrics": {
        "history_size": 4,
        "history_limit": 16,
        "latest_size": 4,
        "dropped": 0,
        "persistent_ledger_writes": 0
      }
    },
    {
      "slot": "obstacle_frame",
      "bytes": 16384,
      "ingest": {
        "status": "ACCEPTED",
        "reason": null
      },
      "metrics": {
        "history_size": 5,
        "history_limit": 16,
        "latest_size": 5,
        "dropped": 0,
        "persistent_ledger_writes": 0
      }
    },
    {
      "slot": "collision_assessment",
      "bytes": 16384,
      "ingest": {
        "status": "REJECTED",
        "reason": null
      },
      "metrics": {
        "history_size": 5,
        "history_limit": 16,
        "latest_size": 5,
        "dropped": 1,
        "persistent_ledger_writes": 0
      }
    }
  ],
  "per_asset": [
    {
      "bytes": 2097151,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      }
    },
    {
      "bytes": 2097152,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      }
    },
    {
      "bytes": 2097153,
      "result": {
        "status": "REJECTED",
        "reason": "scene asset byte limit",
        "exception": "ContractError"
      }
    }
  ],
  "asset_total": [
    {
      "added_bytes": 2097152,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      },
      "retained_bytes": 2097152,
      "items": 1
    },
    {
      "added_bytes": 2097152,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      },
      "retained_bytes": 4194304,
      "items": 2
    },
    {
      "added_bytes": 2097152,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      },
      "retained_bytes": 6291456,
      "items": 3
    },
    {
      "added_bytes": 2097152,
      "result": {
        "status": "ACCEPTED",
        "reason": null
      },
      "retained_bytes": 8388608,
      "items": 4
    },
    {
      "added_bytes": 1,
      "result": {
        "status": "REJECTED",
        "reason": "scene asset store bound",
        "exception": "ContractError"
      },
      "retained_bytes": 8388608,
      "items": 4
    }
  ],
  "asset_count": [
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "ACCEPTED",
      "reason": null
    },
    {
      "status": "REJECTED",
      "reason": "scene asset store bound",
      "exception": "ContractError"
    }
  ],
  "after_clear_items": 0,
  "classification": "SYNTHETIC_METADATA_FILL; ACTUAL_C1_LIMITS; no collision geometry removed"
}
```

## counts

```json
{
  "case_inputs_including_warmup": 99,
  "measured_case_inputs": 75,
  "core_processing_attempts": 99,
  "table_cases": 26,
  "table_delivered": 18,
  "table_not_sent": 8,
  "note": "Table counts are one retained result per case; repetitions include one excluded warm-up. Queue/C4 composition counters separate."
}
```

## fences

```json
{
  "sink_false_probe": {
    "returned": null,
    "dropped": 1,
    "latest_sequence": 1,
    "condition": "same source epoch/sequence rejected by actual C1; sink does not propagate False"
  },
  "repeated_size_rejects": [
    {
      "status": "REJECTED",
      "reason": "document exceeds byte limit",
      "exception": "ContractError"
    },
    {
      "status": "REJECTED",
      "reason": "document exceeds byte limit",
      "exception": "ContractError"
    },
    {
      "status": "REJECTED",
      "reason": "document exceeds byte limit",
      "exception": "ContractError"
    }
  ],
  "initial_status": "ready",
  "retained_sequence_before_expiry": 1,
  "receipt_unchanged": true,
  "expired_status": "expired",
  "expired_value": null,
  "map_rejected": true,
  "map_cleared": true,
  "clock_status": "unavailable",
  "clock_age_ms": null,
  "history_max": 16,
  "history_limit": 16,
  "replacements": 40,
  "service_dropped_counter": 1,
  "note": "Size exceptions occur before service.dropped increments; diagnostic rejection count is independent."
}
```

## queue

```json
{
  "evidence_kind": "ACTUAL_C4_WORKER_AND_D2_CORE_WITH_EXPLICIT_DELAY_GATE",
  "input": 60,
  "accepted_at_ingress": 60,
  "processed": 2,
  "replaced_pending": 58,
  "invalid": 0,
  "rejected": 0,
  "stale_or_superseded_results": 1,
  "latest_replacements": 1,
  "pending_max": 1,
  "executing_limit": 1,
  "pending_limit": 1,
  "displayed_sequence": 60,
  "timings": [
    {
      "sequence": 1,
      "injected_wait_ms": 0.501292,
      "real_core_ms": 1.319958
    },
    {
      "sequence": 60,
      "injected_wait_ms": 0.003625,
      "real_core_ms": 1.351
    }
  ],
  "latest_health": {
    "sources": {
      "lidar": {
        "age_ns": 5482000,
        "stale": false,
        "source_stamp_ns": "1000000059",
        "fusion_time": "SOURCE_CLOCK_ONLY"
      }
    },
    "rejected": 0,
    "late_results": 1,
    "dropped": 58,
    "invalid": 0,
    "latency": {
      "queue_ms": 1.7071659676730633,
      "processing_ms": 2.6451670564711094,
      "receipt_to_done_ms": 4.358000040054321
    },
    "worker_error": null,
    "queue_capacity": 1,
    "executing_capacity": 1
  },
  "history": {
    "history_size": 1,
    "history_limit": 16,
    "latest_size": 1,
    "dropped": 0,
    "persistent_ledger_writes": 0
  },
  "end_to_end_latency": "UNKNOWN_SOURCE_CLOCK_MAPPING",
  "accounting": "60 ingress = 58 pending replacements + 2 processed; first result superseded, one service replacement",
  "queue_after_close": 0,
  "latest_after_close": null
}
```

## composition

```json
{
  "status": "PASS",
  "actual_http": "ASGI_IN_PROCESS_NO_TCP",
  "input": "C4 existing latest_fixtures; actual numerical cores; explicit generated clock mapping",
  "results": [
    {
      "bytes": 10550,
      "sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "canonical_sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "severity": "UNKNOWN",
      "reason": "UNKNOWN",
      "fixture_timing": {
        "c4_received_monotonic_ns": 1010000000,
        "observation_stamp_ns": "1000000000",
        "observation_received_monotonic_ns": 1001000000,
        "source_clock_domain": "fixture-clock",
        "d2_started_monotonic_ns": 1010000000,
        "d2_finished_monotonic_ns": 1010000000,
        "d3_started_monotonic_ns": 1010000000,
        "d3_finished_monotonic_ns": 1010000000,
        "c4_converted_monotonic_ns": 1010000000
      },
      "fixture_timing_is_benchmark": false
    },
    {
      "bytes": 10550,
      "sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "canonical_sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "severity": "UNKNOWN",
      "reason": "UNKNOWN",
      "fixture_timing": {
        "c4_received_monotonic_ns": 1010000000,
        "observation_stamp_ns": "1000000000",
        "observation_received_monotonic_ns": 1001000000,
        "source_clock_domain": "fixture-clock",
        "d2_started_monotonic_ns": 1010000000,
        "d2_finished_monotonic_ns": 1010000000,
        "d3_started_monotonic_ns": 1010000000,
        "d3_finished_monotonic_ns": 1010000000,
        "c4_converted_monotonic_ns": 1010000000
      },
      "fixture_timing_is_benchmark": false
    },
    {
      "bytes": 10550,
      "sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "canonical_sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "severity": "UNKNOWN",
      "reason": "UNKNOWN",
      "fixture_timing": {
        "c4_received_monotonic_ns": 1010000000,
        "observation_stamp_ns": "1000000000",
        "observation_received_monotonic_ns": 1001000000,
        "source_clock_domain": "fixture-clock",
        "d2_started_monotonic_ns": 1010000000,
        "d2_finished_monotonic_ns": 1010000000,
        "d3_started_monotonic_ns": 1010000000,
        "d3_finished_monotonic_ns": 1010000000,
        "c4_converted_monotonic_ns": 1010000000
      },
      "fixture_timing_is_benchmark": false
    },
    {
      "bytes": 10550,
      "sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "canonical_sha256": "50c352c2c50b8ef835217e717b64c99cec465a5cee997b4398661aba8abc2e8c",
      "severity": "UNKNOWN",
      "reason": "UNKNOWN",
      "fixture_timing": {
        "c4_received_monotonic_ns": 1010000000,
        "observation_stamp_ns": "1000000000",
        "observation_received_monotonic_ns": 1001000000,
        "source_clock_domain": "fixture-clock",
        "d2_started_monotonic_ns": 1010000000,
        "d2_finished_monotonic_ns": 1010000000,
        "d3_started_monotonic_ns": 1010000000,
        "d3_finished_monotonic_ns": 1010000000,
        "c4_converted_monotonic_ns": 1010000000
      },
      "fixture_timing_is_benchmark": false
    }
  ],
  "c3": {
    "status": "PASS",
    "reason": "",
    "obstacleCount": 1,
    "collisionAvailable": false,
    "collisionReason": "POSE_JOINT_OR_SOURCE_INSUFFICIENT",
    "availability": {
      "reference_cloud": "UNAVAILABLE",
      "sensor_clouds": "UNAVAILABLE",
      "sensor_origins": "UNAVAILABLE",
      "bulk_references": "C1_AUTHENTICATED_ASSETS",
      "asset_count": 0,
      "source_status": {
        "collision_assessment": "ready",
        "controller_local_trajectory": "unavailable",
        "costmap_snapshot": "unavailable",
        "global_path": "unavailable",
        "obstacle_frame": "ready",
        "robot_pose": "unavailable"
      },
      "collision": {
        "c4": {
          "clock_epoch": "clock-1",
          "intent_status": {
            "authority_present": true,
            "product_enforcement_connected": false,
            "reason": "UNKNOWN",
            "severity": "UNKNOWN"
          },
          "mapping_window_ns": [
            "0",
            "1000000000000"
          ],
          "original_assessment_sequence": 1,
          "original_validity_interval": {
            "clock_domain": "fixture-clock",
            "from_ns": "1000000000",
            "until_ns": "1250000000"
          },
          "product_enforcement_connected": false,
          "source_profile": "d3-356d0a036eb62d546e159e12a0691d7f5ea278f6/0.2",
          "timing": {
            "c4_converted_monotonic_ns": "1010000000",
            "c4_received_monotonic_ns": "1010000000",
            "d2_finished_monotonic_ns": "1010000000",
            "d2_started_monotonic_ns": "1010000000",
            "d3_finished_monotonic_ns": "1010000000",
            "d3_started_monotonic_ns": "1010000000",
            "observation_received_monotonic_ns": "1001000000",
            "observation_stamp_ns": "1000000000",
            "source_clock_domain": "fixture-clock"
          }
        },
        "c4_binding": {
          "authority_generation": 1,
          "clock_epoch": "clock-1",
          "command_scope": "bounded-body-twist",
          "controller_goal_id": "goal-1",
          "family_id": "synthetic-family",
          "family_revision": "family-r1",
          "footprint_revision": "footprint-r1",
          "frame_id": "odom",
          "host_clock_id": "fixture-host",
          "lease_id": "lease-1",
          "map_generation": 0,
          "map_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
          "map_revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "robot_geometry_hash": "cdd3320e7241cb43e0b74d874143d7da5bfa64117140e631074cf423d8250828",
          "runtime_generation": 1,
          "source_epoch": "synthetic-1",
          "tf_epoch": "tf-1"
        },
        "coverage": {
          "complete_for_motion": false,
          "evidence": null,
          "horizon_s": 0.1,
          "status": "MOTION_COVERAGE_NOT_QUALIFIED",
          "swept_volume_max": [
            0.4834879566956773,
            0.4734879566956773,
            0.7734879566956773
          ],
          "swept_volume_min": [
            -0.4734879566956773,
            -0.4734879566956773,
            -0.1734879566956773
          ]
        },
        "issues": [
          "MOTION_COVERAGE_NOT_QUALIFIED"
        ],
        "joint_age_s": 0.01,
        "obstacle_age_s": 0.01,
        "pose_age_s": 0.01,
        "protection_mode": "ADVISORY_ONLY",
        "source_validity_interval": {
          "clock_domain": "fixture-clock",
          "from_ns": "1000000000",
          "until_ns": "1250000000"
        },
        "time_conversion": {
          "binding_id": "SYNTHETIC_SHARED_CLOCK",
          "offset_ns": "0",
          "original_interval": {
            "clock_domain": "fixture-clock",
            "from_ns": "1000000000",
            "until_ns": "1250000000"
          },
          "source_epoch": "synthetic-1",
          "uncertainty_ns": "0"
        }
      },
      "errors": []
    },
    "diagnostics": {
      "accepted": 1,
      "rejected": 0,
      "resets": 1,
      "history": 0,
      "retainedPackets": 1,
      "lastSequence": 2,
      "error": "",
      "geometryCopies": 2,
      "cachedLayers": 2
    },
    "timings": [
      {
        "warmup": true,
        "clock": "Node performance.now",
        "parse_ms": 0.5689579999999985,
        "adapt_ms": 0.5143750000000011,
        "consume_ms": 1.4823330000000006
      },
      {
        "warmup": false,
        "clock": "Node performance.now",
        "parse_ms": 0.654874999999997,
        "adapt_ms": 0.16404200000000202,
        "consume_ms": 0.12062500000000043
      },
      {
        "warmup": false,
        "clock": "Node performance.now",
        "parse_ms": 0.40954200000000185,
        "adapt_ms": 0.052042000000000144,
        "consume_ms": 0.14116599999999835
      },
      {
        "warmup": false,
        "clock": "Node performance.now",
        "parse_ms": 0.5658329999999978,
        "adapt_ms": 0.11791700000000205,
        "consume_ms": 0.071708000000001
      }
    ],
    "render": "NOT_RUN_NODE_CONSUMER_ONLY",
    "timing_summary": {
      "parse_ms": {
        "n": 3,
        "p50_ms": 0.5658329999999978,
        "p95_ms": 0.654874999999997,
        "max_ms": 0.654874999999997
      },
      "adapt_ms": {
        "n": 3,
        "p50_ms": 0.11791700000000205,
        "p95_ms": 0.16404200000000202,
        "max_ms": 0.16404200000000202
      },
      "consume_ms": {
        "n": 3,
        "p50_ms": 0.12062500000000043,
        "p95_ms": 0.14116599999999835,
        "max_ms": 0.14116599999999835
      }
    }
  },
  "product_enforcement": false,
  "end_to_end_latency": "UNKNOWN; Python and JS clocks have no mapping",
  "full_render": "NOT_RUN_FOR_THIS_COMMAND_ASSESSMENT; absent pose/joints/path must stay unavailable"
}
```

## maps

```json
[
  {
    "points_per_source": 400,
    "source_bytes": 22770,
    "input_hashes": [
      "5a501d26741196765823c05d816df8d1ab171dd9bdf10e9f6abc7da99b1e8a8f",
      "6d8385d3772a00e58e1b13335c782a9e1e4caeb13e55cdb9d1d28bc17a5a2869"
    ],
    "measurements": [
      {
        "operation": "source_list",
        "warmup": true,
        "read_bytes": 22770,
        "opens": 2,
        "returned_bytes": 1691,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 22770,
        "opens": 2,
        "returned_bytes": 1691,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 22770,
        "opens": 2,
        "returned_bytes": 1691,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 22770,
        "opens": 2,
        "returned_bytes": 1691,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": true,
        "read_bytes": 11385,
        "opens": 1,
        "returned_bytes": 9697,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 11385,
        "opens": 1,
        "returned_bytes": 9697,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 11385,
        "opens": 1,
        "returned_bytes": 9697,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 11385,
        "opens": 1,
        "returned_bytes": 9697,
        "output_points": null
      },
      {
        "operation": "full_export",
        "warmup": false,
        "read_bytes": 91850,
        "opens": 11,
        "returned_bytes": 16328,
        "output_points": 800
      },
      {
        "operation": "bundle_list",
        "warmup": true,
        "read_bytes": 39498,
        "opens": 4,
        "returned_bytes": 183,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 39498,
        "opens": 4,
        "returned_bytes": 183,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 39498,
        "opens": 4,
        "returned_bytes": 183,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 39498,
        "opens": 4,
        "returned_bytes": 183,
        "output_points": null
      }
    ],
    "solver": "ACTUAL_D1",
    "limits": {
      "max_source_bytes": 268435456,
      "max_export_bytes": 268435456,
      "chunk_points": 16384,
      "max_points": 20000000
    },
    "IO": "ACTUAL_LOGICAL_READ_BYTES; OS disk cache state uncontrolled; generator time excluded"
  },
  {
    "points_per_source": 20000,
    "source_bytes": 1120378,
    "input_hashes": [
      "caae5ee09ca428f540c8e55b660e4b2e3a8fd736a1003379fab5645ec7cba8c8",
      "14b2a4d3bf32dab38e7b77fa734ed79d1a716f7b9e092ac312aa34c1042de8a5"
    ],
    "measurements": [
      {
        "operation": "source_list",
        "warmup": true,
        "read_bytes": 1120378,
        "opens": 2,
        "returned_bytes": 1695,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 1120378,
        "opens": 2,
        "returned_bytes": 1695,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 1120378,
        "opens": 2,
        "returned_bytes": 1695,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 1120378,
        "opens": 2,
        "returned_bytes": 1695,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": true,
        "read_bytes": 560189,
        "opens": 1,
        "returned_bytes": 9705,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 560189,
        "opens": 1,
        "returned_bytes": 9705,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 560189,
        "opens": 1,
        "returned_bytes": 9705,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 560189,
        "opens": 1,
        "returned_bytes": 9705,
        "output_points": null
      },
      {
        "operation": "full_export",
        "warmup": false,
        "read_bytes": 4482346,
        "opens": 11,
        "returned_bytes": 5828,
        "output_points": 40000
      },
      {
        "operation": "bundle_list",
        "warmup": true,
        "read_bytes": 1126662,
        "opens": 4,
        "returned_bytes": 185,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 1126662,
        "opens": 4,
        "returned_bytes": 185,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 1126662,
        "opens": 4,
        "returned_bytes": 185,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 1126662,
        "opens": 4,
        "returned_bytes": 185,
        "output_points": null
      }
    ],
    "solver": "NOT_RUN_LARGE_MAP; GIVEN_GENERATOR_TRANSFORMS_EXPORT_ONLY",
    "limits": {
      "max_source_bytes": 268435456,
      "max_export_bytes": 268435456,
      "chunk_points": 16384,
      "max_points": 20000000
    },
    "IO": "ACTUAL_LOGICAL_READ_BYTES; OS disk cache state uncontrolled; generator time excluded"
  },
  {
    "points_per_source": 200000,
    "source_bytes": 11200382,
    "input_hashes": [
      "b8e870c3ec77d7754dde03911e0259b240af95082ac50fdaa47f76a6edaf28aa",
      "085041070c1fe04d19ac705dd40b326e5e58ce551ca6ed3b0a413cc6a4758ddc"
    ],
    "measurements": [
      {
        "operation": "source_list",
        "warmup": true,
        "read_bytes": 11200382,
        "opens": 2,
        "returned_bytes": 1697,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 11200382,
        "opens": 2,
        "returned_bytes": 1697,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 11200382,
        "opens": 2,
        "returned_bytes": 1697,
        "output_points": null
      },
      {
        "operation": "source_list",
        "warmup": false,
        "read_bytes": 11200382,
        "opens": 2,
        "returned_bytes": 1697,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": true,
        "read_bytes": 5600191,
        "opens": 1,
        "returned_bytes": 9696,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 5600191,
        "opens": 1,
        "returned_bytes": 9696,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 5600191,
        "opens": 1,
        "returned_bytes": 9696,
        "output_points": null
      },
      {
        "operation": "source_preview_160",
        "warmup": false,
        "read_bytes": 5600191,
        "opens": 1,
        "returned_bytes": 9696,
        "output_points": null
      },
      {
        "operation": "full_export",
        "warmup": false,
        "read_bytes": 44802390,
        "opens": 11,
        "returned_bytes": 5835,
        "output_points": 400000
      },
      {
        "operation": "bundle_list",
        "warmup": true,
        "read_bytes": 11206697,
        "opens": 4,
        "returned_bytes": 186,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 11206697,
        "opens": 4,
        "returned_bytes": 186,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 11206697,
        "opens": 4,
        "returned_bytes": 186,
        "output_points": null
      },
      {
        "operation": "bundle_list",
        "warmup": false,
        "read_bytes": 11206697,
        "opens": 4,
        "returned_bytes": 186,
        "output_points": null
      }
    ],
    "solver": "NOT_RUN_LARGE_MAP; GIVEN_GENERATOR_TRANSFORMS_EXPORT_ONLY",
    "limits": {
      "max_source_bytes": 268435456,
      "max_export_bytes": 268435456,
      "chunk_points": 16384,
      "max_points": 20000000
    },
    "IO": "ACTUAL_LOGICAL_READ_BYTES; OS disk cache state uncontrolled; generator time excluded"
  }
]
```

## c3 cache

```json
{
  "status": "PASS",
  "evidence_kind": "ACTUAL_C3_CACHE_WITH_MEMORY_TRANSPORT",
  "repeated": {
    "entries": 1,
    "downloads": 1,
    "decodes": 1
  },
  "reconnect": {
    "entries": 1,
    "downloads": 2,
    "decodes": 2
  },
  "revision": {
    "entries": 1,
    "downloads": 3,
    "decodes": 3
  },
  "removed": {
    "entries": 0,
    "downloads": 3,
    "decodes": 3
  },
  "disposed": {
    "entries": 0,
    "downloads": 3,
    "decodes": 3
  },
  "polls": 100,
  "total_limit_rejected": true
}
```

## browser

```json
{
  "evidence": {
    "kind": "UI_FIXTURE",
    "input": "SYNTHETIC only; not native Nav2 or robot replay",
    "browser": "151.0.7922.34",
    "cases": [
      {
        "name": "existing official renderer and shared model cache",
        "result": "PASS"
      },
      {
        "name": "empty \u2192 cone \u2192 costmap \u2192 supplied path generations \u2192 supplied local trajectory",
        "result": "PASS"
      },
      {
        "name": "moved, occluded, removed, lidar-only, depth-only, unmatched YOLO",
        "result": "PASS"
      },
      {
        "name": "wrong calibration, unmapped clock, sensor time skew block derived geometry/risk",
        "result": "PASS"
      },
      {
        "name": "map/epoch invalidation while paused and reconnect late packets",
        "result": "PASS"
      },
      {
        "name": "stale pose/joints and idle expiry hide URDF and risk; no goal substitution",
        "result": "PASS"
      },
      {
        "name": "inspect provenance, layer toggles, pause/step/resume, dark desktop",
        "result": "PASS"
      },
      {
        "name": "light, narrow 390px, HiDPI, accessible labels and no horizontal overflow",
        "result": "PASS"
      },
      {
        "name": "1200 packets at >=10Hz with bounded retention, UI response and burst coalescing",
        "result": "PASS"
      },
      {
        "name": "destroy/remount unsubscribes, releases history, removes canvas and cancels callbacks",
        "result": "PASS"
      },
      {
        "name": "no mutation / ROS / goal / cmd / service / websocket requests or page errors",
        "result": "PASS"
      }
    ],
    "errors": [],
    "stress": {
      "count": 1200,
      "elapsedMs": 30002.10000014305,
      "rateHz": 39.99720019579557,
      "rafCallbacks": 1801,
      "maxRafGapMs": 32.89999985694885,
      "timerDelayP95Ms": 9,
      "diagnostics": {
        "accepted": 1216,
        "rejected": 3,
        "resets": 2,
        "history": 1,
        "retainedPackets": 1,
        "lastSequence": 1224,
        "error": "",
        "geometryCopies": 0,
        "cachedLayers": 0,
        "received": 1227,
        "rendered": 1263,
        "dropped": 8,
        "pending": 0,
        "maxPending": 1,
        "maxDrawMs": 5.8999998569488525,
        "paused": false,
        "destroyed": false,
        "boxScratchBytes": 192,
        "renderedObjects": 3
      },
      "heapBeforeGcBytes": 3115620,
      "heapAfterGcBytes": 3330300,
      "heapDeltaBytes": 214680,
      "interactionMs": [
        25,
        60,
        46,
        49,
        48,
        45
      ],
      "burst": {
        "accepted": 1217,
        "rejected": 3,
        "resets": 2,
        "history": 1,
        "retainedPackets": 1,
        "lastSequence": 2424,
        "error": "",
        "geometryCopies": 0,
        "cachedLayers": 0,
        "received": 2427,
        "rendered": 1265,
        "dropped": 1207,
        "pending": 0,
        "maxPending": 1,
        "maxDrawMs": 5.8999998569488525,
        "paused": false,
        "destroyed": false,
        "boxScratchBytes": 192,
        "renderedObjects": 3
      }
    },
    "request_count": 22,
    "c3_sha": "5bf58097f4a67806f5515b931a3b8013d65bf01e",
    "source": "tests/expansion_c3/browser.mjs unchanged",
    "exit_code": 0,
    "local_only": true,
    "evidence_kind": "ACTUAL_BROWSER_UI_FIXTURE_NOT_NUMERICAL_COMPOSITION",
    "stderr": ""
  },
  "sha256": "11eecd5960b4306b024ab26e1703fb12e8ac4a6ba906a33da0eb713c677d42ae",
  "kind": "SAVED_TRACE_SEPARATE_RUN_NO_CROSS_RUN_SPEEDUP"
}
```

## process

```json
{
  "peak_rss_bytes": 158859264,
  "user_cpu_s": 2.969978,
  "system_cpu_s": 0.561049,
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
    7.45947265625,
    6.64990234375,
    5.875
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
