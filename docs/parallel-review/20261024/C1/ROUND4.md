# C1 ROUND4 — 관측·검토용 후보 고정

2026-10-25 KST. 역할 C1, 기존 브랜치 `review/20261024-c1-integration-r2`.
실제 시작 local/remote SHA: `85c5b6b85ca85e74503876b075e5ceba92dd4565`, clean independent clone.
검증 대상 기능 commit: **50ad48849ad0862aeeba034d009ac34e42fddd8e**. 이 문서 포함 최종 제출 SHA는 제출 응답에 기록한다.
후보 상태: **READY_FOR_READONLY_DEVICE_REVIEW**.

ROUND3 최초 receipt 계약, 1,200관측/중복 처리, durable intent와 STOP 선점,
기존 offline signal 미션, main `104692fa`와 L1 `5339e3b`의 채택분을 보존했다.
설치·초기 하네스·Nav2 설치·원본 fixture 재구축은 하지 않았다.

## 채택·미채택과 현재 증거

| 역할 | 이번 exact delta / 선택 | 현재 판단 |
|---|---|---|
| C2 | `8a58370be8562a8f40377ab659ee3f7776fe5200` → 기능 `0dd534fecbd8b2f485d8ab043426e05dcea2afc7`; 원격 보고서 HEAD `2f85adbb19da9c0ace02e561e54474cbf57b7c9b` | required immutable inference-settings binding 채택. C2 소유 source는 exact bytes 일치 |
| C3 | `16c63e08be5a7c10887e9e05cae94e94788e990f` → `32914885d84b9bf98e799492366aeab0f908f547` | RPP 확장/보존 lock/공통 입력 adapter/실패 결과 채택. 생산 config 교체 없음 |
| C4 | `380800ca9e211495769fe60ee8221e3f4fb40f16` → `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd` | profile/association/diagnostic/false GREEN 근거 채택. 기본 full640 유지, tile은 명시적 탐색 옵션 |
| D0 | `8ba7affe1023fc0791136aa47ca1cd8884b54685`의 공통 입력 기능 `83f4ee8d6971d00ab31b2de0eeebf329542dd5d6` | C3의 `repro/d0-source.json`에 고정된 24파일/hash와 canonical manifest `1e995e63e9e601433399f052d6a9630b4d5fb53081cfd1b00003aae2b16ef84e`로 등록·검증. materialized 입력은 ignored |
| L1/main | `5339e3b5c9906991e08766b61bd27d92e725aa6f` / `104692fa0070ef085eee918913ea05fdb2d88c05` | 이미 채택된 결과 보존, 중복 적용 없음 |

각 역할의 old→new patch만 적용했고 충돌은 없었다. C1 owner/STOP/coordinator를
역할 브랜치 전체 파일로 덮어쓰지 않았다. C2 새 코드의 소유자 commit을 먼저 읽고
채택했으며 이후 원격 제출의 ancestry와 보고서만 추가됐음을 확인했다.

후보 고정 직전 C3가 `20d7f56f24cff768e716a56813250ebbd3c2c234`로 전진했다.
새 SE2 planner/config와 recorder 증분·ROUND4를 읽었다. 그 제출에는 native 결과가
아직 pending이므로 이 후보에 **미채택**했다. 읽기 전용 RGB 후보를 새 planner
검증 대기로 막거나 생산 기준선을 바꾸지 않는다. D0
`da7230bb65722e4a1d3f4ab0c1d16e63fcd344e3`의 feasible1 독립 분석도 읽었으며
기존 공통 입력 경로의 diff는 없다. 추가 분석/이미지는 참조만 하고 복사하지 않았다.

[ROUND4_EVIDENCE.json](ROUND4_EVIDENCE.json)은 현재 채택 코드 hash, 역사적 실행 source,
immutable 입력, 선택적 연구 자료를 구분한다. 기존
`competition_evidence_revisions.json`과 과거 D0 해시는 그대로다. 새 검토 index는
runtime 전체를 여닫는 gate가 아니므로 무관한 보고서 변경이 기능을 비활성화하지 않는다.
C3 자체 RPP manifest/source 검증과 기존 D0 revision 검증은 유지한다.

### 실제 native 결과의 범위

- 일반 diagnostic: source `7a220d458fe8bce8cdd366caa4e9a546bddebd60`,
  [run 40162921802](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40162921802)
  **SUCCESS**, 시나리오 기대 7/7. 실제 원격 source/terminal 상태 재확인.
- D0 adapter: source `5eacacf42378ad91319a5de323df7844f34ea33b`,
  [run 40164154349](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164154349)
  **FAILURE**. D0 6개 evidence/safety 6/6, 기대 3/6.
  feasible1/feasible2/original_tight5의 도달 실패는 유지한다.
