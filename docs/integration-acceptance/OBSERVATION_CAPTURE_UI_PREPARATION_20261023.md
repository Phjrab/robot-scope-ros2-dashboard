# 정합 입력 보존과 통합 UI 적용 준비 — 2026-10-23

로봇 없이 수행한 후속 구현과 설치 소스 비교다. 비교 기준 main은 `c6b6e807`이며,
장비 마지막 확인 Git 기반은 `d7807de8`에 선택 적용한 파일들을 더한 상태다.
이번 작업은 장비 접속·배포·서비스 재시작·센서 실행·제어를 수행하지 않았다.
실제 정지/이동 관측 결과는 [SAME_START_OBSERVATION_20261023.md](SAME_START_OBSERVATION_20261023.md),
이전 최소 수정은 [OFFLINE_MOTION_FOLLOWUP_20261023.md](OFFLINE_MOTION_FOLLOWUP_20261023.md)를 따른다.

## 선택적 입력 기록과 재현

기존 `POST /api/v1/observations/map-alignment` 요청에 `capture_inputs: true`를
명시하면 기존 결과에 `input_capture`가 추가된다. 기본값은 false이며 일반
요청은 배열 인코딩을 수행하지 않는다. 새 endpoint나 자동 수집은 없다.

기록 내용:

- 실제 solver의 전체 normalized reference(최대 100,000점)와 투영·stride 후
  query(최대 512점). 각 XYZ 배열은 little-endian float64 base64, 점 개수와
  SHA-256을 함께 저장한다. 원시 센서 payload나 원본 PCD의 복제는 아니다.
- 지도 ID/revision/frame, query frame, 단위, 실제 `T_map_odom_seed`, paired
  pose의 topic/frame/child/position/orientation과 존재할 때 sequence.
- 기존 provenance 전체: 원래 cloud/pose source timestamp 문자열, 수신 시각,
  관측 세대와 pairing 근거. 원래 시각을 현재 시각으로 바꾸지 않는다.
- 원래 응답의 수렴·잔차·overlap·처리시간·변환, 원본 5cm 판정과 잠정 10cm
  판정. `REJECTED/NOT_CONVERGED`도 정상 완료된 수치 응답이면 기록한다.

기존 source/map/신선도/완료 검사를 통과한 응답만 기록한다. HTTP 409로 끝나는
입력 불일치·stale·deadline·busy 실패에는 기록이 없으며, 이 기능으로 모든
실패 입력을 보존할 수 있다고 해석하지 않는다. 기존 600ms 계산 예산과 판정
기준은 유지한다. 선택적 배열 인코딩은 완료 검사 뒤 추가 비용이며
`input_capture_runtime_ms`로 분리한다. 큰 JSON 응답 인코딩도 WebSocket 이벤트
루프 밖에서 수행한다. 장비에서의 추가 지연은 아직 측정하지 않았다.

`scripts/observation_capture.py`는 요청 1회와 로컬 파일 저장을 위한 도구다.
장비 적용과 새 관측 실행을 승인받은 후, 기존 관측 요청의 최신 map/source
식별자와 seed를 담은 JSON을 입력한다. 다음은 **향후 실행 예시**이며 이번에는
장비에 실행하지 않았다.

```sh
.venv/bin/python3 scripts/observation_capture.py capture \
  --base-url http://192.168.50.30:8088 \
  --request /private/path/alignment-request.json \
  --output /private/path/new-input-capture.json
```

같은 origin에 한 번만 요청하며 redirect·URL 인증정보·자동 재시도를 허용하지
않는다. 입력이 오래됐다고 seed/epoch를 자동 교체하지 않는다. 센서 시작이나
결과 pose 적용은 없다. 출력은 저장소 밖의 새 파일만 허용하며 mode 0600으로
생성하고 기존 파일은 덮어쓰지 않는다. 읽기/출력 크기는 4MiB로 제한한다.
좌표가 포함된 결과는 private 자료로 보존하고 Git에 추가하지 않는다.

재현은 로봇 연결 없이 실행한다.

```sh
.venv/bin/python3 scripts/observation_capture.py replay \
  /private/path/new-input-capture.json \
  --output /private/path/new-replay.json --budget-seconds 10
```

배열 개수·hash·유한값, 지도/응답/source 일치와 rigid seed를 검사한 뒤 현재
solver로 다시 계산한다. 재현 예산은 명시적으로 최대 60초이며 live 예산을
변경하지 않는다. 결과는 `HISTORICAL_NUMERICAL_REPLAY`, `current_pose_valid=false`,
`operational_application=NOT_RUN`이다. 원래 응답은 배열을 제외하고 그대로
함께 보존한다. 플랫폼·라이브러리·실행시간 차이가 있어 수치 결과가 달라질
수 있으며, 과거 결과를 새 결과로 대체하거나 절대 정확도로 해석하지 않는다.

17:43 수동 이동의 미수렴 기록에는 XYZ가 없어 당시 정합을 재현할 수 없다.
이번 기능은 **다음 관측 입력**을 보존하기 위한 것이다. 연속 이동 UI 검증은
여전히 시도했지만 미통과이며, 절대 정확도와 Go2 본체 변환은 미측정이다.

## 통합 UI와 보존된 장비 소스의 호환성

private `same-start-20261023/offline-capture-ui/`의 `audit_ui.py`와
`ui-compatibility.json`에 비교 근거를 보존했다. 이는 현재 장비 재조회가 아니다.

