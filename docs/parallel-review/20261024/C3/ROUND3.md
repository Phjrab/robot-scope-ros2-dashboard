# C3 ROUND3 — 재현 가능한 RPP와 센서 출현 장애물 재계획

검토일 2026-10-25 KST. 브랜치 `review/20261024-c3-nav2-benchmark`.
실제 시작 HEAD와 당시 원격 C3 HEAD는 모두 `16c63e08be5a7c10887e9e05cae94e94788e990f`였다.
작업 트리는 깨끗했고 별도 일반 clone에서 C3 소유 경로만 수정했다.
RPP 확장 기능 source: `7a220d458fe8bce8cdd366caa4e9a546bddebd60`.
D0 연결 기능 및 최종 코드 후보: `5eacacf42378ad91319a5de323df7844f34ea33b`.
이 문서와 최종 결과만 기록하는 후속 커밋을 native 실행 source로 바꾸어 주장하지 않는다.

## 보존한 환경과 기존 결과

기존 [native run 40099437117](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40099437117)의 artifact **12562342808**을 API 확인하고 실제 다시 다운로드했다. `expired=false`, 만료 **2026-11-07T13:49:59Z**. 원본 `image-lock.json`과 보존본은 byte 일치한다.

- Base: `ros@sha256:566b87e6dfc48392189a9c32e594e84060fa9948de93b04e536f39475a1f6963`.
- Nav2 **1.1.20**, rclpy **3.3.22**, 전체 dpkg lock SHA-256 `45f626571f4fd5388d7bc174cae017e5482a4c2396254a5adfb461342076a5de`.
- `experiments/competition_nav2/repro/`: 전체 package lock, 실제 RPP YAML, 기존 8개 action terminal/validation/artifact hash, C1 계약 보존. 설치된 ROS package만 포함하며 비밀/환경/생성 지도는 없다.
- 기존 artifact 8개를 새 validator로 독립 재검사: 8/8 PASS. 이는 새 native 실행 수에 포함하지 않는다. 당시 시나리오 기대 7/8과 MPPI diagnostic의 65 s timeout/SAFE_WAIT는 그대로다.
- 기존 strict/좁은 배치 및 모든 hosted 실패 이력은 삭제하거나 성공으로 재분류하지 않았다. 원래 12-case/144 계획도 그대로이며 이번에 전체 행렬을 실행하지 않았다.

Hosted job의 새 머신에서는 예전 local image ID를 사용할 수 없어 기존 Dockerfile/build CLI에 보존 lock을 입력한다. base digest와 top-level apt 버전을 고정하고 **전체 transitive package 목록이 다르면 거부**한다. 로컬 ROS/daemon 재설치, 초기 하네스 재작성은 없다. 실행은 기존 network-none, read-only root/repo, capability drop, PID/메모리/CPU 제한을 사용한다.

## 작은 확장과 증거 경로

기존 1장애물 diagnostic을 같은 source/config/image/fixture로 3회 실행한 뒤, 출현 장애물 1회·두 장애물 1회·blocked/dropout 각 1회를 실행한다. 기존 `execute.py`, `native_runner.py`, container manager와 validator를 재사용한다.

| 항목 | 기존 diagnostic | 이번 변경 |
|---|---|---|
| 시작 / 목표 | `[2,3,0]` / `[6,3,0]` | 동일 |
| 전체 footprint | 0.716 × 0.324 m standing visual mesh | 동일; 실제 보행 외피 미검증 |
| 제한 | 0.18 m/s, 0.6 rad/s, 기존 가속도/TTL | 동일 |
| 시간 / 도착 허용 | 65 s / 0.12 m, 0.2 rad | 동일 |
| 지도 / 정책 | 별도 diagnostic room; parking allowed | 동일; 대회 geometry로 승격하지 않음 |
| 출현 장애물 | `[3.7,2.7]–[4.3,3.3]`, 처음부터 존재 | 같은 위치, goal 경과 3 s에 출현 |
| 두 장애물 | 원래 장애물 | `[5.0,2.7]–[5.3,3.3]` 1개 추가 |