- D0의 옛 `ADAPTER_REQUIRED`와 C4의 옛 `received_s=processed_s` 요청은 현재
  미완료가 아니다. adapter 실행과 최초 receipt 연결은 이미 구현·검증됐다.
- 위 native 실행은 역사적 source에 귀속한다. 이 C1 SHA에서 native 실행을
  반복하지 않았다. 접촉 0을 목표 도달로, 다른 geometry의 성공을 좁은 경기장
  성공으로 바꾸지 않는다. 원본 `map_transform=null`, 현장 치수/보행 외피는 미검증이다.

## C1의 실제 연결

`session.py`는 trusted caller가 선택한 `inference_settings_sha256`를 시작 전에 받는다.
worker의 실제 detector 설정과 맞는지 검사하고 ingress 및 C2 `SignalBinding`에 고정한다.
이 C4 canonical hash에는 모델, 해상도, tile, confidence, prediction/fusion NMS 및
profile 식별자가 포함된다. 관측에서 처음 본 hash를 자동 등록하지 않는다.

같은 모델이어도 설정이 바뀌거나 hash가 없으면 gate를 닫고 기존 STOP/owner fence를
통해 세션을 종료한다. 이전 GREEN/dwell/goal을 새 설정에 이어 쓰지 않는다. 실제
C4 pipeline/projection → C2 join/runtime → C1 session의 양성/음성 회귀로 확인했다.
최초 receipt/processed/source age 계산, TTL .25초 및 물리 STOP 기준은 바꾸지 않았다.

`replay_review.py`는 기존 C4 `inspect_inputs/iter_frames`, `OwnerModel`, `TrafficPipeline`,
`TrafficWorker`, C1 ingress의 읽기 전용 projection 진단을 사용한다. 별도 navigation
port나 mission session을 생성하지 않는다. 원래 간격을 server monotonic schedule에
대응시키며, 처리가 밀려도 receipt를 현재 조회 시각으로 갱신하지 않는다.
원본 local path/URL metadata는 HTTP snapshot에 내보내지 않는다.

기존 mission 검사 영역의 `?rgb_review=1#missions`에서 원본·bbox·raw 판정,
`detection-only/associated/stable`, UNKNOWN 이유, 선택 profile/hash, 처리/queue 지연을
볼 수 있다. 미션 API가 불가해도 RGB 진단은 읽을 수 있다. browser는 조회만 하고
새 run·추론·미션 시간을 만들지 않는다. 마지막 관측과 이미지 두 세트/trace 64개만
메모리에 보관한다. 감지 raw GREEN과 실제 미션 허가는 별도다.

실제 replay에는 feet/physical STOP/path/departure facts가 모두 null이다. 합성 미션의
독립 simulated facts와 결합하지 않았다. 화면은 PRIVATE_RECORDED_RGB/LIVE 아님으로
표시하며 false GREEN(과거 tile audit: 표지판 3, 근거 부족 housing 28)과 지연을 숨기지 않는다.

기존 `?offline_signal=1#missions`는 그대로 접근→HOLD→독립 가상 STOP/발 2초→GREEN→
exit→가상 이동→완료를 제공한다. RED/UNKNOWN 유지와 계획 응답 지연 중 STOP도 유지한다.
검사에서 초기화 중 GET이 미완성 harness를 읽는 경합을 발견해, 기존 demo가 setup을
완료한 후 snapshot에 공개하도록 고쳤다. 공용 실제 하드웨어 경로는 변경하지 않았다.

## 재현과 사적 자료 경계

기존 Python/Node 환경을 사용한다. 프로젝트 루트에서:

```bash
# 공개 CI와 동일: 작은 생성 RGB만 사용
PYTHONPATH=.:tests python3 tests/competition_fixture_server.py --synthetic-rgb-review
# http://127.0.0.1:4187/?rgb_review=1#missions
# 기존 미션: http://127.0.0.1:4187/?offline_signal=1#missions

# 실제 private RGB: 기존 C4 JSONL와 local model/config를 명시적으로 선택
PYTHONPATH=.:tests YOLO_CONFIG_DIR=/private/new-review/yolo-config \
MPLCONFIGDIR=/private/new-review/mpl-config \
python3 tests/competition_fixture_server.py \
  --private-replay-manifest /private/existing/frames.jsonl \
  --replay-config /private/existing/config.json \
  --replay-model /private/existing/model.pt --acknowledge-trusted-pickle \
  --replay-fps 5 --inference-profile full640
```