- `fix-2/merged-runtime` Python 176파일 중 173파일이 현재 소스와 byte 단위로
  같다. 당시 적용한 5파일은 source manifest의 적용 후 SHA와도 대조했다.
- 차이는 이번 capture 옵션의 Python 2파일과 이미 main에서 제거한
  `external_global_observation.py`의 미사용 `tempfile` import뿐이다.
  새 `observation_capture.py`는 과거 snapshot에 없으므로 별도 추가 대상이다.
- UI가 사용하는 router 등록, 지도/PCD 편집, sensor tracking, global
  observation의 처리 코드는 보존본과 같다. API route 추가/삭제는 없으며,
  route 목록 일치만으로 호환성을 판정하지 않고 해당 처리 코드도 비교했다.
- main의 상대 JS import 122개는 모두 해결된다. 이는 전체 main 소스의
  검사이며, 장비에 해당 파일이 현재 존재한다는 증명은 아니다.

과거 Git 기반과 달라진 static 21파일 중 `pointcloud_transport.js`와
`socket_watchdog.js`는 마지막 적용 manifest와 현재 main의 SHA가 같다.
나머지 **19파일**이 통합 UI 검토 후보다. 아래 경로는 `robot_dashboard/static/`
기준이다. “보존 SHA 있음”도 실제 적용 전에는 현재 설치 hash를 재확인한다.

| 묶음 | 파일 | 설치 바이트 근거 |
| --- | --- | --- |
| 진입점·3D 표시 | `app.js`, `scene3d.js` | 보존 SHA 있음 |
| 현재 관측 | `features/maps/live_observation.js`, `features/maps/live_observation_contract.js` | 보존 SHA 있음 |
| 현재 관측 표시 | `features/maps/live_observation.css`, `features/maps/saved_scene.js` | 현재 장비 readback 필요 |
| global 관측 | `features/maps/global_observation.css`, `global_observation.js`, `global_observation_contract.js`, `global_observation_integration.js` (모두 같은 디렉터리) | 현재 장비 readback 필요 |
| sensor 관측 | `features/maps/sensor_tracking.css`, `sensor_tracking.js`, `sensor_tracking_contract.js` (모두 같은 디렉터리) | 현재 장비 readback 필요 |
| 3D 편집 | `features/map_editor3d/full_source.js`, `features/map_editor3d/workspace.js` | 현재 장비 readback 필요 |
| 화면 구성 | `dashboard-polish.css`, `index.html`, `features/slam/depth_capture.js`, `features/slam/presentation.css` | 현재 장비 readback 필요 |

15파일은 이번 비교에 실제 설치 바이트 근거가 없으므로 과거 Git hash를
설치 전조건으로 쓰지 않는다. 신규 파일처럼 보이더라도 장비에서 부재를
확인해야 한다. `app.js`만 최신본으로 바꾸면 새 import/DOM/CSS의 동반 변경을
놓칠 수 있으므로 19파일을 함께 비교하고 설치된 사용자 변경을 보존한다.

private `capture-backend-candidate/`, `ui-candidate/`와 `candidate-manifest.json`은
소스와 SHA를 고정한 검토 자료다. unknown before hash는 null로 남긴다.
현재 설치값·백업이 확보되지 않았으므로 자동 적용 스크립트는 제공하지 않는다.

## 다음 장비 적용 범위의 구분

| 범위 | 대상 | 필요한 장비 단계 |
| --- | --- | --- |
| 이전 최소 이동 표시 수정 | 이전에 준비한 static 2파일 | hash 확인·백업·적용·브라우저 새로고침 |
| 통합 UI | 위 19 static 후보 | 15파일 readback 포함 설치 차이 재검토·백업·구체적 적용 목록 확정·새로고침 |
| 입력 기록 | API router, `relocalization/observation_alignment.py`, 새 `relocalization/observation_capture.py`의 Python 3파일 | 현재 hash/신규 경로 확인·백업·별도 배포 및 서비스 재시작 |

이전 최소 2파일 묶음과 통합 UI 묶음을 순서대로 덮어쓰지 않는다. 특히 이전
`app.js` 후보는 당시 장비 파일에 최소 patch만 적용했으며 최신 main 전체와
다르다. 실제 적용할 한 범위를 선택하고 현재 설치 상태에 맞춰 구성한다.
CLI는 운영자 PC에서 실행하며 장비 배포 파일에 포함하지 않는다.

기존 관측기는 17:47:27 KST에 종료됐다. 새 관측 실행과 현장 정지·수동 이동
확인은 위 소스 준비와 별도다. 기존 승인 횟수를 재사용하지 않으며 실제 배포가
필요할 때 변경 파일·서비스·설정/지도 보존·백업/복구·실행 범위를 묶어 제시한다.
다음 한 작업은 로봇이 준비됐을 때 **현재 설치 파일을 읽어 후보와 대조하고
최소 적용 범위를 확정하는 것**이다.

## 로컬 검증

전체 Python 2,636개 실행(4 skipped), JS 643개, 관련 브라우저 16개 통과.
브라우저 범위는 live observation 9, global observation 4, full-source editor 3이다.
Ruff, 기존 strict mypy 4모듈, JS 문법 100모듈도 통과했다. 새 입력 보존 검사
8개는 실제 분리 worker와 오프라인 재현, float64 왕복, 선택적 sequence,
원본 거부 판정 보존, 손상/범위 검사, private 출력, 단일 HTTP 요청을 다룬다.
이 검증은 실제 장비 지연·궤적·정확도 검증을 대신하지 않는다.
