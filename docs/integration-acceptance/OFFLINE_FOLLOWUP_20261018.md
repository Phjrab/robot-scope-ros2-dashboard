# 로봇 전원 OFF 후속 작업 — 2026-10-18

## 범위와 소스

로컬 `main`의 `a79c67a9f9f303e3444367a1ce1f3f003a3c4d96`에서 기존 변경을
보존하고 Stop 표시, 지도 시점, 보정 실패 진단, 오프라인 SE3 실험을 마무리했다.
원격 main 조회·push·release는 하지 않았다. 이 문서를 포함하는 로컬 커밋이
이번 변경이며, private `validation-closeout.json`에 최종 커밋과 파일 해시를 남긴다.

이번에는 로봇 SSH·카메라·ROS·서비스·배포·TF·initialpose·goal·ARM·bridge·이동을
실행하지 않았다. 마지막 **과거 실기 기록**의 설치본은 `40276a5`, 2026-10-17
종료 상태는 IDLE/카메라 해제/bridge OFF였다. 오늘의 장치 상태로 재확인한
것이 아니다. 새 캡처와 카메라 pitch 조절도 수행하지 않았다.

## 구현 결과

| 항목 | 변경과 경계 |
| --- | --- |
| VSLAM Stop 표시 | 요청 중, 수락, 정리 중, 종료 미확인, 확인된 IDLE, 실제 정리 실패를 구분한다. POST 수락 뒤 GET timeout이 나도 수락 사실을 보존하며 자동 중복 Stop을 보내지 않는다. |
| 늦은 상태 응답 | session/generation/engine/epoch, request ID, 조회 순서를 비교한다. 잘못된 `{}` 응답으로 IDLE을 만들지 않는다. 서버 generation 감소는 `UNKNOWN / SESSION_GENERATION_RESET`으로 표시하고 페이지 재조회 전 명령을 막는다. |
| 정리 재시도 | 실패한 cleanup만 명시 재시도한다. 현재 STOPPING을 이전 `CLEANUP_REQUIRED` reason보다 우선하고, IDLE + `cleanup_required=false`를 확인한다. IDLE + true는 성공으로 처리하지 않는다. |
| 지도 시점 | 기존 전체 극값 FIT를 유지한다. 주요 영역 FIT는 표시점 최대 10,001개의 축별 2–98 percentile 범위를 사용하며, 50점 미만은 표시점 전체 범위를 사용한다. 서버가 제공한 전체 bounds와는 다를 수 있고, 의미상 벽/객체 분할이 아니다. |
| 카메라 중심 | 유효한 카메라 pose와 일치하는 frame/영상 보정 참조가 있을 때 현재 위치를 화면 중심으로 옮긴다. 줌·회전·따라가기 설정을 보존한다. 데이터/pose가 없으면 해당 버튼을 끈다. |
| 원본 보존 | FIT/중심 이동은 보기만 바꾼다. 점군 배열·전체 bounds·지도 export·정합 입력을 필터링하거나 수정하지 않는다. 전체 FIT로 원래 전체 범위를 복원한다. |
| 보정 진단 | 중심 1픽셀과 5×5 주변의 유효 수·비율, IQR/허용값, 불연속, 평면 잔차, 점별 거부 이유, 선택 분포를 구분한다. 실패해도 모든 샘플의 진단을 유지한다. |
| 보정 실패 경계 | API 422와 각도/분석 export 차단을 유지한다. 실패한 후보 평면의 잔차를 성공한 보정값으로 표시하지 않는다. 새 입력·늦은 응답·export 재계산 실패가 이전 결과를 복원하지 않는다. |

계산 알고리즘, 동기화·깊이·평면 품질 임계값, 최소점 수와 100점 상한은 그대로다.
정확히 6점을 선택하면 6점 모두 주변 검사와 평면 인라이어 기준을 통과해야 한다.
같은 벽의 가로·세로에 12–20개 점을 분산하고 경계·가림·반사를 피하도록 안내한다.
이 권고는 점을 더 선택하면 반드시 통과한다는 보장이 아니다. 결과는 여전히
RELATIVE_ONLY이며 본체 절대각이나 운영 변환에 적용하지 않는다.

## 보관 실측 샘플의 오프라인 재현

2026-10-17의 조절하지 않은 동일 각도 촬영
`0f301ed2870243e5bb0a6bac68dc5b94`, `c92c6700bc5a4125b9bf3d9408d5fe8e`를
원본 SHA256을 유지한 채 재사용했다. 실제 Python router/store와 기존 Settings
패널을 127.0.0.1에서 실행했다. 로컬 harness는 보관 샘플 GET과 분석 API만
제공하고 장비/시작/종료/제어 경로를 제공하지 않는다. 기존 ZIP의 각 파일
해시·크기를 확인한 사본으로 목록 → JSON/IR 가져오기 → 동일 좌표 선택 →
422 실패 진단 표시 → 각도 없음/분석 export 비활성화를 확인했다.