출현 전 정적 지도에는 해당 장애물이 없다. 가상 scan의 실제 ray hit만 native obstacle layer로 들어간다. 새 `observations.jsonl`은 native `Path` 및 global costmap을 **구독**해 원본 좌표/전체 occupancy bytes를 lossless 보존한다. source/receipt 시각, 출현 이벤트, scan 원점/전체 ranges를 함께 남긴다. 비용지도 직접 그리기, 정답 path 입력, GT pose teleport는 없다.

검증은 이전 free costmap → 실제 scan hit → 새 lethal cell → 미래 장애물을 통과하던 native path가 우회 path로 바뀐 순서를 재계산한다. costmap과 plan의 단일 native publisher도 확인한다. path centerline 변화와 body 안전은 별개이며, body 안전은 실제 final actuator를 적분한 pose와 연속 sweep으로 검증한다. raw/native command와 final command trace, goal UUID/terminal, shutdown ZERO도 기존 검사 대상이다.

가능성 witness는 출현 이후의 모든 장애물까지 포함해 오프라인 sweep했다. 출현 fixture 1,846 samples / 보수적 clearance 0.307053 m; 두 장애물 1,847 samples / 0.107053 m. 이 수치는 native 주행 결과가 아니며 witness는 Nav2에 전달하지 않는다.

## D0 및 다른 역할 읽기 전용 확인

시작 시 D0 HEAD는 `69789d3cadded006dfc303e65e57f61941753214`였고 공통 export가 미제출이어서 기존 diagnostic 7회를 먼저 완료했다. 최종 확인에서 D0가 `8ba7affe1023fc0791136aa47ca1cd8884b54685`로 전진했음을 확인했다. 새 입력 기능 commit **`83f4ee8d6971d00ab31b2de0eeebf329542dd5d6`**, canonical manifest **`1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`**를 고정하고, C3 소유 opt-in 외부 fixture 어댑터로 연결한다. 다른 역할 코드는 수정하지 않는다.

| geometry 기준 | native 결과 |
|---|---|
| 공통 fixture 도입 전 | 기존에 실행된 C3 diagnostic 유지; 아래 ROUND3 실행 결과 |
| D0 공통 fixture 도입 후 | 아래 별도 어댑터 native 결과에 기록; 본체/센서/geometry가 달라 diagnostic과 점수 합산하지 않음 |

시작 시 C1 `review/20261024-c1-integration-r2`는 `765622ecbe20dd29b40296dd2ad24fa508ac9443`였으며 초기 C3 `d023131`까지만 채택했다. 최종 확인에서는 **`85c5b6b85ca85e74503876b075e5ceba92dd4565`**로 전진했고 C1 ROUND3 문서와 파일 blob을 확인했다. 현재 C1은 C3 **`16c63e0`까지 채택**했다. 따라서 이번 인계는 **16c63e0 → 7a220d4 → 5eacacf**의 증분이다. C1 공용 브라우저/ESM 수정은 C3가 중복 구현하지 않았다.

L1 브랜치는 실제 존재하며 HEAD `5339e3b5c9906991e08766b61bd27d92e725aa6f`다. main은 최종 확인에서도 `104692fa0070ef085eee918913ea05fdb2d88c05`로 L1 미병합이다. 시작 시 C1에는 L1이 없었지만 **최신 C1 85c5b6b는 L1의 connection-loss/proposal reset을 채택**했다고 ROUND3 문서에서 확인했다. L1·위치추정·초기값 소스는 C3가 수정하지 않았다. 다른 역할의 전진을 보존한다.

## C1 인계 계약

`experiments/competition_nav2/repro/rpp-contract.json`과 ROS-free `rpp_contract.py manifest`가 plugin/config hash, frame/topic, NavigateToPose 성공·cancel/terminal, command epoch/TTL/HOLD, image lock 및 독립 시뮬레이션 한계를 제공한다. 소스/설정 hash가 달라지면 manifest 검증이 실패한다.

