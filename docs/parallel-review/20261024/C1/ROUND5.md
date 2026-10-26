# C1 ROUND5 — 두 가지 RGB replay 목적 분리, 후보 동결

2026-10-26 KST. 브랜치 `review/20261024-c1-integration-r2`.
실제 시작 local/remote HEAD `c052db127f2952b693971642f0a33c8efcb43098`, clean 독립 clone.
기능 검사 SHA **3a3a45e8f57bb6f048e66f5c994e08049558c894**. 문서 포함 제출 SHA는 최종 응답에 별도로 기록한다.
상태 **READY_FOR_READONLY_DEVICE_REVIEW**. 실장비/실시간 인식/이동 승인과 별개인 읽기 전용 후보다.

## 이번에 닫은 문제와 보존 범위

기존 `_drive`는 각 입력의 추론과 PNG encode가 끝난 뒤에만 다음 입력을 읽었다.
ROUND4의 마지막 `queue_residence_s=220.430113`은 기록 schedule에서 처리까지의 누적
지연이며, 메모리에 220초의 FIFO가 쌓였다는 측정이 아니었다. 이전 증거를 수정하거나
새 측정으로 대체하지 않는다.

기존 CLI와 viewer에 `exhaustive` / `latest-wall-clock`을 구분했다.

- **exhaustive**: 기본값, 모든 이미지 분석·게시를 보존. 기본 clock은 기존 `wall-clock`.
  원래 기록 offset을 host anchor에 대응시키고 밀려도 최초 receipt를 갱신하지 않는다.
  명시적 `--replay-clock source-timeline`은 fixture 시간 평가다. 원래 offset/stamp/간격을
  유지하며 처리 wall time은 따로 기록한다. 이 경우 wall-clock 예정 arrival/lag는 null이다.
- **latest-wall-clock**: 원래 재생 시계에 따라 진행한다. 새 입력이 이미 due이면 오래된
  미디코딩 입력을 건너뛴다. 디코딩 중 더 최신 입력이 due가 되면 그 디코딩 결과도 drop한다.
  feeder는 매 추론/encode 완료를 기다리지 않는다. 입력 끝에서만 bounded worker/display를
  drain한다. source-timeline과의 혼용은 CLI에서 거부한다.

C4 `iter_frames`의 체크섬/이미지 decoder를 재사용했다. 선택한 원래 입력 index와
기록 offset 기반 fixture stamp, 같은 replay epoch를 유지한다. 건너뛴 seq를 압축하지 않는다.
실제 hardware metadata는 원래 Frame metadata에 남고, fixture 시계를 hardware 시계로
승격하지 않는다. 원본 파일·기록 metadata·최초 receipt는 poll/reload/encode 때 갱신하지 않는다.

실행 thread는 decode 1 + 기존 TrafficWorker inference 1 + encode 1로 고정된다.
기존 worker는 실행 1 + latest pending 1을 그대로 유지한다. 결과 consumer도 실행 encode 1
+ pending 결과 1이다. 이미지 쌍 2개, trace 64개, 각 stage 분위수 window 256개로 제한한다.
기존 입력 목록 외에 전체 frame/image/metadata history를 추가하지 않는다.

Worker에는 선택적인 동기식 결과 sink와 enqueue/start/completion 측정만 추가했다.
기본 호출자는 그대로 동작한다. viewer sink는 읽기 전용 결과 전달이며 mission callback이
아니다. stop/close는 feeder/consumer/pending을 취소·회수하고 이미 실행 중인 추론/encode의
늦은 결과는 버린다. 실제 종료 전까지 중단할 수 없는 thread를 강제로 죽이지 않는다.

기존 C2 시간·inference-settings binding, first receipt, 1,200관측, durable effect,
STOP 선점, main/L1 채택분은 재구현하지 않았다. TTL .25초/안정성 .4초/권한 기준은 그대로다.
새 classifier, 신호 미션, planner/controller, 카메라 소유자 또는 장비 capability는 없다.

## 시간·계수와 화면

한 host monotonic domain에서 아래를 분리한다.

- 기록 offset/fixture stamp와 원래 계획한 arrival.
- decode 시작·완료, worker enqueue·실제 processing 시작.
- OwnerModel `infer` 호출 시작·완료(전후 처리 포함, GPU kernel 단독 시간이 아님), pipeline 완료.
- encode 시작·완료와 서버 게시. 브라우저 paint/network 시간으로 주장하지 않는다.
- `worker_pending_s`는 enqueue→processing, `schedule_to_processing_s`는 예정 arrival→processing.
  구 key `queue_residence_s`는 C4의 기존 schedule→processing 의미로 보존하며 FIFO 길이가 아니다.
