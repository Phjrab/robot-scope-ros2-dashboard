# C0 N1 비이동 배포·센서 증거 결과

결과 ID: `C0-NONMOTION-20261101-N1`. 사용자가 충전선 미연결·정지 유지·즉시 중지 및 회수 가능을 직접 확인했다. C0 단일 담당으로 2026-11-01 17:15:50–17:24:56 KST 창을 수행하고 종료했다. 현장 확인은 사용자 진술이며 물리 정지 연속성을 센서로 독립 증명한 것은 아니다. 이전 W05는 종료된 별도 시험이다.

## 단계별 첫 결과와 후속 조치

| 항목 | 결과 | 이번 증거·한계 |
|---|---|---|
| 현재 base 및 보호자료 | PASS | c414 전체2268파일·links2·HTTP4·selector; map/annotation125 및 config8 대조 |
| 배포 준비·활성화 | PASS | 정확 e24, stage/정상 activate 각1회; 전체2282파일, 변경35/불변2247/삭제0, 보호자료 백업·내용/metadata 검증 |
| 실제 실행본 | PASS | `e24c52181fc4c1146fe42fcc7318a8dbd16903ee`, PID46311, 해당 release cwd·selector·HTTP 확인 |
| 지도 쌍 선택 | PASS | map1/map1_2D의 ID·revision·계보·교정 확인 및 새 generation 선택. geometry 미확인, 운영 위치추정 적용 아님 |
| 관측 READY | PASS | start1회, 정확 session에서 약6.089초 뒤 READY |
| 준비 입력 증거 | PASS | preparation GET1회, HTTP200, evidence.valid=true, 5개 check 통과, 최종 pair가 초기와 다른 exact stamp |
| 정보성 global 제안 | FAIL / 후속 BLOCKED | proposal POST1회; worker 계산 완료 뒤 상위 proposal은 `GLOBAL_AMBIGUOUS` 거절. 재시도·gate 완화 없음 |
| 운영 정합·TF/Nav2·주행 | NOT_RUN | INITIAL POSE·Nav2 시작·goal·이동 0회. P1/P2·dwell·경사로·실제 위치 URDF 검증은 의존 조건 미충족 |
| 관측 종료·source/bridge | PASS, 표본 구분 | 정확 session stop1회 후 STOPPED. 최초 bridge active 직후 제어 연결 stale 표본 보존; 이후 최종 ready/authenticated/connected 확인 |
| 관측 뒤 source strict | 최초 FAIL | tracked2282 오류0이나 예상 외 pyc1개가 추가돼 파일 집합 검사 거절 |
| 캐시 수리·별도 최종 검사 | PASS | 원본 코드 동등성 읽기 대조 후 정확 cache1개 가역 보존. 예외 추가 없이2282파일·links·HTTP·selector·보호자료 재검사1회 통과 |

배포 후보 e24의 [CI 41286223938](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/41286223938)는 세 job SUCCESS다. Ubuntu22.04/Python3.10 및 Ubuntu24.04/Python3.12 각각 Python3317(3315 PASS/2 SKIP), coverage79%, Node720 PASS, browser262 PASS, mission actual-API fixture10 PASS다. 이 CI와 아래 캐시 예방 후속 수정의 검증을 합산하지 않는다. 과거49ed9e7 CI failure는 보존했고 재실행하지 않았다.

## 지도·교정·설정과 적용 상태