```sh
python3 experiments/competition_nav2/rpp_contract.py manifest
cp experiments/competition_nav2/repro/image-lock.json /tmp/c3-lock.json
python3 experiments/competition_nav2/container/manage.py build --lock /tmp/c3-lock.json
python3 experiments/competition_nav2/rpp_contract.py run --mode isolated-sim \
  --scenario diagnostic_single_obstacle --lock /tmp/c3-lock.json --output /tmp/c3-new-run
python3 experiments/competition_nav2/run_extension.py --lock /tmp/c3-lock.json \
  --output /tmp/c3-new-extension
```

새 output 경로를 사용한다. 마지막 명령은 기존 executor로 7회를 실행한다. `--mode live`는 ROS/컨테이너를 열기 전에 argparse exit 2로 거부된다. `SIM_GT`, identity map→odom, simulation actuator는 생산 live pose나 최종 물리 command 소비자가 아니다. production import/설정은 C1이 별도로 검토하며 이 제출은 수정하지 않는다.

## 로컬 검사

| 실제 명령 / 검사 | 결과 |
|---|---|
| 기존 c3-venv Python: `-m unittest discover -s experiments/competition_nav2/tests -q` | 50 PASS |
| 같은 Python: `-m unittest discover -s tests -v` | 2,691 run; 2,689 PASS / 2 SKIP, 95.797 s |
| 기존 Node: `--test tests/*.mjs` | 70 PASS |
| Ruff `check experiments/competition_nav2` | PASS |
| `python3 scripts/check_repository_secrets.py`, `git diff --check` | PASS |
| contract manifest / live mode rejection | manifest PASS; live exit 2 |
| 다시 내려받은 기존 native artifact 독립 replay | 8/8 evidence/safety PASS; 기존 MPPI 기대 실패 유지 |

전체 Python의 기존 optional SVG/rosbags 2 skip은 native Nav2 skip이 아니다. 새 집중 검사는 설정/fixture 불변, 나중 장애물까지 포함한 witness, costmap-only 증거/관측 이전 costmap/변하지 않은 path/손상된 grid 거부를 포함한다.

## 실제 ROUND3 native 결과

[Native run 40162921802](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40162921802) **SUCCESS**, exact source `7a220d458fe8bce8cdd366caa4e9a546bddebd60`, 2026-10-25T04:48:33Z 종료. 신규 native 실행 **7회**, native/evidence **7/7**, 독립 sweep·freshness·HOLD/ZERO safety **7/7**, 시나리오 기대 **7/7**. artifact를 내려받아 로컬 `validate_directory`로 다시 7개 모두 PASS를 확인했다. `ROUND3_NATIVE.json`에 각 gate와 실제 action/명령 수/해시를 보존한다.

[Artifact 12586694269](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40162921802/artifacts/12586694269): 1,758,183 bytes, `expired=false`, 만료 **2026-11-08T04:48:29Z**. Archive digest `sha256:3c593948490bfdfb8cf46a35ccc5e45ef24edb912202d1eb07c974e1878d7427`.

이번 image ID `sha256:1ac54ef5801af2bb84e4669cbe0231fe1447ccbf8b701a29fcfb12a865d7bf78`; base와 전체 package hash는 위 보존본과 동일하다. 빌드 이미지 ID가 같다고 주장하지 않는다. 7개 실행의 실제 config hash는 모두 `ea1e0668db1e54cd6d31082317b3d3889843a3efa1377ba9d22bfb8c0a06f3b2`이고, 기존 성공 실행의 실제 config와도 동일하다. RPP 반복 3개는 source/image/config/fixture hash가 모두 같다. baseline fixture hash `631f19f08a426f4ba91666fadea3b38488580259fabde589b8532854a7ba873a`.

| 사례 | native 종료 / 결과 | 목표 오차 m | 독립 swept clearance m | 경로 길이 m | raw / final 표본 |
|---|---|---:|---:|---:|---:|
| 1장애물 repeat 0 | SUCCEEDED(4) / GOAL_REACHED | 0.115576 | 0.278915 | 4.275053 | 568 / 611 |
| 1장애물 repeat 1 | SUCCEEDED(4) / GOAL_REACHED | 0.116652 | 0.279306 | 4.266981 | 560 / 604 |
| 1장애물 repeat 2 | SUCCEEDED(4) / GOAL_REACHED | 0.116042 | 0.275223 | 4.272706 | 569 / 612 |
| 출현 장애물 | SUCCEEDED(4) / GOAL_REACHED | 0.115775 | 0.268837 | 4.377174 | 605 / 652 |
| 두 장애물 | SUCCEEDED(4) / GOAL_REACHED | 0.115241 | 0.257407 | 4.457155 | 611 / 651 |
| fully_blocked | ABORTED(6) / SAFE_WAIT | 2.700000 | 0.000000 conservative proxy | 0.000000 | 43 / 182 |
| sensor_stale | CANCELED(5) / SAFE_WAIT, SENSOR_STALE latch | 2.380524 | 0.000000 conservative proxy | 0.319500 | 45 / 138 |

