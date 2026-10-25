# C2 ROUND4 — 추론 설정 binding 마감 / 기능 동결

2026-10-25 KST. 브랜치 `review/20261024-c2-mission-adapter`.
실제 작업 기준은 local/remote가 일치한 `8a58370be8562a8f40377ab659ee3f7776fe5200`이며 시작 시 작업 트리는 깨끗했다.
**검사 대상 기능 커밋: `0dd534fecbd8b2f485d8ab043426e05dcea2afc7`.**
후속 커밋은 이 검토 문서만 추가하며, 문서 포함 최종 HEAD와 원격 CI 상태는 제출 응답에 기록한다.

## 현재 코드로 확인한 기준선

| 읽기 전용 대상 | 실제 원격 HEAD | 확인 결과 |
|---|---|---|
| main | `104692fa0070ef085eee918913ea05fdb2d88c05` | 변경하지 않음 |
| C1 r2 | `85c5b6b85ca85e74503876b075e5ceba92dd4565` | ROUND3 C2 runtime/시간 계약 채택. session public guard, planning await 뒤 guard, ingress 오류 시 gate.retire, 관측 ledger 개선 존재 |
| C4 | `9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd` | context의 inference_settings_sha256/observation_mode, 실제 settings/pipeline/projection 확인 및 교차 실행 |
| L1 | `5339e3b5c9906991e08766b61bd27d92e725aa6f` | 브랜치 존재. C1의 DIAGNOSIS.md/live_observation.js/test_live_observation.mjs가 L1과 동일함을 diff로 확인 |

C1 ROUND3의 1,200 관측 + 1,200 duplicate/reconnect, 공통 fixture 및 브라우저 결과는 이전 완료 증거다. 이번 C2의 재실행 결과로 계산하지 않는다. 최신 C1 exact SHA의 [CI 40164585569](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40164585569)는 조회 시 completed/success였다. C4 문서의 과거 C1 미완료/L1 미통합 상태를 현재 미완료로 재사용하지 않는다.

## 최소 변경과 승인 경계

제품 코드 변경은 `robot_dashboard/mission_routes/competition_native/fragments.py` 한 파일이다.

- frozen `SignalBinding`에 필수 `inference_settings_sha256: str`을 추가했다. trusted owner가 관측 수신 전에 선택한 설정의 digest다. observation의 값을 기대값으로 자동 등록하는 코드가 없다.
- 형식은 정확히 소문자 `[0-9a-f]{64}`다. owner pin이 잘못되면 생성 시 `C4_EXPECTED_INFERENCE_SETTINGS_INVALID`; 인자 자체를 생략하면 생성자가 거부한다.
- context 값 누락/None은 `C4_INFERENCE_SETTINGS_REQUIRED`, 형식 오류는 `C4_INFERENCE_SETTINGS_INVALID`, 다른 유효 digest는 `C4_INFERENCE_SETTINGS_MISMATCH`다. 대문자·공백·줄바꿈·비문자열을 조용히 정규화하지 않는다.
- 명시적 `observation_mode="mission"`이 아니면 `C4_MISSION_OBSERVATION_REQUIRED`다. detection-only bbox/영상은 미션 발/STOP/출발 근거가 되지 않는다.
- 불일치 시 Packet을 반환하지 않는다. 기존 C1 `SoftwareNativeSession.observe`의 ingress 오류 처리에서 gate가 retire된다. C2는 observation/diagnostic image/bbox를 수정하거나 pipeline을 중지하지 않는다.
- 설정 변경을 현재 실행의 기대값 수정으로 수용하지 않는다. trusted owner가 기존 실행을 종료하고 새 binding/runtime을 구성·검토해야 한다. 새 producer epoch도 같은 재바인딩 경계를 유지한다.

`config_hash`, `model_sha256`, producer/epoch/clock/association/sequence 및 최초 receipt 검증은 그대로다. 모델 가중치가 같아도 tile·해상도·추론 설정의 동일성을 의미하지 않는다. sidecar v0.1 내 추가 필드 확인으로 충분하므로 v2 schema/새 FSM/추가 검증 계층을 만들지 않았다.

runtime.py, adapter.py, coordinator.py, state.py, observations.py, authority.py 및 공용 파일은 변경하지 않았다. TTL .25초, C4 색 안정성 .4초, 독립 STOP 2초 기준과 최초 수신 시각 계산도 변경하지 않았다.

## C1에 필요한 정확한 호출 변경

현재 `CompetitionIngress.join`의 non-fixture 경로는 이미 실제 C4 projection과 C2 join을 호출한다. 함수/입출력은 그대로이며 **기존 SignalBinding 생성에 owner digest keyword를 추가**한다. 기존 C1 session/ingress/worker/shared coordinator를 이 브랜치에서 수정하지 않았다.

```python
# Trusted composition, before accepting any observations.
# The digest comes from approved owner configuration, never observation.context.
signal_binding = SignalBinding(
    producer_id=trusted_source_id, epoch=trusted_epoch,
    source_clock=verified_source_clock, config_hash=approved_traffic_config_hash,
    binding_id=approved_binding_id, model_sha256=approved_model_sha256,
    signal_id=approved_signal_id, crossing_id=approved_crossing_id,
    receiver_clock_id=session.runtime.config.receiver_clock_id,
    inference_settings_sha256=approved_inference_settings_sha256,
)
session.ingress.signal_binding = signal_binding
```

