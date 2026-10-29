# C3 2차 보완 — canonical snapshot / 실제 core·HTTP 연결

> 최신 후속 검증: [C1 0.2·bulk·native 기록 재생](ROUND2_V02.md). 아래는 이전 SHA의 역사적 결과이며 현재 계약/실행 상태는 이 링크를 우선합니다.

2026-10-29. **C3 보완 구현 및 합성 입력의 실제 core·HTTP·화면 검증 완료. 생산자 계약 직접 연결은 미완료. ROS/native/device 미실행.**

## 제출 및 검증 기준

- 기존 브랜치: `review/20261029-x-c3-scene-ui`. 기존 구현/커밋을 보존했다.
- 이전 제출 HEAD: `92658bccc253f31552415f9c9d667bbd28957a06`.
- **검증 소스·테스트 SHA: `49e87f019587320587ed0cd2843c8245a1cbd7ac`**.
- 소스 tree: `895c90433ab6c6f8fd39baac66808626543fbc9f`.
- 해당 tree의 소스 바이트로 전체 회귀와 브라우저 검사를 수행한 뒤 커밋했다. 이 보고서/증거 추가 커밋은 구현을 변경하지 않는다.
- 최종 제출 HEAD는 이 ROUND2/증거를 추가한 커밋이다. 자기 SHA를 본문에 넣으면 SHA가 바뀌므로 `git log -1 --format=%H -- docs/parallel-expansion-20261029/C3/ROUND2.md`로 확인한다. 최종 채팅에 실제 40자리 HEAD, 원격 일치 및 최종 HEAD CI를 보고한다.
- 시작 시 원격 main은 `5c1ffe3ba3c070e67e143d39b65650cc8dba5f2e`였다. 조사만 했으며 rebase/reset/통합하지 않았다. C3의 공용 코드 기반은 기존 `f469155c2b0c505f3e472e878f75029d7b8d39df` 그대로다.

## 해결한 결함

| 위치 | 변경·검증 |
| --- | --- |
| `c1_adapter.js` | 실제 C1 `sources[slot]`와 observation `data`를 소비한다. `sources.display` 요구 제거. stream epoch와 sensor epoch를 분리하고 map generation을 확인한다. 실제 D2 `center/extent`를 미터 geometry로 변환하고 구조화 provenance를 보존한다. |
| 같은 파일 | canonical `{host_clock_id,start_monotonic_ns,end_monotonic_ns}` 처리. 서버 receipt/received age와 명시적인 transport elapsed만 사용한다. 브라우저와 서버 monotonic 시각을 서로 빼지 않는다. 정수 ns는 JSON 토큰 단계에서 정확한 문자열로 보존하고 이미 반올림된 unsafe Number는 차단한다. wire 버전은 **C1 0.1** 그대로다. |
| `consumer.js` | 반복 snapshot의 동일 scene sequence에서도 서버 만료/부재를 반영한다. frozen source stamp의 TTL을 재시작하지 않는다. 서버가 무효화한 평가 sequence를 기억해 늦은 HTTP 응답이 되살리지 못한다. generation 변경 시 캐시/경로/상태를 비운다. |
| 같은 파일 | 불변 slot revision별 geometry 재사용. 고정된 slot별 캐시와 기존 queue/history 제한 유지. 유효한 D2 객체가 단지 표시용 cloud 부재 때문에 사라지지 않는다. 제공된 불량 cloud가 객체 처리 중 예외를 일으키지 않는다. |
| `index.js`, `draw.js` | SOURCE MODE와 evidence 종류를 분리한다. 입력으로 제공된 sensor origin을 표시한다. clearance·coverage·protection·recommendation을 따로 표시한다. 활성 평가의 부재에는 마지막 ACTIVE_CONSTRAINT/HOLD 상태를 남기고 reported downgrade는 명시한다. |
| 실험 host/runner | 기존 fixture를 유지하면서 실제 C1 offline app 모드를 추가했다. 이 모드에는 fixture replay 버튼과 가짜 reference cloud가 없다. D2/D3/C1 코드를 복제하지 않고 외부 정확한 Git blob을 검증·import한다. |
| C3 tests | canonical 11개 회귀, 실제 HTTP 6개 시나리오 및 frozen-time 검사 추가. 기존 consumer 16개와 fixture browser 11개 유지. bootstrap 전용 선택 검사는 더 강한 실제 HTTP suite로 대체했으며 기존 증거는 보존했다. |