- 3D map1: ID `49ea555eea2f4ca1adaea223`, revision `c9ad9bcc4c8b7c02a47a0db5822707853110b60cb4b9ef837e42b0c32e3c823e`, content SHA256 `930e7be693eac04fabeed0974031b0dccef4351c2365b6abd274fa4646be191c`.
- 2D map1_2D: ID `2fc7070075fd522860e67480`, revision `f691b8e98e81de784c89f98127de9f4ccff4aa487c76747b860bdd70a523cc76`.
- family `3df9ead4ab40285d7d687279`, revision `3d9a7cc55651a85c45cc26bcfee41b062c4a4a09f630d868a4ce0750fd79bb05`; p1/p2는 해당2D에 결합하고 annotations revision `c639ebe083cd57a0dd1dcbe61703cecc08eff51e4a6974fd10ef75a95d7a345a` 유지.
- calibration file SHA256 `5025e83be9014bef40ab6b57970a8f981fd196689e9b7404cd3503668ad28226`; 저장 Nav2 parameter revision `9a47e9d4a6c0d2b5beb0664cc1370a7bf6b70d647418815c5381f196d335645a`. 저장 설정의 revision은 생성 YAML 파일 자체 SHA와 다르다.
- 새 선택 generation `739b1e251c6f4de6baaf48a11b5b2706`. 지도 쌍 선택은 유지하지만 geometry·현재 운영 pose·단일TF/Nav2 적용은 미확인/미실행이다. 재부팅 직후의 selected=null로 되돌렸다는 뜻이 아니다.
- source 요청 정책은 pointcloud pinned `/cloud_registered`, odometry auto/빈 requested로 복원했고 selected topic도 전후 일치했다. pointcloud의 메모리 origin은 persisted→user로 바뀌었다. 영구 source 파일 hash는 최종 검사에서 보존됐다.
- 속도·yaw tolerance·progress checker·후방 가중치·교정은 변경하지 않았다. `ALL_DIRECTION_BASELINE` 운영 정책을 바꾸지 않았으나 현재 운영 정합 runtime이 없어 적용 중인 위치추정으로 표현하지 않는다.

## 준비 증거와 새 실패

관측 session `5f1a71c5b2104248a3437c4819ff18a7`. 초기 paired pose/cloud stamp `1793521239658536195`에서 최종 `1793521241059010505`로 갱신됐고, reference도 최종 exact stamp를 사용했다. 마지막 check의 pose/cloud receipt age는 0.111735/0.106092초, graph age는1.374/1.371495초였다. 각 check에서 observer·source epoch·subscription·graph identity가 일치하고 publisher 및 endpoint는 각각1이었다. reference의 자격은 `OBSERVATION_FRAME_ONLY_MAP_RELATION_UNVERIFIED`다.

서버 total3276.795ms, pair validation1108.865ms, health/handoff247.070ms, final capture20.524ms이며 client 전체 요청은3.653133초다. 초기 snapshot1833.746ms도 기록했다. 내부 구간을 lock 대기·연산 시간으로 임의 분해하지 않는다. N1 성공은 W05 실제 원인을 확정하거나 당시의 누락된 sensor stamp를 복원하지 않는다.

제안 `a2bb55d73e3472cfd0a89398`은 별도 새 exact capture를 사용했다. worker는 succeeded/reaped이나 상위 proposal은 rejected/`GLOBAL_AMBIGUOUS`였다. 원시 provider의 기존 ambiguity override는 enabled/applied=true이고 `AMBIGUOUS_UNVERIFIED_ESTIMATE` 및 `AMBIGUOUS_ALTERNATIVES`를 반환했다. 이번에 그 설정을 변경하지 않았으며 상위 gate가 운영 후보로 받아들이지 않았다.

중복을 포함한6개 내부 후보의 현재 잔차 RMSE는 약0.3054–0.3361m, 겹침은 약64.35–67.83%였다. 이는 현재 스캔과 저장 지도에 대한 정합 지표이며 실제 위치 정확도나 도착 오차가 아니다. 과거 HIGH_RESIDUAL·지도 원점·구신 지도 RMSE 조사는 하지 않았다. proposal quality/body candidate는 거절에 따라 null이다.

관측 시작 요청부터 STOPPED 확인까지33.107초였다. stop HTTP202의 STOPPING 응답과 이후 STOPPED 확인을 구분한다. 최종 Nav2/goal idle, lease/deadman false·명령0, observation STOPPED/inactive/pending false, global active=null, bridge ready/authenticated/connected 및 소유권 busy/unknown 없음이 확인됐다. 각 값은 비원자적 표본이다.

## 캐시 최초 실패·가역 수리·재발 방지 후보

