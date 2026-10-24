# Nav2 패널 근거 조사 후속 기록

작성: 2026-10-24 14:12 UTC (23:12 KST). 읽기 전용 조사.

이 문서는 기존 NAV2_PANEL_EVIDENCE.md의 당시 스냅샷을 보존하면서 새 증거를 추가한다. 이전 C3의 native 실행 0회는 이전 검토 SHA 시점의 사실이며, 현재 후속 결과를 뜻하지 않는다. 이번 조사에서는 원격 문서, GitHub job 상태와 다운로드된 원시 증거를 정적으로 대조했다. ROS, 컨테이너, 벤치마크, 프로젝트 검증기 또는 로봇을 실행하지 않았으며 설정/런타임/UI/운영 코드는 변경하지 않았다.

## 1. 증거 출처와 보존

- [C3 후속 보고서](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/16c63e08be5a7c10887e9e05cae94e94788e990f/docs/parallel-review/20261024/C3/FOLLOWUP.md)
- 실제 시험 소스: afe02f38d8396d11d786d39452ac572f27d72c22. 보고서 commit과 시험 source를 구분한다.
- [Actions run 40099437117](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437117): API로 확인한 native job 120888357645는 completed/failure. 8-case 단계 failure, 증거 보존 단계 success.
- [원시 artifact 12562342808](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437117/artifacts/12562342808): 824,072 bytes. API expiry 2026-11-07 13:49:59 UTC, 그전 삭제 가능.
- 다운로드 ZIP: C3_humble_40099437117.zip. SHA256: 8c5329b1e7f7c5d5db71062b5b815f90ffbcb3a438106ffa6432b6dc129ecc13. GitHub API digest와 일치.
- 127 members, 총 압축해제 크기 6,699,821 bytes. CRC 오류, 중복 이름, 절대/상위경로, 심볼릭 링크 없음. 아카이브 코드는 실행하지 않았다.
- ARCHIVE_MANIFEST.json에 전체 member 이름/크기/SHA256; STATIC_INSPECTION.json에 이번 정적 대조; actions_jobs.json에 조회 job 상태; selected_raw에 일부 원본 JSON/log/YAML 보존. 전체 원본은 ZIP으로 보존한다.

## 2. 실제 확보된 native 증거

minimum/minimum-summary.json의 planned/attempted/native_recorded 모두 8. 8개 개별 result.json outcome과 summary가 일치하며, 모든 개별 validation.json은 PASS를 기록한다. 이것은 원격 실행자가 기록한 검증 결과의 확인이지 이번 조사자가 재실행한 검증은 아니다.

| 시나리오 | RPP | MPPI |
|---|---|---|
| empty | GOAL_REACHED, 위치오차 0.118 m | GOAL_REACHED, 위치오차 0.115 m |
| 별도 feasible obstacle diagnostic | GOAL_REACHED, 위치오차 0.115 m | SAFE_WAIT, 위치오차 0.260 m, 기대 GOAL_REACHED 미달 |
| fully blocked | SAFE_WAIT, action ABORTED(6) | SAFE_WAIT, action ABORTED(6) |
| sensor dropout | SAFE_WAIT + SENSOR_STALE, action canceled(5) | SAFE_WAIT + SENSOR_STALE, action canceled(5) |

8/8 증거 검증 PASS와 7/8 시나리오 기대 달성은 서로 다른 지표다. CI를 성공으로 바꾸어 표현하면 안 된다. 요약의 status는 COMPLETED_WITH_FAILURES다. 각 기록에 swept-footprint collision, boundary violation, HOLD 중 nonzero count는 0이다. 최종 zero 및 실제 정지거리의 해석은 물리 로봇과 분리해야 한다.

MPPI diagnostic fixture timeout_s=65.0을 확인했다. 전체 sim_time은 69.85초이므로 전체 실행시간과 목표 제한시간을 혼동하지 않는다. native.log에는 Failed to make progress → Spin recovery → FollowPath 재시작 → client cancel이 기록되어 있다. plugin setup 실패로 분류하지 않는다.

원시 params.yaml의 MPPI는 motion_model: DiffDrive, vy_max: 0.0, vy_std: 0.0이다. 이 결과는 Omni의 횡이동 효용이나 4족보행 동역학의 비교가 아니다. footprint는 0.716 × 0.324 m 사각형, pose_source는 SIM_GT다. diagnostic fixture는 명시적으로 NOT competition arena이다. reference feasibility는 1,846 samples, 최소 clearance 0.307053 m이며 실제 MPPI 주행 여유거리나 전체 경기장 성공률이 아니다. summary에서 실제 diagnostic 최소 conservative clearance는 RPP 0.278641 m, MPPI 0.109537 m로 기록되지만 단일 실행으로 우열을 일반화할 수 없다.

8개 모두 source afe02f38, 같은 image ID, Nav2 1.1.20 및 rclpy 3.3.22를 기록했다. 4쌍 모두 fixture JSON byte-equivalent, YAML에서 controller_server.FollowPath만 제외한 나머지 구조가 동등함을 이번 정적 조사에서 직접 확인했다. baseline/repeat 0/fixture seed 20261024의 단일 사례이며 MPPI optimizer RNG seed 보장은 없다. 원격 작성자의 local independent replay 완료 주장은 보고서에 있지만 이번 조사에서 replay하지 않았다.

## 3. 패널에 대한 결론

기존 패널 유지, 의미 명확화 및 후보 항목 분리라는 결론은 유지된다. 이번 결과로 RPP 또는 MPPI를 승자로 선정하거나 운영 파라미터를 바꿀 근거는 부족하다. 특히 현재 시험은 MPPI Omni가 아니라 DiffDrive이므로 Go2의 body vy 지원을 검증한 것이 아니다.

다음 근거 수집에서는 설치 plugin/version, 선택 profile, 저장값/실제 readback/브리지 제한/관측 속도를 구분하고, 반복 시험과 전체 course 및 현실적 sensor/지연 조건을 추가해야 한다. 144-run 원래 matrix, 전체 경기장, gait/slip, 실제 제동, 실제 센서, Jetson 타이밍 및 로봇 배포는 여전히 NOT_RUN이다. 팔로잉 컨트롤러 교체, UI 항목 추가, 값 적용은 이 보고서의 범위가 아니다.

## 4. C1 통합 결과와의 혼동 방지

[C1 integration review](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/765622ecbe20dd29b40296dd2ad24fa508ac9443/docs/parallel-review/20261024/C1/INTEGRATION_REVIEW.md)는 시험 source c5de97b14c3bc132bf881d132378641cf69f825a 및 승인된 D0 6403aab3afef96efa778b5265afd7ce5b351265c, C3 d0231311c41c9dcb81df35d7138cf11207be49c9를 명시한다. 이후 C3 followup은 미포함이라고 적혀 있다. 따라서 그 통합 CI 성공은 이번 afe02f38 native 시험이나 이후 D0 변경까지 검증했다는 뜻이 아니다. 이 조사에서 최신 D0 tip 자체를 별도로 조회하거나 C1 CI를 재실행하지 않았다.

## 5. 작업 범위

완료: connector 기반 자료 읽기/아카이브 다운로드, digest/CRC/경로 점검, JSON/YAML/log 정적 대조, 별도 부록 및 원시자료 로컬 보존.
미수행: ROS/컨테이너/프로젝트 validator 실행, 설치, 로봇 접속, 설정 변경, UI 변경, Git commit/push, Library 업로드. 배포 및 실제 로봇 안전성 판정은 하지 않았다.