0 clearance proxy는 원래 좁은 arena의 EDT-radius 보수값이며 접촉 판정은 full polygon SAT/sweep로 별도 수행한다. 모든 사례 접촉/terrain·floor 위반/HOLD 중 nonzero는 0이다. 두 장애물 native 최소값 0.2574073585 m와 독립 재표본 최소값 0.2574070078 m의 차이(−0.0000003507 m)도 JSON에 남겼다. 누적 시각에서 복원한 dt의 sweep 표본 차이이며 둘을 byte-identical 수치라고 주장하지 않는다.

출현 장애물은 goal 경과 시계 기준 아래와 같이 기록됐다. 50 ms plant tick의 부동소수점 누적 때문에 요청 3.00 s 이후 실제 출현 tick은 3.05 s였다.

| 사건 | 실제 경과 s | 근거 |
|---|---:|---|
| 장애물 출현 | 3.05 | fixture appearance + plant event |
| 최초 sensor hit | 3.10 | 실제 scan 27 beams, source pose/ranges 재계산 |
| native global costmap 삽입 | 3.35 | 새 lethal 16 cells; 출현 전 free 확인 |
| native 우회 path | 3.75 | 초기 199점 path는 미래 장애물을 통과, 이후 191점 path는 우회 |
| 우회 뒤 실제 command | 이후 구간 | native raw 531개, nonzero final 530개 |
| 최종 도달 | SUCCEEDED | 거리 0.115775 m / yaw 0.157744 rad; 전체 run wall 32.658 s |

전체 run wall 시간은 activation/종료 정리를 포함한다. goal budget을 늘리지 않았다. dropout은 경과 2.20 s에 SENSOR_STALE가 latch됐고 이후 stale nonzero 0, 실제 cancel ACK 1, terminal 5, 마지막 actuator `[0,0]`다. 모든 사례 shutdown ZERO와 자식 프로세스 정리 PASS. 최대 plant wall gap은 0.137018 s(whole-run), 각 run 75 ms 초과 tick 1회이며 hard realtime 보장으로 해석하지 않는다.

동일 source의 [공용 CI 40162921767](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40162921767)는 **FAILURE**다. 두 OS에서 Python/JS/정적 검사/의존성 audit는 통과했지만 브라우저 수집 단계가 `SyntaxError: Named export 'GO2_JOINT_NAMES' not found`, `observed_joints.js` CommonJS 처리로 실패했다. 이는 실제 실패 로그로 확인했다. C1의 공용 브라우저/ESM 수정은 C3에 채택하지 않았으며 소유 범위 밖 파일을 중복 수정하지 않았다. 전용 native SUCCESS와 공용 CI FAILURE를 합쳐 전체 CI 성공이라고 표시하지 않는다.

이 단락의 초기 RPP 통합 후보는 7a220d4다. 최신 C1은 기존 FOLLOWUP의 16c63e0를 이미 채택했으므로 그 이후 변경만 증분 검토한다. D0 연결을 포함하는 최종 코드 후보는 아래 5eacacf다. 통합 후 해당 source의 native evidence와 통합 브랜치의 offline contract 테스트를 별도 표시하고, 통합 SHA에서 native를 실행하지 않았다면 그렇게 명시한다. 이 후속 문서 커밋 때문에 같은 native 7회를 반복하지 않는다.

## 범위 및 남은 한 가지