현재 C1 `tests/competition_integration/harness.py::SoftwareHarness.asyncSetUp`의 `SignalBinding(...)`도 같은 keyword가 필요하다. 합성 Detector의 고정 profile은 실제 C4 `inference.settings("full640", confidence_floor=.25, model_sha256=approved_model_sha256)`로 관측 전에 계산하여 detector와 owner pin 양쪽에 지정할 수 있다. 실제 운용에서 관측이 전달한 profile 이름이나 digest를 이 계산의 승인 입력으로 삼지 않는다. trusted 설정 digest를 이미 보관했다면 그 값을 그대로 사용한다.

C1의 현재 `.github/workflows/ci.yml` 두 `Fetch exact historical dependencies for C2 comparative tests` 단계는 `765622e`와 `380800c`만 fetch한다. 이번 전용 테스트를 채택할 때 목록에 **`9e9ebcc0cbc613d5b0a7f50a27a7b256c3f829bd`**를 추가하고 기존 `C2_CROSS_REQUIRED=1`을 유지해야 한다. 공용 CI 수정은 C1 소유이며 이 브랜치에서는 하지 않았다.

first receipt/1,200 tick/STOP/await guard patch는 다시 적용할 대상이 아니다. 자세한 유지 계약은 [WIRING_PROPOSAL.md](../../../mission-competition/native-adapter/WIRING_PROPOSAL.md)에 있다.

## 기존 fixture와 호환성

기존 raw C4 입력에 digest 또는 mission mode가 없으면 최신 non-fixture join에서 거부한다. model hash나 config hash로 digest를 추정하지 않는다. C1의 `source_clock="fixture"` + 명시적 synthetic activation 전용 분기는 기존 offline 경로로만 보존할 수 있으며 native 증거로 승격하지 않는다. C4 projection 자체도 fixture clock을 거부한다.

기존 C2 synthetic SignalFragmentTests는 hand-authored expected digest/mode를 명시했다. 역사적 C4 `380800c` pipeline 교차 검사 한 곳은 stub detector의 선언된 pin/mode를 **테스트에서만** context에 공급한다. 이는 구형 C4가 해당 metadata를 원래 내보냈다는 주장이 아니다. 원본 증거/JSON fixture는 덮어쓰지 않았다. 최신 C4 검사 9개는 실제 pipeline이 내보낸 metadata를 그대로 비교하며 missing/malformed/다른 설정의 거부를 검증한다.

기존 dependency overlay에 exact C4 SHA와 필요한 Python module 목록만 추가했다. 다른 역할 소스는 Git 객체에서 임시 디렉터리로 읽고 정리하며 C2 tracked 파일로 복사/병합하지 않는다. 테스트 중 fetch/install/network는 없고 exact 객체가 없으면 NOT_RUN/SKIP, `C2_CROSS_REQUIRED=1`이면 실패다. C2 자체의 이전 공용 CI shallow checkout에서 교차 검사가 SKIP되더라도 이를 교차 PASS로 계산하지 않는다.

## 실제 교차 검사와 고정 후보 검증

신규 9개 검사는 실제 C4 settings/config/frames/pipeline/association/projection을 실행한다. detector는 stub, 동일 JPEG는 작은 합성 영상, clock/physical facts는 합성이다. 실제 모델 색 정확도·원본 RGB replay 검증이 아니다. C4가 사용하는 D0 helper는 기존 C2 checkout의 보존된 버전이며 최신 D0 전체 통합을 주장하지 않는다.

| 신규 교차 검사 | 결과 |
|---|---|
| owner pin 형식·immutability | PASS |
| 동일 설정, first=10.00 / age=.02 / processed=10.08 / now=10.15 → age=.17 | PASS |
| 동일 model/imgsz에서 full640 → upper-overlap640; C4가 다시 GREEN이 되어도 기존 owner는 거부 | PASS, bbox/영상 참조 유지 |
| 설정 누락·malformed·상이한 digest | PASS, 자동 pin 없음 |
| 새 epoch와 기존 runtime 재바인딩 거부 | PASS, old GREEN 복원 없음 |
| old GREEN polling·추론 완료 시각 대체·만료 | PASS, receipt 갱신 없음 |
| 같은 JPEG의 정상 새 seq/stamp와 stamp 재사용 거부 | PASS |
| detection-only 표시 보존과 mission 거부 | PASS, feet/STOP/departure 생성 없음 |
| mission mode 없는 구형 입력 / fixture clock | PASS, native 승인 없음 |

기존 환경에서 실행한 명령:

```bash
C2_CROSS_REQUIRED=1 python -m unittest tests.competition_native.test_inference_binding -v
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests/competition_native -t . -v
C2_CROSS_REQUIRED=1 python -m unittest discover -s tests -v
node --test tests/*.mjs
node scripts/check_frontend_syntax.mjs
ruff check --no-cache robot_dashboard scripts tests/competition_native
python -m mypy --config-file mypy.ini
python scripts/check_repository_secrets.py
git diff --cached --check
```