JSONL의 각 행은 `image`(manifest directory 내부 파일), `sha256`, `replay_time_s`이며
C4 기존 loader가 경로/체크섬을 검증한다. 필요하면 CLI의
`--replay-observation-mode mission`으로 association 진단을 볼 수 있지만 이 viewer는
어떤 모드에서도 출발 권한을 만들지 않는다. `upper-overlap640`도 CLI에서만 선택한다.

HTTP에는 파일/모델 입력을 받는 POST endpoint가 없다. source query도 거부한다.
서버는 127.0.0.1에만 bind하고 Host/Origin 및 cross-site 요청을 제한하며 이미지에는
no-store/same-origin 정책을 적용한다. `CI` 환경에서는 private CLI 입력을 거부한다.
public CI artifact는 합성 RGB와 기존 합성 미션 자료뿐이다. 실제 스크린샷과 JSON은
C1 clone 밖의 private work 경로에만 보관했고 Git/원격 artifact에 추가하지 않았다.

### 이번 실제 저장 RGB 실행

기존 소유자 제공 모델 SHA `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`,
이미 로컬에 보존된 RGB 255장과 C4 config를 읽었다. 다운로드/촬영/설치/새 학습 없음.
full640 설정 SHA `f237ce7aea41a89a6dfaf228b206631a15c465857868c2830bd1bc4f470f56ec`.
기존 C4 Python 3.12 환경/torch 2.6.0+cpu/ultralytics 8.3.203을 재사용했다.

완료 상태 COMPLETE, 처리 255장. free detection box 수는 RED65/GREEN15/UNKNOWN20/
AMBIGUOUS5이며 target 정확도/recall이 아니다. 선택 모드는 detection-only, canonical
상태 UNKNOWN, mission 권한 0, 물리 이동 false. 완료 후 reload의 run/관측/횟수는 같았다.
원본·overlay 렌더를 시각 확인했고 private screenshot/trace를 로컬에 보관했다.

이번 로컬 실행의 마지막 pipeline 처리 1.149593초, queue residence 220.430113초로
크게 밀렸다. SOURCE_STALE/RECEIPT_EXPIRED를 실제로 표시했다. 마지막 표본 수치를
p95나 Jetson 성능으로 해석하지 않는다. 초기 UI 자동 검사의 60초 완료 대기는
timeout됐으며, 원래 replay를 재시작하거나 시계를 바꾸지 않고 완료 후 화면/재연결을
재검사했다. 처리 성공을 실시간성·실제 stable GREEN/정확도 승인으로 바꾸지 않는다.

## 실제 검사와 CI

| 명령/검사 | 이번 결과 |
|---|---|
| `PYTHONPATH=.:tests C2_CROSS_REQUIRED=1 python3 -m unittest discover -s tests -v` | 2,952 실행, 2,950 PASS / 2 SKIP, 99.539초 |
| C1 actual-package 회귀 | 기존+추가 45개를 전체 suite에서 실행; 설정 교체·누락·detection-only·RGB loader/worker·초기화 조회 포함 |
| `... unittest discover -s tests/competition_native -t tests -v` | 117 PASS, 3.098초; C1 보존 회귀 1개 포함 |
| `... unittest discover -s tests/competition_traffic -t tests -v` | 81 PASS, .372초 |
| `python3 -m unittest discover -s experiments/competition_nav2/tests -v` | 58 PASS, 2.697초; pinned D0 24파일 준비 후 원본 sensor conformance 포함 |
| `node --test tests/*.mjs` | 666 PASS |
| `npx playwright test --reporter=line` | 198 PASS, 6.5분 |
| `npx playwright test -c playwright.competition.config.mjs --output=competition-test-results` | 10 PASS, 43.2초; 공개 입력은 합성 전용 |
| `rpp_contract.py manifest`, Ruff, mypy, frontend syntax, tracked secret scan, diff check | PASS; mypy 4파일, frontend 108모듈 |
| private 실제 RGB browser 확인 | COMPLETE255/원본·overlay 표시/reload 불변/권한0 PASS; latency/정확도 승인은 아님 |