main 병합, PR, robot SSH/HTTP, 센서/카메라 인수, 서비스 변경, 배포, ARM/실이동은 0회다. physical braking, 실제 foot/gait envelope, Omni 및 Jetson 성능은 검증하지 않았다. 선택적 MPPI 튜닝은 실행하지 않으며 기존 RPP 후보를 우선한다.

다음 한 가지: **D0 feasible1의 저장된 native path·회전 명령과 full-body 충돌 예측을 대조해 RPP 도달 실패 원인을 한 사례에서 분리**한다. 원본 holonomic witness를 정답 경로로 주입하거나 body/geometry/clearance/timeout을 바꾸어 성공시키지 않는다.

## D0 어댑터 추가 검증

실제 미완료 연결을 해결하기 위해 `--fixture`를 추가했다. `prepare_d0.py`는 pinned Git objects의 24개 파일을 hash 확인 후 C3의 ignored 입력 디렉터리에 materialize한다. 원본 triangle sensor는 프로세스로 격리해 호출하며 복사/재구현하지 않는다. 센서 반환은 0.20 s 이내로 제한하고 source/receipt age에 실제 계산 시간을 포함한다. 원본 probe 6 scenes × 3개, 전달된 모든 360 ranges가 로컬에서 정확히 일치했고 dropout의 None도 일치했다.

기존 C3 0.716×0.324 m / 0.04 m grid와 별도로, D0 원본 0.81×0.56 m에 0.03 m 축 여유를 한 번 적용한 0.87×0.62 m를 native 및 독립 sweep에 같이 사용한다. native padding=0, grid=0.02 m, scan period=0.2 s, freshness=0.25 s, dropout=4 s다. 기존 command TTL/가속도/속도 제한은 그대로다. 숨은 cone을 prior에 넣지 않으며 source/geometry/truth/observation hashes와 원본 기대를 fixture artifact에 보존한다.

초기 RPP 7회 성공은 위 `7a220d4`에 귀속한다. 어댑터 후보에서는 기존 diagnostic 1회 회귀와 D0 6회만 별도로 실행한다. D0 witness는 lateral translation을 포함하는 holonomic 가능성 증거라 DiffDrive RPP의 도달 보장이 아니다. strict/feasible 사례의 SAFE_WAIT도 기대 도달 실패로 남기며 workflow failure gate를 유지한다.

어댑터 후보 로컬 검증: 집중 58 PASS(원본 sensor conformance 6 scenes 포함), 전체 Python 2,691 run / 2,689 PASS / 2 SKIP(85.845 s), JS 70 PASS, Ruff/secret scan/diff PASS. 기존 source `7a220d4`의 실제 7개 artifact를 수정된 validator로 재검사하여 7/7 PASS를 확인했다. native 어댑터 source/run과 실제 결과는 아래와 같다.


### D0 실제 native 실행과 독립 검증

[Native run 40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349), exact source **`5eacacf42378ad91319a5de323df7844f34ea33b`**, 2026-10-25T05:07:39Z 종료, **FAILURE**. 실패 gate를 제거하지 않았다. 설치·pinned inputs materialize·sensor conformance·native 기록은 모두 성공했고, **도달 기대 3건 실패** 때문에 workflow가 실패했다.

[Artifact 12588085458](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349/artifacts/12588085458): 1,813,021 bytes, `expired=false`, 만료 **2026-11-08T05:07:36Z**, digest `sha256:c2d20937c7e2d7d2d20527994e8eaa116d2fab1d556638562ce688972317d8cb`. 원본을 다운로드하고 **7/7 독립 replay PASS**. `ROUND3_D0_NATIVE.json`에 원래 D0 기대, scene/geometry/observation hash, 실제 종료·명령 수, native 로그 발췌, conformance와 검사 hash를 보존한다.

