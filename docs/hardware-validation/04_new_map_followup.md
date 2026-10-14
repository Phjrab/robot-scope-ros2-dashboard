# 04 — 新 지도 후속 검증 (2026-10-14)

Run: `stage04-newmap-20261014T113809Z`. **새 지도·운영자 좌표의 실제 Nav2 경로 계산은 PASS, 운영 localization 시작은 FAIL이며 위치 검증은 BLOCKED다. 초기 위치를 적용하지 않았고 주행 목표를 보내지 않았다.** 이 기록은 앞선 02–04 측정을 대체하지 않는다.

## 대상과 입력

로컬/실제 원격 main은 `eb9026a`; clean 장비 checkout은 `416d25c`다. 장비의 원격 추적 ref는 오래되어 ahead 10으로 표시됐지만 이를 GitHub 최신 main으로 취급하지 않았다. 이 실행에서 source 배포나 systemd 서비스 재시작은 하지 않았다. 실제 dashboard cwd/interpreter, runtime/gateway source hash, Nav2 executable/plugin hash, 설정과 도구 hash를 private evidence에 기록했다.

운영자가 지도 이름을 정정하고 제공한 초기 위치에 현재 정지해 있음을 확인했다. 실제 catalogue의 map ID/revision, PCD→occupancy family lineage를 고정했다. 새 지도는 302×176, 해상도 0.05m, free 18723/occupied 34429/unknown 0이다. 초기·목표 cell은 free이며 비free cell 사각형을 고려한 보수적 지도 여유는 각각 1.408m/1.453m였다. 실제 구조의 정답·지도 편집 정확도를 확인한 것은 아니다. 지도 이름/좌표·원본 지도와 상세 identity는 private evidence로 보존했다. 운영자가 이전 목표 검증을 보고했지만 그 주행의 독립 증거로 쓰지 않았다.

## 운영 localization

기존 Nav2 job이 실행 중이었고 이전 goal은 terminal이었다. active mission/lease 없음, deadman false, zero command를 확인한 뒤 승인된 04 범위에서 기존 Nav2만 API로 정상 중지했다. 기존 공유 mapping job과 FAST-LIO는 계속 유지했다. exact map/parameters revision을 고정한 localization-only 시작은 `navigation startup timed out: navigation localization inputs are stale`로 실패했다. 세션은 자동 정리됐고 초기 위치 count는 0이다.

첫 실패 이후 6.083초 passive 측정에서는 host callback wall time minus header stamp가 raw LiDAR 0.116–0.129초, FAST-LIO odometry 2.606–5.436초, registered cloud 2.613–5.467초였다. 원래 sensor clock·물리 end-to-end 지연은 미검증이므로 이 값을 독립 latency로 보고하지 않는다. 그 뒤 10.018초 관측에서 odometry 102개, source stamp 엄격 증가, 단일 publisher, stamp 차이 0.064–0.231초, callback 최대 gap 0.208초를 확인했다. raw LiDAR도 기존 age gate를 충족했다.

이 **측정된 입력 회복 이후 새 조건에서 한 번** localization-only를 시도했으나 다시 같은 stale startup 실패가 발생했다. 초기 위치 요청 gate가 열리지 않아 `/initialpose`를 발행하지 않았다. 시작 중 API sample은 cloud age 약 0.001–0.098초였으나 유효 odometry age/rate는 null이었다. 모든 현재 조건의 root cause를 확인했다고 주장하지 않는다. 추후 필요한 좁은 조사는 startup 중 runtime odometry callback/검증 탈락, source stamp 및 executor backlog를 함께 기록하는 것이다. 동일 조건으로 계속 기동하거나 timeout/freshness/rate 기준을 완화하지 않는다.

READY, operational pose alignment, 안정성/정확도, map→odom 및 odom→base의 정상 운영 authority는 BLOCKED다. 위치 오차는 null이다. D2 onboard source 변경은 아직 장비에 없고 observer/manager opt-in 0이어서 D2 job/후보 적용도 수행하지 않았다.

## 독립된 실제 planner

Nav2 planner 1.1.20 및 `nav2_navfn_planner/NavfnPlanner`를 **domain83 + localhost-only + 실험 namespace + 전용 TF remap**으로 실행했다. 시작 전 domain이 비었고 실행 graph에 control, cmd_vel, NavigateToPose, FollowPath endpoint가 없었다. 운영자가 제공한 정지 위치와 목표를 격리된 실험 pose로 투영했다. 운영 TF로 발행하지 않았다.

기존 Navfn A*, tolerance0.5m, allow_unknown=true, radius0.22m, inflation0.25m/cost scaling5, static+inflation 설정을 유지했다. scan obstacle layer는 포함하지 않는다.

| 실제 action 입력 | 결과 |
| --- | --- |
| 제공 초기 위치→목표 | SUCCEEDED(status4), path90, 길이2.257095m, 끝점 일치 |
| occupied / 지도 밖 / 다른 frame | 각각 ABORTED(status6), path0 |

이 결과는 경로 계산의 증거이며 로봇 위치 정확도/목표 도달/실제 주행 승인이 아니다. unknown0인 새 지도에서는 unknown 거부를 재검증하지 않았다. 이전 synthetic unknown 허용 FAIL은 남는다. 새 지도에는 annotation이 없고 KEEP_OUT은 display-only semantics이며 실제 costmap enforcement는 미검증이다. native action의 map-revision fence와 통과 불가능 통로 재검증은 이 후속 범위에서 수행하지 않았다. planner 설정과 입력을 바꿔 이전 공백을 PASS로 만들지 않았다.

## 종료와 다음 조건

소유 planner exit0, 두 실패 세션의 runtime 자동 정리, passive subscriber 종료를 확인했다. dashboard/bridge/relay의 현재 PID와 invocation은 전후 동일하고 기존 FAST-LIO와 공유 mapping job은 유지됐다. 원래 Nav2는 중지했고 운영 localization은 failed/inactive로 남겼다. 이전 terminal goal 표시를 새 주행 성공으로 해석하지 않는다. 지도 파일 hash는 모두 불변이다. lease 없음, deadman false, commandzero이며 bridge의 nonzero Move count는 전후1019로 동일하다. 최종 물리 정지는 독립 관측하지 않았으며 시작 전 운영자 확인과 소프트웨어 종료 상태를 구분한다.

카메라/VSLAM 작업·재설치·초기화·ARM·lease·이동 목표·장애 주입은 수행하지 않았다. **05단계는 미승인이다.** 먼저 stale startup의 원인을 확인하고 기존 interlock을 만족하는 localization-only 경로에서 이 지도/실제 pose의 적용 및 정렬을 검증해야 한다. [구조화 판정](04_new_map_followup.json)은 이전 검증 matrix와 별개이며 전체 04 acceptance를 승인하지 않는다.

## 문서 검증

이번 변경은 문서/판정 JSON뿐이다. 커밋 전 요구된 plain Python 전체 suite는 1633개(2 skip)를 실행했고 기존 FastAPI/Starlette/Pydantic 누락으로 import error 6개가 남았다. 실행 환경은 설치/변경하지 않았다. JavaScript 360개 통과, JSON 상태/null 계약·상대 링크·whitespace·private 경계 검사를 통과했다. 앞선 가상환경 1675개 통과 기록은 최초 보고서에 유지하며 이번 실행의 성공으로 복사하지 않는다.