추가 파일은 `robot_dashboard/relocalization/__pycache__/v031_observation_compat.cpython-310.pyc`, 8739bytes, mode0644, SHA256 `51f7991ba317318943f24a3f9faae6d7388d7644fed2d679d384a8b5bef0f710`였다. 정확 e24 원본 SHA256 `0ae898d09453b59b3daf2bdb6843a2f05c901f8697b44802a1ed801720e1067b` 및 timestamp/size 헤더와 재귀 code attributes가 일치했다. 캐시를 실행하지 않았으며 raw pyc bytes를 재현했다는 주장은 아니다.

fresh idle·정확PID·소유권 조건 아래 이 파일 하나를 `/home/unitree/robot-scope-backups/c0-n1-single-cache-20261101/`로 동일 inode/hash/mode/owner/mtime를 유지해 rename했다. 최초 실패를 지우거나 캐시 무시 규칙을 추가하지 않았다. 뒤의 엄격 검사는 별도 수리 후 검사로 PASS했고 source·지도·교정·설정 내용은 바꾸지 않았다.

C1.1의 Python3.10 합성 import 재현에서 실제 worker/adapter의 `-I` 실행과 `-I`+PYTHONDONTWRITEBYTECODE는 캐시를 만들었고 `-I -B`는 만들지 않았다. 실제 생성 프로세스를 추적한 증거는 없어 유일한 원인으로 단정하지 않는다. 최소 수정은 직접 global worker 실행과 scope admission 뒤 worker exec에 `-B`를 추가하는 두 줄이다. 공통 admission 경로의 sensor worker에도 적용되며 기존 `-I`·pin·scope·UID·socket·품질 gate는 유지한다.

신규2회귀는 미수정 임시본에서2 FAIL, 수정 임시본의 관련35검사는 PASS였다. 수정후 장비 재관측·재배포는 NOT_RUN이다. N1 창은 종료됐으며 새 배포로 이 실패를 성공할 때까지 반복하지 않는다.

로컬 후속 전체 검증: Python3319 중3317 PASS/2 SKIP,123.965초. skip은 optional SVG plotting 및 rosbags 부재다. 정확 Node20 경로를 제공한 환경으로 parity 검사가 포함됐다. ruff PASS, mypy4파일 PASS, secret scan 및 diff check PASS. JavaScript·브라우저 코드는 변경하지 않았고 기존 성공 검사를 재실행하지 않았다. 신규 exact-commit CI는 게시 후 별도 추적하며 e24 CI를 이 수정의 결과로 사용하지 않는다.

## 복구 경로와 남은 의존

배포 백업은 `/home/unitree/robot-scope-backups/c0-review-e24-e24c52181fc4/`에 유지하며 기존 c414 release도 보존했다. 복구가 필요하면 새 현재 정지/소유권과 예상 selector·base hash를 확인한 뒤 검토된 selector-only 정상 lifecycle restart 경로를 사용한다. API 불가 시 고정 systemctl 경로의 권한은 읽기 확인했지만 실제 rollback/백업 복원은 NOT_RUN이다. 지도·교정·설정을 옛 백업으로 덮어쓰지 않는다.

다음 의존은 모호한 현재 위치 가설의 구분과 사용자 INITIAL POSE·기하 조건, 운영 정합·연속 갱신·단일TF/Nav2 반영 증거다. 이를 충족한 뒤 별도 현재 goal/path/count/time 창에서 P1 정지/dwell→녹색 버튼→P2, 경사로 연속성과 실제 위치 URDF 표시를 검증해야 한다. N1 및 과거 이동 승인을 그 창으로 재사용하지 않는다.

공개 자료에는 raw 지도/점군·실제 좌표·설정 원문·자격증명을 넣지 않았다. C1.3/C1.4 검토는 C0가 보존한 receipt·JSON·코드의 독립 대조이며 장비에서 같은 검사를 재실행한 것이 아니다. 빈 stage/activate/verify 로그만으로 종료 코드나 호출 횟수를 독립 입증하지 못하고, C0가 관찰한 tool exit와 실행 기록으로 별도 기재했다.