| 사례 | 실제 native / 종료 | 독립 evidence | 독립 safety | 도달·대기 기대 | 실제 경로 m | raw / final |
|---|---|---|---|---|---:|---:|
| 기존 C3 diagnostic 회귀 | GOAL_REACHED / 4 | PASS | PASS | PASS | 4.277803 | 569 / 612 |
| D0 empty | GOAL_REACHED / 4 | PASS | PASS | PASS | 3.983161 | 503 / 547 |
| D0 feasible1 | SAFE_WAIT / 6 | PASS | PASS | **FAIL: 미도달** | 0.805500 | 115 / 230 |
| D0 feasible2 | SAFE_WAIT / 6 | PASS | PASS | **FAIL: 미도달** | 0.283500 | 59 / 175 |
| D0 original_tight5 | SAFE_WAIT / 6 | PASS | PASS | **FAIL: 미도달** | 0.000000 | 10 / 126 |
| D0 blocked | SAFE_WAIT / 6 | PASS | PASS | PASS | 0.000000 | 7 / 123 |
| D0 sensor_dropout | SAFE_WAIT / 5, SENSOR_STALE | PASS | PASS | PASS | 0.670500 | 83 / 176 |

어댑터 실행 묶음은 native/evidence/safety **7/7**, 기대 **4/7**이며, 이 중 D0만 보면 native/evidence/safety **6/6**, 기대 **3/6**이다. 앞의 다른 geometry 7/7 성공과 섞어 D0 도달 성공으로 해석하지 않는다. D0 strict 실패는 그대로 보존했다.

D0 empty 목표 오차 0.118647 m로 도착 허용 내에 도달했다. feasible1/2/strict에서는 **RPP `detected collision ahead` → FollowPath abort → `Collision Ahead - Exiting Spin` → NavigateToPose ABORTED(6)**가 실제 native 로그에 남는다. blocked는 NavFn valid path 생성 실패 후 Spin도 정지했다. 초기 하네스/설치 실패나 65 s timeout이 아니다. 이것만으로 원래 geometry가 불가능하다거나 단일 parameter가 원인이라고 단정하지 않는다. D0 witness는 holonomic이며 RPP는 vy=0인 점도 그대로다.

모든 경우 padded-body 접촉·route/forbidden 위반·HOLD 중 nonzero는 0, shutdown ZERO와 프로세스 정리 PASS. D0 unpadded body의 독립 최소 clearance는 empty/feasible1/feasible2/dropout **0.054000 m**, strict **0.037175 m**, blocked **0.041814 m**로 0.03 m보다 크다. 회전 recovery는 실제 native 출력이며 GT로 pose를 보정하지 않았다.

D0 dropout은 경과 4 s 이후 새 observation이 없고, 마지막 scan source 3.90 s, SENSOR_STALE latch **4.15 s**, stale 이후 nonzero 0, 실제 cancel ACK/terminal 5 및 마지막 `[0,0]`다. 6개 D0의 conformance는 각 3 probe(전체 18개 중 17 delivered), 전달된 6,120 ranges 모두 원본과 **차이 0**. 실제 주행 scan은 매번 현재 pose/elapsed/epoch로 D0 원본 sensor에서 산출됐으며 이 자료도 검증했다.

D0 실제 config hash **`5caef12a8f7774d55570f6404b6797ef55056c78e459d5bbfc2dd05c04826609`**. 기존 C3 회귀는 원래 `ea1e0668...`를 유지했다. 전체 package lock은 첫 RPP 확장과 같은 `45f62657...`이며 세부 image ID·전체 hash는 JSON에 있다. Body/grid/sensor 조건 변경은 opt-in D0에만 적용했고 이를 전후 동일 조건 비교로 포장하지 않는다.

동일 코드 source의 [공용 CI 40164154330](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154330)도 두 OS의 browser E2E collection에서 기존 `GO2_JOINT_NAMES` CommonJS 오류로 **FAILURE**다. Python/JS/정적·audit 단계는 통과했다. C1 소유 공용 수정은 중복하지 않았다.

C1이 검토할 코드 후보는 **5eacacf**(기존 7a220d4 결과 포함)이며 native 실행 source를 위 두 SHA로 구분해야 한다. 외부 D0 입력은 이제 ADAPTER_REQUIRED가 아니라 실제 실행됐다. 다만 3개 obstacle case는 도달 미충족이므로 대회 장애물 통과 capability를 승인하는 근거로 사용하지 않는다. 이번 오프라인 연결에 추가 필수 입력은 없다. 실제 map 정합·보행 envelope·물리 제동은 여전히 별도 INPUT_REQUIRED/NOT_RUN이며 이번 범위에 포함하지 않는다.