- input/decoded/offered/processed, decode 전·후 drop, pending 교체, 표시 교체, invalid,
  late result/encode를 구분한다. 계수는 단계별이며 invalid는 processed와 겹칠 수 있다.

평균/max는 해당 stage 전체 관측, p50/p95는 최근 최대 256개의 nearest-rank 값이다.
이번 실제 비교는 각 30개여서 모든 표본을 포함한다. 원본/overlay는 동일 run/sequence의
두 이미지가 모두 로드됐을 때 함께 교체한다. 늦은 이미지 응답이 서로 다른 프레임 쌍을
만들지 않으며, browser refresh도 한 번에 하나만 실행한다. 이전 화면의 pre 높이 제한이
추가 시간 항목을 가리지 않도록 해당 inspector 안에서만 해제했다.

모든 화면에 replay/LIVE 아님, stage/raw/stable/UNKNOWN, profile/hash, drop/coverage,
실제 pending과 schedule lag를 표시한다. feet/physical STOP/path/departure는 null,
출발 권한 false다. C4 false GREEN 이력은 유지한다.

## 현재 역할 결과 재확인

| 역할 | 확인한 원격 HEAD | 처리 |
|---|---|---|
| C1 | `c052db127f2952b693971642f0a33c8efcb43098` | 기준과 동일, 사용자 변경 없음 |
| C2 | `2f85adbb19da9c0ace02e561e54474cbf57b7c9b` | `0dd534f` binding은 이미 채택, 변경 없음 |
| C4 | `bf0436687a0a9dbab1ff7ac370f1bc0de42d07ad` | 실패 emitter 보고서/데이터 요청 참조. 구현 미채택, OFF 유지, 기존 full640 hash 보존 |
| C3 | `d253ee090a5f5c145c3842ed2cc0105d7d95fea3` | A/B 모두 실패한 isolated 후보. production 채택·native 재실행 없음 |
| D0 | `da7230bb65722e4a1d3f4ab0c1d16e63fcd344e3` | 기존 공통 입력/증거 pin 보존, 옛 missing-signals 요청 재등록 없음 |
| main / L1 | `104692fa0070ef085eee918913ea05fdb2d88c05` / `5339e3b5c9906991e08766b61bd27d92e725aa6f` | 기존 채택분 유지 |

C3 [A run 40167720216](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40167720216),
source `20d7f56f24cff768e716a56813250ebbd3c2c234`와
[B run 40168963222](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40168963222),
source `2a1b1f172f30d010fa33d9b7f247a9163f175e82`의 terminal FAILURE를 재확인했다.
A는 목표 실패, B는 목표와 once-padded footprint 안전 검사 모두 실패다. C3의
costmap/footprint 후속 수정 대기가 RGB 후보를 막지 않는다. 옛 시간·초기 통합 요청도 다시 열지 않는다.

[ROUND5_EVIDENCE.json](ROUND5_EVIDENCE.json)은 이번 소스 hash와 작은 비민감 측정만 포함한다.
ROUND4 index와 기존 runtime revision/원본 자료는 그대로이며, 옛 검사가 새 worker 코드를
검사했다는 주장은 하지 않는다. 새 전역 runtime manifest gate를 추가하지 않았다.

## 검사와 실제 저장 RGB 비교

느린 합성 detector를 막아 둔 동안 latest feeder가 입력 끝에 도달하고, inference 해제 후
첫 결과와 마지막 seq 7만 처리하는 회귀가 통과했다. 같은 조건에서 exhaustive는 첫 입력에서
대기 후 8개 모두 처리했다. 느린 decoder의 decode 전/후 drop, 느린 encoder와 bounded 결과
교체, 동일 이미지의 새 seq 처리, 실제 packet 재전송 시 추론 재사용 금지, 미검증 source clock,
설정 변경, TTL 초과, stop/close 뒤 late result 폐기를 실제 C4 pipeline/worker로 검사했다.

| 검사 | 이번 결과 |
|---|---|
| 새 replay 회귀 | 11 PASS, 1.297초 |
| C1 integration 전체 | 56 PASS, 11.663초 |
| 기존 dedicated competition browser | 10 PASS, 39.3초; 동일 source 이미지 쌍/reload/시간 표시와 기존 STOP/미션 포함 |
| 필수 전체 Python | 2,963 실행: 2,961 PASS / 2 SKIP, 96.472초 |
| JS / common browser | JS 666 PASS; common browser 중단(exit143), 남은 파일 15 PASS, 26.5초; 전체 결과는 source CI 참조 |
| Ruff / mypy / syntax / secret scan / diff check | PASS; mypy 4파일, syntax 108모듈 |