내부 display profile은 기존 C3 구현을 유지하기 위한 내부 형식이며 새 공통 wire v1이 아니다. C1 validator가 canonical schema를 소유한다. 누락된 데이터는 생성하지 않는다.

## 정확한 읽기 전용 의존성

| 역할 | SHA | 이번 사용 |
| --- | --- | --- |
| C1 | `54629c793ad4ae0ea88127f00ed1b7f8805fc4e2` | 실제 contracts / offline `create_test_host` / router / SceneSnapshotService. 10개 Git blob 일치 검증. |
| D2 | `c0d266e290a2d29c173d3b83520f8c96efea9447` | 실제 `process_lidar` → `Tracker.step` → ObstacleFrame. 3개 blob 일치. |
| D3 | `09b68b692fa4b7ccdea39b1a16e3ff150794e12d` | 실제 `assess` 및 geometry core. D2 객체를 그대로 입력. 5개 blob 일치. |
| C2 | `5eed1a9959ca25a4f30bd5b5712806a5ad660c51` | 읽기 전용 export에서 최신 호환성 20개 확인 후 동결. |
| D1 | `cbedd05ba6f97dad5506e8003302f689ed8fcb4c` | C2가 이 SHA의 실제 정합→review→export→reload를 검증한 제출 증거 확인. 이번 C3에서 solver 재실행하지 않음. |
| C4 | `b9d700d754f0d3d43b9afdcffcb86e9deb7b1020` | `c1_ports.py`/인계의 projection 경계를 읽기만 함. runtime/ROS 미실행. |

D1/C2의 이미 확인한 정합·저장을 다시 구현하거나 튜닝하지 않았다. 이번 실행 순서는 raw synthetic points → D2 → D3 → C1 → C3였다. 다른 역할 checkout/index/브랜치는 변경하지 않았다. 읽기 전용 export는 `/tmp/c3-round2-deps`, C2는 `/tmp/c3-c2-frozen`에 있다. C1의 공용 `pcd_editing`, D2의 `relocalization/experimental_se3.py` 의존성은 C3 공용 기반과 해당 역할 SHA 사이에 차이가 없음을 확인했다.

## 계약 불일치를 숨기지 않은 실제 연결

실제 D3 raw 출력은 C1 `CollisionAssessment.from_dict`에서 다음 오류로 **실패한다**:

> validity interval requires explicit host clock and monotonic bounds

D3는 `{clock_domain,from_ns,until_ns}`를 출력한다. 실제 C1은 `{host_clock_id,start_monotonic_ns,end_monotonic_ns}`를 요구한다. 역할 문서 표의 C1 `clock_domain` 표기보다 실제 게시 코드를 우선했다. 현재 D3에는 `NEAR` enum 또는 `coverage.complete_for_motion` 필드도 없으며 `coverage="COMPLETE_SYNTHETIC"` 인자가 있다.

C3 소유 **테스트 runner에서만** 다음 변환을 명시했다.

1. source/host가 같다고 선언한 합성 clock correspondence를 assert한다. 2^53을 넘는 `9007199254740993` ns를 사용한다.
2. 원본 D3 interval을 `freshness.original_validity_interval`에 보존하고 C1의 정수 host interval을 생성한다. clock domain/epoch/원래 receipt/시작·끝 시각은 바뀌지 않는다.
3. C1 snapshot이 정확히 비교하는 obstacle reference를 `{source_epoch,sequence}`로 투영한다. 전체 원본 D3 출력은 증거에 보존한다.
4. 실제 C1 validator/ingest/snapshot을 실행하고 인증된 HTTP GET 응답을 실제 C3 adapter/consumer/overlay에 전달한다.

이는 실제 호스트 간 시계 대응 또는 운영 production converter 검증이 아니다. raw 실패를 EXPECTED_CONTRACT_FAILURE로 기록하는 검사가 별도로 있으며, 이를 직접 호환 PASS로 합산하지 않는다. 공용 validator나 CI 기준은 변경하지 않았다.