촬영 조건 checkbox는 과거 시험의 사용자 선언을 재현한 것이다. 실제 동일
평면 여부나 본체 수평을 인증하지 않으며, 이번 현장 조건 확인도 아니다.
화면은 10월 17일 보관 실측과 현재 장비 연결 없음으로 표시했다.

| 선택점 집합 | 샘플 1 | 샘플 2 |
| --- | --- | --- |
| 기존 6점: 주변 깊이 통과 | 1/6 | 5/6 |
| 근접 6점: 주변 깊이 통과 | 6/6 | 6/6 |
| 근접 6점: 후보 평면 인라이어 / 필요 | 4/6 | 4/6 |
| 근접 6점: 실패 후보 평면 최대 절대 잔차 | 0.868080 m | 0.879371 m |

기존 점은 `(300,85), (345,85), (390,85), (340,115), (365,140), (390,165)`;
근접 점은 `(300,86), (343,85), (390,85), (340,114), (363,138), (391,164)`다.
중심 픽셀과 5×5 유효 깊이 비율이 100%여도 깊이 불연속 또는 평면 합의에서
거부될 수 있다. 이 잔차는 독립 정답 대비 정확도나 카메라 캘리브레이션 오차가
아니다. 이번 실측 상대각 계산과 분석 JSON 내보내기는 품질 거부로 미완료다.
이전 원본 ZIP/compatibility JSON 수집·export 성공 기록은 그대로 보존한다.

## 오프라인 SE3 지도/query 실험

`scripts/inspect_se3_pair.py`는 기존 `evaluate_recorded_se3.qualified_inputs`,
합성 benchmark scene, `experimental_se3` solver/변환/거리 계산을 재사용한다.
새 정합 알고리즘, 전역 재위치추정 또는 운영 연결을 만들지 않았다. 입력
identity/hash/frame/metre 단위, 명시된 `T_target_source`, 고정 seed 1–5개를
기록한다. 원본을 변경하지 않고 seed 전후의 query→map overlap, gate 내 RMSE,
전체 query 최근접 거리 p50/p95와 XY/XZ/YZ 도표를 저장한다. 매번 새 private
출력 디렉터리가 필요하며 덮어쓰지 않는다.

```sh
python3 scripts/inspect_se3_pair.py --synthetic-demo --plots --output-dir /private/path/new-demo
python3 scripts/inspect_se3_pair.py --manifest /private/path/qualified-input.json --plots --output-dir /private/path/new-recorded
```

`--plots`에는 선택 의존성 matplotlib이 필요하다. 저장소 필수 의존성은 변경하지
않았다. 이번 합성 데이터는 같은 장면에서 파생한 두 배열이고 독립 실측이 아니다.
각 1,588점, 변경하지 않은 correspondence gate 0.75 m로 다음을 기록했다.

| Seed | query→map overlap 전/후 | gate 내 RMSE 전/후 (m) | solver 판정 |
| --- | --- | --- | --- |
| 항등 변환 | 1.000 / 1.000 | 0.262619 / 0.075295 | REJECTED / HIGH_RESIDUAL |
| 고정 합성 근접 prior | 1.000 / 1.000 | 0.148339 / 1.68e-8 | CANDIDATE |
| (20,20,20) m | 0.000 / 0.000 | null / null | REJECTED / LOW_OVERLAP |

도표는 전후 동일 축과 모든 제한된 입력점을 사용하고 SYNTHETIC 및 운영 미수행을
표시한다. CANDIDATE는 실제 재위치추정 성공이 아니다. 독립 정답/절대 오차는 null,
global relocalization과 operational application은 NOT_RUN이다.

기존 실측 `run-20261014T041650Z/recorded-input-unqualified.json`은 기존 gate에서
`BLOCKED: unqualified provenance: calibration_verified`로 종료했다. 그 기록에는
clock/frame 연결/독립 수집/map-family·revision/seed도 미확인으로 남아 있다.
동일 `camera_init` 이름만으로 세션 간 원점을 같다고 볼 수 없다. 실측을 합성으로
대체하거나 calibration/seed를 추정해 적격 입력으로 이름 바꾸지 않았다.
다음 실측 실험에는 독립 reference/query의 해시·세션·map family/revision, 실제
calibration/config hash, clock/frame 연결 근거, 한 번만 registration한 query와
정답을 사용하지 않은 근사 seed가 필요하다.

## 검증 결과와 증거

| 검증 | 결과 |
| --- | --- |
| 기존 프로젝트 `.venv` 전체 Python | 2,275개, OK (skip 3) |
| 전체 JavaScript | 452 PASS |
| 전체 브라우저 첫 실행 | 150개 중 136 PASS, 14 fixture 실패 |
| 실패 14개 수정 후 관련 재실행 | 14/14 PASS; 고유 150개 모두 통과, 전체 실행을 반복하지 않음 |
| 지도 캡처 추가 확인 | 1 PASS, 합성 데이터 |
| 이전 `a79c67a` UI 비교 캡처 | 3 PASS, 합성 fixture를 이전 동작에 맞춘 private harness |
| 선택 matplotlib plot 검사 | 기존 설치된 시스템 Python으로 1 PASS, 합성 데이터 |
| 정적 검사 | ruff, 저장소 기본 mypy 4개 모듈, JS 86개 구문, source secret scan, diff 검사 PASS |
| 보관 실측 로컬 UI | 위 2개 샘플 import/선택/422 진단/각도·export 차단 확인 |