| 고정 후보 실제 결과 | 수치/범위 |
|---|---|
| 신규 inference binding | 9 PASS, .397초 |
| C2 전체 | **116 PASS**, 1.162초. 이전 107개 + 신규 9개 |
| 전체 Python | **2,807 실행: 2,805 PASS, 2 SKIP**, 85.059초 |
| JavaScript | **660 PASS**, 1.380초 |
| frontend syntax / Ruff / mypy | PASS / PASS / 설정된 4개 파일 PASS |
| staged secret scan / diff whitespace | PASS |

Python 3.12.3/Pydantic 2.13.4 기존 venv, 기존 NumPy/OpenCV/Pillow, Node 24.19.0, Ruff 0.6.9 및 기존 quality venv의 mypy를 재사용했다. 설치/초기 하네스/Nav2 설치/공통 fixture 재구축 없음. 전체 async/IPC 테스트는 기존 샌드박스 종료 제한을 피하는 승인된 환경에서 실행했으며 로봇/외부 서비스가 없다. SKIP 2개는 optional rosbags 미설치, PCD_EDIT_NODE 미설정이다. 기존 fixture의 BLOCKED/COMPUTED_DECLARED_INPUTS 출력은 예상 결과다. 원시 로그/영상/가중치는 업로드하지 않았다.

이전 C2 `8a58370` [CI 40163606542](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40163606542)는 양쪽 matrix에서 Python/JS까지 통과하고 공용 browser E2E에서 실패한 것을 실제 job 상태로 확인했다. 최신 C1의 성공 결과와 구분하며 C1의 공용 수정을 중복 적용하지 않았다. 이번 exact 최종 제출 CI 상태/run/artifact 여부는 push 후 조회하여 응답에 기록한다. 이번 로컬 공용 browser E2E/실제 C1 전체 재통합은 NOT_RUN이다.

증거 구분: **합성 소프트웨어 교차 시험 PASS**. 실제 Nav2+가상 센서, 실제 저장 RGB replay, 실장비 관측, 실이동은 이번 C2에서 모두 NOT_RUN이며 이전 타 역할 증거로 대체하지 않는다. `live_ready=false`를 유지한다.

## 물리 입력 인계 — 미확인 값은 unknown

| runtime에 필요한 사실 | 필요한 입력·시각·검증 | 현재 확보 여부 / 미연결 지점 |
|---|---|---|
| 앞발 영역 판정 | 두 앞발의 측정 위치, 센서/관절 frame→body→zone 변환, leg 기구학·보정, stop-zone geometry, producer epoch/seq/source stamp와 동기화 오차 | 합성 feet Packet만 검증. 실제 producer/보정/zone 정확도 **unknown**. 3D 모델/FAST-LIO IMU pose만으로 앞발 접촉·앉기 정확도를 입증하지 않음 |
| 실제 STOP·departure | 독립 measured pose/velocity 또는 관절 상태의 출처와 취득시각, freshness/continuity, HOLD 설치 이후 2초 STOP 및 exit ACK 이후 독립 MOVING/departure | 합성 측정만 있음. 실제 source/topic/frame/속도 임계값 검증 **unknown**. command 또는 goal/HOLD ACK는 물리 정지·이동 증거가 아님 |
| final command consumer | 기존 `FinalConsumerConstraintPort(install=...)`의 실제 설치 callback/ConsumerReceipt, 단일 최종 소비점의 HOLD latch·old RELEASE fence·watchdog/E-stop | C2 port와 C1 software SessionGate/CommandBoundary 연결은 구현됨. 기존 `ControlManager`/navigation command bridge 이후 실제 actuator 소비점의 연결·설치 ACK·물리 watchdog 검증 **unknown**. 새 publisher/node/monitor 없음 |

이 표는 미확인 입력의 인계다. 사용자에게 같은 정보를 다시 전부 요구하거나 오프라인 통합을 차단하지 않는다.

## 변경 목록과 마감

기능/전용 검사: `fragments.py`, `tests/competition_native/{dependency_overlay,test_inference_binding,test_round3_cross_contract,test_runtime_contract}.py`.
문서: `docs/mission-competition/native-adapter/{HANDOFF,WIRING_PROPOSAL}.md`, 이 `ROUND4.md`.
다른 역할 파일·공용 session/ingress/worker/coordinator/UI/CI·main을 수정하지 않았다. 삭제/이동/바이너리 추가·사용자 변경 덮어쓰기 없음.

**C2는 기능 동결/통합 검토 대기로 마감한다. 남은 한 가지는 C1이 이 exact delta와 trusted profile pin을 기존 통합 브랜치에 증분 반영하고 자신의 통합 검사를 수행하는 것**이다. 구체적인 C1 회귀가 발견되면 그 항목만 후속 수정한다. 새 FSM/terrain/parking/튜닝/추가 하네스를 자동 확장하지 않는다.

main 병합·PR 생성·장비 접속·센서 인수·서비스 변경·배포·실이동을 수행하지 않았다.
