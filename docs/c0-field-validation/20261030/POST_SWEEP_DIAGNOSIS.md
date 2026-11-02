# C0 1차 종료 뒤 진단과 2차 후보

이 문서는 ROUND1_RESULTS.md/json과 ROUND1_CLOSED.json을 먼저 만든 뒤 작성했다. 이번 source는 main 846121b이며 제품 코드·주행 설정 변경, 장비 배포·이동은 0건이다. 과거 실기 요약과 이번 직접 실행을 아래에서 구분한다.

## 관측 사실과 미측정 경계

| 사건 | 이번 확인 사실 | 처음 확인하지 못한 경계 | 원인 확정 수준 | 최소 다음 검사 |
|---|---|---|---|---|
| C0-CONNECT | SSH와 대시보드 후보 GET 모두 No route to host | 장비 IP/전원/물리 링크·실제 endpoint | 연결 실패는 확인; 전원 OFF/주소 변경 등 원인은 미확정 | 운영자가 기존 장비 전원·망을 확인한 뒤 동일 경로 read-only probe 1회 |
| C0-CI | main 846121b CI run41001998475의 Ubuntu24.04 job123888307012가 URDF old-revision 숨김 poll 114행에서 20초 timeout | 해당 CI 브라우저 내부 redraw/응답/타이밍 | 실패 위치 확인; 이번 동일 대표 시험 1회는 통과, 원인 미확정 | 보존 artifact/trace에서 response→state→draw 경계를 비교; timeout 확대/skip으로 숨기지 않음 |
| C0-PROGRESS | 이번 실제 Gateway 호출에서 작은 양의 첫 값 .0416856 이후 .838→…→.490일 때 진행률 0 | 첫 거리값이 새 goal/새 plan에 속한다는 식별 | SOFTWARE_REPRODUCED; 원시 field replay 아님 | goal generation/plan provenance를 pin하는 단일 수정 설계와 stale-first/진짜 정체 대조 |
| C0-ARCHIVE | 기존 보고에 generated YAML/bundle cleanup 뒤 원본 archive 미확보; 현재 navigation_jobs._cleanup_job_dir가 job 디렉터리 제거 | cleanup 이전 원본 보존 영수증 | 이전 누락+현 코드 경계 확인; 이번 장비 파일은 미조회 | 실제 시작 전 현재 job의 제한된 YAML/bundle/effective snapshot을 private에 복사하고 hash 확인 |
| C0-STOPGO | software 2초 dwell/one-shot/source generation/최종 dispatch guard 통과 | 이번 실제 Nav2 success→fresh 측정 정지→dwell | 구현 연결은 software 확인; 실기 미측정 | 새 시험창 내 stop+next 1묶음, 실제 receipt와 goal 수·출발·종료를 따로 계측 |
| C0-RAMP | ALL_DIRECTION_BASELINE, 같은 source stamp body heading sector/pitch 계측과 별도 obstacle 경로 존재 | 실제 ramp raw/LIO/correction/TF/scan/browser 시간열 | 실제 첫 악화 단계 미측정 | 정밀 도착과 독립 가능한 기존 수동 관측 1회; 지원되는 관측 전용 ownership 먼저 확인 |

No route to host는 프로그램의 위치추정 실패나 인증 실패가 아니다. 현재 STOP·lease·active goal을 알 수 없으므로 현재 정지 안전성을 전제한 서비스 변경·이동을 시작하지 않았다. 다른 장비인 jetson5/JamoBridge의 주소를 이 로봇으로 대체하지 않았다.

## 정밀 방향 잔차와 접근 정체는 다른 문제

아래 두 행은 10월30일 기존 현장 보고서 5154761의 결과다. 이번 C0에서 재주행하지 않았고 private 원시 장비 기록을 재확보한 것도 아니다.

| 기존 사례 | 확인된 결과 | 아직 확정 못한 물리 원인 | 별도 후보 |
|---|---|---|---|
| 가까운 약20도 회전 | SUCCEEDED, 결과 수신 부근 yaw −4.72°, 첫 측정 정지 −6.87°. active TF extrapolation/collision 0/0 | 이후 body yaw 변화가 대부분을 설명하지만 외부 ground truth 아님 | 별도 yaw .05rad 한 가지만 비교하는 기존 오프라인 후보. 외부 완료기준 .10m/.10rad·정지2초 유지 |
| 약 .80m 접근 | CANCELED, active 표본 최저 XY12.93cm로 .10m 내부 0건, 순수 최종 회전 표본0. native progress abort2 | accepted .05~.07248m/s 명령 대비 몸체 진행이 작음. 저속응답/현장조건/곡률/보정 기여 미분리 | 동일 기록의 requested goal/plan→bridge accepted→body motion→correction 경계 정렬 먼저. 최소속도 강제 증가·progress 무력화 안 함 |

현재 원인으로 옛 TF 오류를 재사용하지 않는다. 두 번째를 제자리 회전 중 translation-only checker 중단으로 설명할 근거도 없다. 이번 1차 과정에 yaw tolerance·속도·progress checker·후방 가중치 탐색을 하지 않았다.