| 시나리오명 | 실제 D3 출력 | 화면/증거 |
| --- | --- | --- |
| PREDICTED_CONTACT | STOP_REQUIRED / PREDICTED_COLLISION, -0.252 m | 모델 예측 접촉 표시; 물리 접촉 확인 아님 |
| NEAR | UNKNOWN / UNKNOWN, +0.012 m | NEAR는 합성 시나리오명이라고 명시. producer에 없는 risk enum을 만들지 않음 |
| UNKNOWN_PARTIAL | UNKNOWN, +1.572 m | SPARSE와 ADVISORY_ONLY를 분리 표시 |
| SCOPED_SYNTHETIC_CLEAR | CLEAR, +1.572 m | 명시한 합성 body box·제공된 경로 범위의 COMPLETE_SYNTHETIC만 사용 |
| ACTIVE_UNKNOWN | UNKNOWN, +1.572 m | ACTIVE_CONSTRAINT / HOLD_FOR_VALID_INPUT 유지 |
| EXPIRED | core 원본 UNKNOWN; 서버는 assessment null | C1 `REFERENCE_OR_VALIDITY_UNKNOWN`, pose/객체/costmap stale |

D3 collision model은 합성 body box이다. 화면의 기존 공식 Go2 URDF asset·12개 관절 시각화와 동일한 충돌 모델이라고 주장하지 않는다. m/map 축을 공유하되, 실측 foot/body 충돌 정확도·센서 보정은 검증하지 않았다.

C1의 generic pose/path/costmap `data` 하위 geometry 스키마는 이 SHA에서 미정의다. 테스트 host가 합성 pose/joints/path/costmap을 명시적으로 제공하며 UI는 그대로 사용한다. LiDAR 점 8개와 origin `[0.08,0,0.4]`는 실제 D2 입력을 거쳐 `input_sources`로 보존된다. 실제 센서 취득·실제 Nav2 plan/costmap은 아니다. local trajectory·merged reference cloud·D3 drawable envelope는 UNAVAILABLE다. 선택한 map ID/revision/generation은 합성 신원 검증이며 실제 D1 merged 산출물 연결로 승격하지 않는다.

C1에는 16 KiB/sample, latest 합계 80 KiB, wire 128 KiB 제한이 있으며 현재 bulk resolver 계약이 없다. 임의 bulk URL을 받거나 매 프레임 대형 geometry를 파싱하지 않는다. 제한을 늘려 호환성 문제를 우회하지 않았다.

## 실행 결과와 증거

환경: Python 3.12.3, Node 24.22.1(공용 JS 회귀), Node 18.19.1(C3 직접 unit 실행도 통과), Playwright 1.62.1, Chromium 151.0.7922.34. Python package 목록은 evidence에 있다.