2 SKIP은 기존 optional SVG plotting/rosbags이며 신호 교차 검사를 skip하지 않았다.
샌드박스 async 테스트 정지는 해당 C1 프로세스만 종료하고 기존 비샌드박스 검사 환경에서
재실행했다. assertion 삭제/시간 계약 완화로 통과시키지 않았다.
CI는 C2 비교에 필요한 C4 exact Git objects와 D0 source를 명시적으로 fetch한다.
원격 exact code CI: [run 40168592604](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168592604),
source `50ad48849ad0862aeeba034d009ac34e42fddd8e`, **SUCCESS**, 세 job 모두 성공.
전용 통합 job은 C2 117/C4 81/C1 45/registry 2, D0 136+30+44+13+11, C3 58을 실제 실행했다. 두 OS(ubuntu-22.04/Python3.10, ubuntu-24.04/Python3.12) 모두 Python 2,952개(2 SKIP),
JS 666개, 공통 browser 198개, 전용 E2E 10개가 PASS다. browser 소요는 각각
12.9분/8.0분, 전용 E2E는 52.3초/43.4초다.
[Ubuntu22 artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168592604/artifacts/12589803134),
[Ubuntu24 artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168592604/artifacts/12589937185)를
내려받아 합성 RGB screenshot, 실제 패키지를 사용하는 합성 미션 SUCCEEDED trace와
physical_motion=false를 확인했다. private RGB 자료는 포함하지 않았다.

이 결과를 기록하는 마지막 commit은 이 ROUND4 문서만 추가한다. 기능 소스와 테스트는
위 CI source와 동일하다. 성공한 동일 검사를 반복하지 않도록 문서 commit은 `[skip ci]`로
제출하며, 이 문서 commit 자체에 별도 CI가 PASS했다고 주장하지 않는다. 최종 제출 SHA는
제출 응답에 기록한다.
새 native Nav2 실행, 장비 관측, 현장 feet/STOP 검증, actuator 연결, 실이동은 NOT_RUN이다.

## 다음 장비 작업 승인 요청안 — 관측만, 실행하지 않음

**요청 범위:** 별도 사용자 승인 후 정지된 장비의 이미 활성화된 카메라 소유자가
제공하는 RGB/취득 metadata를 제한된 읽기 전용 구독으로 확인한다. 최대 10초/50장,
대상 source·호스트·기존 공개 경로를 승인 시 특정한다. 새로운 카메라 소유권 획득,
카메라 시작/프로필 변경, 로봇 이동은 포함하지 않는다. 기존 owner가 비활성이거나
읽기 경로가 acquisition을 시작하면 중단하고 그 별도 범위를 요청한다.

**파일/서비스:** 장비의 현재 main/배포 checkout/release symlink/config/모델 파일을
덮어쓰지 않는다. `robot-scope.service` 및 camera relay/perception-shadow/control-bridge
계열의 시작·재시작·enable·설정 변경은 0개다. 위 이름은 저장소 example 기준이며
실제 설치 여부는 승인 후 읽기 전용으로 확인한다. 필요한 후보 코드는 별도 workstation
clone의 C1 고정 SHA이며, 원본 모델/config도 읽기 전용으로 둔다. 장비에 새 코드 설치 없음.

**기록/백업:** 기존 배포 commit·release target·관련 설정 hash/서비스 상태를 읽기 전용
baseline으로 기록한다. 비밀은 보고서/원격 저장소에 남기지 않는다. 새 workstation
private 디렉터리에 원본 RGB bytes, 원래 source stamp/clock/epoch/seq, local receipt,
체크섬 JSONL를 append-only 보관한다. 이미 있는 원본/ROUND3 증거는 수정하지 않는다.
실제 RGB screenshot/trace의 공개 또는 원격 업로드는 별도 승인 대상이다.

**성공/중단 기준:** source identity/clock 관계를 측정해 표시할 수 있는지, raw/bbox/
UNKNOWN/지연이 원본과 연결되는지 확인한다. source age가 미확인·지연 초과·association
미검증이면 해당 행은 UNKNOWN/INPUT_REQUIRED로 유지한다. GREEN 정확도·발 접촉·물리 STOP·
goal/HOLD ACK·실제 actuator watchdog을 서로 대신하지 않는다. 이 관측 작업에서는
ARM/initialpose/goal/velocity/posture publisher를 생성하지 않는다.

**복구:** 해당 읽기 구독과 workstation loopback fixture만 닫는다. 장비 파일·서비스를
수정하지 않으므로 배포 rollback 작업은 없다. 승인 범위를 벗어난 변경 필요성이
발견되면 실행하지 않고 baseline/원본을 보존한다. 이동 검증은 별도 계획과 승인이다.

남은 한 가지는 **이 제한된 읽기 전용 장비 관측의 별도 승인과 실행**이다. 이는 현재
후보의 실장비 PASS·GREEN 정확도 승인·native motion 활성화·main 병합 승인이 아니다.

변경 목록은 기능 commit diff와 ROUND4_EVIDENCE의 소유별 source hash에서 확인한다.
main 병합/PR/로봇 SSH·HTTP/서비스 변경/배포/실이동은 수행하지 않았다.