## 이번 진행률 재현

POST_SWEEP_PROGRESS_REPRO.json은 공개된 과거 rounded 거리와 합성 0.5초 간격을 main846121b의 실제 NavigationRosGateway 메서드에 입력한 결과다. 실제 ROS/로봇/명령 publisher를 만들지 않았다.

| 입력 | 첫 baseline | 마지막 계산 진행률 |
|---|---:|---:|
| .0416856→.838→.681→.581→.531→.515→.490 | .0416856m | 0m/s |
| 작은 첫 값 없이 .838→…→.490 | .838m | .050m/s |
| .838 유지(실제 정체 대조) | .838m | 0m/s |

이는 처음 양의 거리값을 곧바로 best baseline으로 고정하는 경계를 재현한다. native SimpleProgressChecker abort와 별개다. 이 자료로 .05rad 후보나 속도 변경의 효과를 주장하지 않는다. baseline을 매번 더 큰 값으로 재설정하면 실제 정체/진동을 진행으로 오인할 수 있어 임의 수정하지 않았다.

## 2차 후보와 의존성

| 후보 | 단일 변경/목적 | 먼저 할 오프라인 반증 | 필요한 현장 | 되돌리기 |
|---|---|---|---|---|
| C0-P1 계측 보존 | generated YAML·bundle·effective readback을 cleanup 전 private 보존 | 제한 크기·snapshot 일관성·symlink/손상·디스크 실패 시 STOP 비차단 | 장비 연결/idle·실제 job 경로 확정. 이동 권한 불필요 | 별도 wrapper 종료; 제품 STOP/cleanup 경로 그대로 |
| C0-P2 진행률 provenance | 새 goal의 plan/feedback 식별 경계만 보완 | 작은 양의 stale-first, zero-first, genuine stall, source/goal 변경 대조 | 먼저 소프트웨어 수정·전체 검사. 실기 일정은 별도 | focused commit revert; controller 파라미터 고정 |
| C0-P3 yaw 여유 | 기존 .10rad→.05rad 후보 하나 | 기존 generator/validator 및 최종 회전 보호 검사 | 1차 표와 분리한 새 감독 시험창/단일 목표. 이번에는 적용 안 함 | 현재 .10rad saved/generated/live 일치 복원 확인 |
| C0-P4 접근 정체 | 현재는 단일 변경 후보 선정 전 | source/plan/bridge/body/보정 같은 시각 연결 및 원본 확보 | 반복주행 전에 원인 분리. yaw와 progress를 동시에 바꾸지 않음 | 현 기준 유지 |
| C0-P5 rear/side | 문제 확인 시 matcher 파생 입력의 bounded 가중만 | 동일 source stamp cloud+pose+reference에서 full 비가중 오차·overlap·정보분포·age/jump/dropout/처리시간 A/B | 먼저 ramp baseline 입력 필요(INPUT_REQUIRED). 전방 장애물 경로 유지 | ALL_DIRECTION_BASELINE 유지 |

V05의 실제 재출발은 V03 실제 source와 V04 actual success·fresh stop·dwell에 의존한다. G1/G3 software PASS가 이 의존성을 우회하지 않는다. V06 수동 관측은 정밀 도착 성공과 독립이며, 자율 lease와 수동 명령이 경쟁하지 않는 지원 경로가 있어야 한다.

R2/R3는 baseline 입력이 없으므로 INPUT_REQUIRED다. 양호한 실제 baseline이면 BASELINE_RETAINED로 닫을 수 있지만 현재는 그렇게 판정하지 않는다. sensor X<0이나 map X<0을 물리적 후방으로 가정하지 않는다. 원래 raw LIO 입력과 전체 전방 collision sensing은 보존한다. 정확한 정답이 없으면 ATE/RPE와 위치 정확도는 UNKNOWN이다.

## 재개와 복구

최소 다음 작업은 **장비 연결을 복구해 비이동 실제 상태를 읽는 것**이다. PID/cwd/source manifest·overlay hash, saved/generated/live, map pin·worker hash, STOP latch·lease·active job/goal·mapping/카메라 소유권부터 확인한다. 이미 배포된 코드가 충분하면 재배포하지 않는다.

필요한 배포가 생기면 idle/미저장 데이터/소유자와 기존 백업 유효성을 확인하고 사용자 dirty 파일·selector·profile만 증분 보존한다. 별도 exact-SHA release로 적용한 뒤 정지 상태 검증을 먼저 수행한다. 기존 검증된 2D·보행·/opt/ros·map/PCD/DB를 일괄 복원하거나 업그레이드하지 않는다.

현재 장비에 변경한 것이 없어 C0 배포 rollback은 해당 없음이다. 현재 물리 STOP/실행 release와 과거 백업의 유효성은 미확인이다. 옛 goal·GREEN·허가는 재사용하지 않는다.