| 검사 | 결과 | 증거 등급 |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -v` | **3117 run / 3115 PASS / 2 SKIP / 0 FAIL**, 104.479 s | 전체 로컬 회귀. 선택 SVG/rosbags 의존성만 SKIP |
| Node 24 `node --test tests/*.mjs` | **699 PASS**, 0 SKIP/FAIL | 기존 공용 JS 전체 |
| Node 24 `node scripts/check_frontend_syntax.mjs` | **116 modules PASS** | 정적 검사 |
| `node tests/expansion_c3/test_consumer.mjs` | **16 PASS** | 기존 fixture/unit |
| `node tests/expansion_c3/test_canonical.mjs` | **11 PASS** | canonical guards/unit; 실제 생산자 실행과 구분 |
| `actual_service.py` → `actual_browser.mjs` | **6 HTTP/화면 cases PASS + frozen source PASS** | 실제 D2/D3/C1 core·실제 loopback HTTP·실제 Chromium, 입력은 SYNTHETIC |
| `tests/expansion_c3/browser.mjs` | **11 PASS**, 1200 packets @ **38.23 Hz**, retained 1, pending ≤1, history ≤3, post-GC +216752 B | 기존 UI fixture/stress/lifecycle; 실제 센서 성능 아님 |
| 갱신한 `c1_compatibility.py` → `check_c1.mjs` | **PASS**, 실제 endpoint response 재검증, 객체 1 / STOP_REQUIRED | 실제 pinned C1 DTO + C3 consumer |
| C2 읽기 전용 contract/ports/exact | **17 + 2 + 1 = 20 PASS** | 마지막 1개는 실제 pinned C1 FusionRequest validator. HTTP callback 검사는 MOCK; 기존 정합/저장 재실행 아님 |
| 실제 merged-map / native 입력 기록 | **INPUT_REQUIRED** | 실제 산출물/기록 미제공 |
| ROS, native Nav2/avoidance, 실장비, 배포 | **NOT_RUN** | 요청된 금지 범위 유지 |

초기 sandbox 전체 회귀는 첫 기존 async endurance에서 진행되지 않아 중단했다(exit 130). 동일 명령을 허용된 로컬 실행 환경에서 재실행하여 위 결과를 얻었다. C2 Python 자식 프로세스 검사도 같은 환경 제한을 해소한 뒤 PASS했다. 공유 syntax runner는 Node 18에서 실패하여 기존 검증 환경인 Node 24로 실행했다. 테스트 삭제·skip 추가·임계값 완화로 해결하지 않았다.

실제 HTTP suite는 무인증 401과 인증 200을 각각 확인한다. 브라우저 요청 **94개 모두 GET·loopback**, page error 0. 추가 API probe 12개도 GET이다. 같은 scene sequence `5`에서 9회 재수신해도 pose/obstacle은 STALE가 됐고 normalized geometry copy는 **7회**로 유지됐다. pause는 표시만 동결하며 PAUSED 표기를 유지한다.

- [전체 증거/파일 hash manifest](evidence/round2/manifest.json)
- [원본 D2/D3/C1 실행 결과 및 직접 계약 실패](evidence/round2/core-results.json)
- [HTTP fingerprint ↔ 표시 상태 ↔ screenshot 결과](evidence/round2/actual-browser-results.json)
- [PREDICTED_CONTACT 화면](evidence/round2/PREDICTED_CONTACT.png)
- [UNKNOWN + 양의 clearance 화면](evidence/round2/UNKNOWN_PARTIAL.png)
- [동일 원본 시간 반복 수신 후 STALE 화면](evidence/round2/FROZEN_SOURCE_STALE.png)
- [기존 fixture browser 결과](evidence/round2/fixture-browser-results.json)

대표 endpoint 원문 SHA-256:
`99f3639d240dcb933a52ba3d5791de5549d9d0f4bcd9b990101fbb6213874ddd`
([10,578-byte 원문](evidence/round2/PREDICTED_CONTACT.http-body.json)). 게시한 `.http-body.json`은 runner가 가독성을 위해 붙인 마지막 개행만 제거하고 실제 HTTP 원문 hash와 일치함을 검증했다. 모든 시나리오 원문 hash는 manifest/browser 결과에 있다. 큰 trace는 `/tmp/c3-round2-fixture-results/browser-trace.zip`에만 보관했다.

재현 명령·export 준비는 [실험 README](../../../experiments/expansion_20261029/c3_scene_ui/README.md)의 Round 2 절에 있다. 실행 예:

```sh
python3 experiments/expansion_20261029/c3_scene_ui/actual_service.py --deps /tmp/c3-round2-deps --out /tmp/c3-round2-results --port 4184
C3_EVIDENCE=/tmp/c3-round2-results node tests/expansion_c3/actual_browser.mjs
C3_FIXTURE_URL=http://127.0.0.1:4184/experiments/expansion_20261029/c3_scene_ui/fixture.html C3_EVIDENCE=/tmp/c3-round2-fixture-results node tests/expansion_c3/browser.mjs
```

## 원격 CI와 경계

- 이전 제출 `92658b…`의 전체 [CI 40828616817](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40828616817): **SUCCESS** 확인. 과거 Goal URDF 실패를 현재 baseline 실패라고 주장하지 않았다.
- 검증 소스 `49e87f0…`의 전체 [CI 40839316098](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40839316098): **문서 확정 시 실행 중**. 이전 기준 실행은 환경별 16~21분이었다. 이 항목은 문서 확정 시점의 관측이며 최종 완료 결과는 아래 링크와 최종 채팅에서 확인한다.
- 소스 SHA와 문서/증거 최종 HEAD를 구분한다. 최종 HEAD의 CI 결과는 실제 원격 실행을 조회하여 최종 채팅에 기록한다.

수정은 C3 feature, C3 tests, C3 experiment, C3 docs 네 소유 경로에 한정했다. `app.py`, 공용 `app.js/scene3d.js/navigation.js`, Goal URDF, 운영 ROS/TF/controller, dependency/CI 파일은 수정하지 않았다. 제품 mount·main 통합·PR·배포·로봇 접속·실이동은 수행하지 않았다. 자신의 기존 브랜치에만 일반 push했다.

## 남은 한 가지

**생산자 소유의 canonical scene replay bundle을 정확한 SHA로 제공받는 것**: 검증된 source→host clock correspondence와 실제 merged-map·native/bulk 참조가 포함된 입력이 필요하다. 현재는 해당 입력이 없어 합성 변환·supplied payload의 실제 core/HTTP 연결까지만 검증했다. 다른 담당을 자동 감시하거나 기다리지 않으며, 임의 데이터·기준 완화로 이 공백을 채우지 않았다.