처음 시스템 Python으로 실행한 전체 검사는 FastAPI/YAML 등 의존성 누락으로
실패했다. 이를 통과로 세지 않고, 의존성이 갖춰진 기존 `.venv`로 바로잡은
전체 결과를 사용한다. skip은 선택 rosbags 미설치, Linux /proc 전용 검사,
venv 내 선택 matplotlib 미설치다. 마지막 항목은 별도 plot 검사로 보완했다.
변경 보정 모듈을 확장 대상으로 삼은 mypy 시도는 Python 3.13 NumPy stub와
target 3.10 충돌로 미완료였고, 표의 mypy는 저장소가 지정한 4개 모듈 범위다.

브라우저 실패 원인은 테스트 응답의 top-level `generation`과 카메라 정합용
`overlay.image` 참조 누락이었다. fixture만 실제 계약에 맞췄고 제품 gate를
완화하지 않았다. 전체 브라우저를 중복 실행하지 않았으며 이후 제품 코드는
바뀌지 않았다. localhost 바인딩 EPERM으로 0개 실행된 별도 시도도 통과 수에
포함하지 않는다. GitHub CI를 새로 실행하거나 원격 CI 결과를 조회하지 않았다.

지도 전후 자료는 같은 합성 점군을 사용하지만, 이전 source 캡처에는 시험용
영상 보정 참조가 빠져 카메라 시야도 보이지 않는다. 이후 캡처는 fixture 참조와
viewport를 보완했다. 카메라 시야 출현을 이번 제품 수정의 효과로 세지 않는다.
FIT 효과의 직접 비교는 현재 source/같은 fixture의 `captured-map-targeted/` 두
이미지로 한다. Stop·보정 캡처 역시 합성 fixture이며 실제 장비 화면이 아니다.

Private 증거 루트는 `robot-scope-hardware-validation-private/offline-followup-20261018/`다.
원본·이미지·점군·trace는 Git에 포함하지 않는다.

- `python-full-venv.log`, `javascript-full.log`, `browser-full.log`,
  `browser-map-targeted-run.log`, `browser-map-capture.log`, `python-optional-plot.log`
- `screenshots-before/`: 이전 source의 Stop timeout/FIT/실패 진단 화면
- `screenshots-after/`: Stop 수락 후 미확인/IDLE, 합성 보정 실패 진단,
  `mount-actual-diagnostics.png` 실제 보관 샘플 진단
- `captured-map-targeted/`: 현재 source의 전체 FIT와 주요 영역 FIT 비교
- `local-estimate-input.json`, `local-estimate-response.json`, `local-api-events.jsonl`,
  `local-ui-observation.json`: 실제 로컬 브라우저 POST와 422 응답/표시 상태
- `se3-synthetic/`: 배열·manifest·report·seed별 SVG,
  `se3-recorded-qualification/report.json`: 실측 적격성 차단
- 별도 `mount-settings-20261017/offline-20261018/`: 이전/이후 진단 JSON과 재현 script

## 남은 현장 확인과 다음 최소 작업

벽 중복과 궤적 점프의 원인은 아직 미확인이다. 관측을 재개할 때 동일
session/generation/map epoch/frame/source timestamp를 묶어 (1) native pose/map,
(2) server 직렬화·WebSocket frame, (3) browser가 해석한 좌표와 view transform을
각각 보존·비교해야 한다. native에서 이미 겹치는지, transport의 좌표/시간/세대가
바뀌는지, 표시 단계에서만 달라지는지를 구분한다. 비교 원본과 해시는 불변으로
유지하고 display-only FIT를 geometry 수정이나 calibration 해결로 보고하지 않는다.

향후 별도 허용을 받은 배포 후 가장 작은 검증은 정지 세션의 Stop 수락 →
서버 IDLE → 실제 camera owner 해제 확인, 같은 지도에서 FIT 전환 시 원본
geometry/export 불변 확인이다. 보정은 가까운 가림 없는 벽의 정지 반복 촬영에서
평면 품질부터 확인하고, 카메라를 해제한 사이에만 사용자 pitch 조절로 확장한다.
로봇 재배치는 별도의 수동 조작 범위다. 독립 정답 정확도, 본체 절대 pose/외부
파라미터, 실제 정합, 주행 적용은 수행하지 않았다.

이번 로컬 UI/도표 확인용 임시 서버와 에이전트 탭은 정리한다. 로봇의 기존
사용자 탭은 건드리지 않으며, 후속 카메라 실행·배포·자동 작업은 예약하지 않는다.