공통 browser 최초 실행은 186/198 진행 표시에 SIGTERM(exit143)으로 종료됐다.
assertion 실패 출력은 없었으나 전체 PASS로 세지 않는다. 고아로 남은 C1 static fixture는
정확한 PID/cwd/명령을 확인하고 그 프로세스만 종료했다. 중단 파일 `ui_density` 및
남은 `ui_reported_fixes`/`ui_workspaces`만 별도 출력 경로로 재개했다. 원래 로그는 보존했다.

기존 private 자료의 **앞 30장, 원래 offset 0..6.8초**를 각각 한 번만 사용했다.
exhaustive 완료·서버 종료 후 latest를 실행했고 부하 비교·전체 검사·빌드를 동시에 실행하지
않았다. 첫 model 호출도 통계에 포함했다. 기존 C4 CPU 환경, 같은 owner 모델 SHA
`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`, full640 설정 SHA
`f237ce7aea41a89a6dfaf228b206631a15c465857868c2830bd1bc4f470f56ec`다.
새 모델/자료 다운로드, 촬영, emitter/threshold/재생 간격 변경은 없다.
30행 모두 source_clock_verified=false이고 실제 source_stamp_ns는 제공되지 않았다.
화면 stamp는 명시적인 fixture offset 기반 값이며 원본 hardware stamp를 복원한 것이 아니다.
원본 hardware timestamp 검사는 INPUT_REQUIRED로 남긴다.

두 모드 모두 COMPLETE, input/decoded/offered/processed/published **30**, coverage **100%**,
decode 전·후 drop/pending 교체/표시 교체/invalid/late **0**. 같은 raw bbox RED15/AMBIGUOUS1,
마지막 stable UNKNOWN, 권한 0이다. RGB 원본과 overlay 및 완료 후 reload 불변을 실제 browser에서
확인했다. UI pre 높이 보정은 이 측정 이후 합성 E2E에서 확인했으며 추론을 반복하지 않았다.

단위 ms, 각 셀은 **평균 / p50 / p95**:

| stage | exhaustive wall-clock | latest-wall-clock |
|---|---:|---:|
| decode | 2.723 / 2.527 / 3.924 | 3.012 / 2.647 / 4.780 |
| 실제 worker pending | .038 / .033 / .046 | .085 / .047 / .164 |
| infer 호출 | 27.908 / 25.127 / 27.038 | 38.523 / 26.012 / 104.224 |
| 전체 pipeline | 30.973 / 25.735 / 27.816 | 41.899 / 26.635 / 151.217 |
| PNG encode | 50.867 / 49.658 / 55.599 | 52.522 / 50.525 / 57.991 |
| schedule→processing | 5.127 / 3.530 / 4.852 | 4.081 / 3.949 / 6.453 |
| schedule→서버 게시 | 87.350 / 79.639 / 122.679 | 99.771 / 84.128 / 217.857 |

이번 private 부하는 두 모드 모두 처리 용량 안이므로 **실제 자료에서 최신 모드의 속도 개선이나
과부하 drop을 입증하지 않았다**. 과부하 구조는 합성 회귀로 확인했다. 이 측정은 ROUND4의
255장/다른 host 부하와 동등 비교가 아니며 온보드 latency, 전체 255장 재평가, 정확도나 실제
stable GREEN PASS가 아니다. GREEN 전환 구간이 없는 이 30장으로 인식 성능을 승인하지 않는다.

실제 screenshot/trace/실행 로그는 clone 밖 private work 경로에만 보존한다. Git과 public
CI artifact에는 원본 RGB·사적 경로·source URL이 없다. 기존 CI는 생성 합성 입력만 실행한다.
첫 exhaustive 실행의 Ultralytics 설정은 디렉터리 미생성으로 `/tmp/Ultralytics` fallback을
사용했고 이후 명시적인 private 설정 디렉터리를 생성했다. 장비/기존 owner config는 변경하지 않았다.

## 실행 예시와 원격 CI

기존 환경에서 프로젝트 루트 기준:

```bash
PYTHONPATH=.:tests python3 tests/competition_fixture_server.py --synthetic-rgb-review \
  --replay-mode latest-wall-clock
# http://127.0.0.1:4187/?rgb_review=1#missions

# 모든 이미지의 fixture source-timeline 평가: wall 부하 재생이 아님
PYTHONPATH=.:tests python3 tests/competition_fixture_server.py --synthetic-rgb-review \
  --replay-mode exhaustive --replay-clock source-timeline

# private 실제 자료: 기존 JSONL/config/model을 CLI로만 선택, public CI에서 거부
PYTHONPATH=.:tests python3 tests/competition_fixture_server.py \
  --private-replay-manifest /private/existing/frames.jsonl \
  --replay-config /private/existing/config.json --replay-model /private/existing/model.pt \
  --acknowledge-trusted-pickle --replay-max-frames 30 --replay-fps 5 \
  --replay-mode latest-wall-clock
# exhaustive 비교는 위 서버 종료 후 --replay-mode exhaustive로 별도 실행
```

HTTP는 source/model 입력이나 시작 명령을 받지 않는다. loopback/same-origin/no-store와
private 입력 CI 금지 정책을 보존했다. browser reload는 새 run/추론을 시작하지 않는다.

원격 기능 CI: [run 40261918104](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40261918104),
source `3a3a45e8f57bb6f048e66f5c994e08049558c894`: **SUCCESS**, 세 job 모두 성공.
전용 통합 job은 C2 117/C4 81/C1 56/registry 2, D0 136+30+44+13+11, C3 58 PASS다. 문서 전용 제출 HEAD와 실제 검사 source SHA를 구분한다.
두 OS 모두 Python 2,963개(2,961 PASS/2 SKIP), JS 666개, common browser **198개**,
전용 competition E2E **10개**가 통과했다. Ubuntu22/Python3.10은 Python 165.656초,
browser 12.8분/전용52.5초, Ubuntu24/Python3.12는 Python165.769초,
browser11.9분/전용50.9초다. 두 skip은 기존 optional plotting/rosbags이며 C1 교차 검사는 skip하지 않았다.
[Ubuntu22 artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40261918104/artifacts/12625366702),
[Ubuntu24 artifact](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40261918104/artifacts/12625282735)를
내려받아 생성 RGB 화면과 소프트웨어 미션 SUCCEEDED/physical_motion=false trace를 확인했다.
private RGB 파일은 포함하지 않았다. 원격 전체 PASS를 로컬 중단 실행의 결과로 소급하지 않는다.

코드 검사 완료 후 이 문서만 `[skip ci]` 제출하여 동일 전체 검사를 반복하지 않는다.
문서 전용 HEAD 자체에 CI가 PASS했다고 주장하지 않으며 기능 파일은 위 source SHA와 동일하다.
새 native 실행/장비 관측/카메라 인수/실이동은 NOT_RUN이다.

## 남은 한 가지 — 한 번의 정지 관측 자료

[ROUND4 승인 요청안](ROUND4.md#다음-장비-작업-승인-요청안--관측만-실행하지-않음)의
workstation 분리/private 보관/장비 파일·서비스 무변경/구독 종료 복구 원칙을 재사용한다.
이번에는 C4의 [원본 자료 요청](https://github.com/Phjrab/robot-scope-ros2-dashboard/blob/bf0436687a0a9dbab1ff7ac370f1bc0de42d07ad/docs/mission-competition/traffic-input/EMITTER_DATA_REQUEST.md)과
맞춰 실제 RED→GREEN→RED 및 negative 구간이 있는 **약20~30초의 한 번의 정지 관측 창**을
제안한다. ROUND4의 10초/50장 제안에서 기간을 늘린 별도 승인안이며, 이번 소프트웨어 지시로
승인되거나 실행된 것이 아니다. 장비와 source는 별도 승인 때 특정한다.

이미 발행 중인 owner RGB·원래 metadata만 private 보관하고 새 camera acquisition·소유권·
설정 변경을 시작하지 않는다. source ID/epoch/seq/ns stamp/clock/최초 receipt/source age와
exposure/gain/settling은 제공값만 보존하고 미제공은 null이다. metadata가 부족해도 진단 표시는
가능하지만 mission 권한으로 연결하지 않는다. 원본 checksum과 recording 단위의 사람 검토를
함께 전달한다. 현재 독립 전환 자료는 **INPUT_REQUIRED**이며 기존 RGB 재생 검사를 막지 않는다.

따라서 남은 한 가지는 **별도 승인 후 이 한 묶음의 정지 관측 원본을 확보하는 것**이다.
main 병합·PR·로봇 접속·카메라 인수·서비스 변경·배포·ARM/goal·실이동은 수행하지 않았다.
최소 완료 이후 새 기능/튜닝/하네스를 추가하지 않고 후보를 동결한다.
