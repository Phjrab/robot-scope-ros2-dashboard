# 수동 이동 관측 — 로봇 없이 수행한 후속, 2026-10-23

main 통합 `27a9a5c` 이후의 오프라인 수정·분석이다. 장비 접속, 배포, 서비스
재시작, 관측기 실행, 로봇 제어는 수행하지 않았다. 실제 장비 이력은
[동일 시작점 관측 기록](SAME_START_OBSERVATION_20261023.md)을 따른다.

## 수정과 재현

`LiveMapObservation.setMap()`은 지도 전체 metadata를 문자열로 비교했다.
동일 ID·revision·frame에서도 이름·점 개수·저장시각 표시 정보가 갱신되면
`MAP_CHANGED`로 기존 보정과 궤적을 버리는 것을 단위 검사로 재현했다.
이제 세 식별 필드와 유효한 reference의 유무를 비교하고 표시 정보는 갱신한다.
실제 ID·revision·frame 변경, reference 누락·revision 불일치·demo 입력은
계속 연결을 해제한다. 당시 장비의 정확한 `MAP_CHANGED` 유발 이벤트가 이
조건이었다고 확정한 것은 아니다.

앞서 반영한 동일 revision의 비동기 재조회 수정과 함께 브라우저에서 합성
0.5 m 이동·30° 회전·목록 정보 갱신·지연된 지도 응답을 검증했다. 기존 보정과
궤적 시작점이 유지되며, 실제 revision 변경은 위치와 overlay를 지운다.
별도 결정론적 검사에서는 이동 중 두 소켓의 600 ms 침묵, 재접속, 늦게 도착한
구 소켓 callback, 멈춘 animation frame, 지도 정보 갱신을 결합했다.
1초 초과 stale 이후에는 새 입력만으로 anchor가 되살아나지 않는다.
freshness·source·잔차·수렴 기준과 로봇 출력 경로는 변경하지 않았다.

## 보존 기록 분석과 재생의 한계

private `same-start-20261023/offline-followup/`에 재현 스크립트, 입력 SHA-256,
`stream-analysis.json`, `receipt-gaps.csv`, `replay-results.json`을 보존했다.
원시 자료는 Git에 포함하지 않는다. 아래는 기존 109.90초 이동 구간만의
요약과 구분한 **각 전체 5분 기록**이다. 간격은 로봇 내부 loopback WebSocket
기록기의 monotonic 수신시각 기준이다.

| KST 구간 | pose / 점군 수 | 최대 수신 간격 pose / 점군 | 점군 간격 ≥600 ms / >1초 |
| --- | --- | --- | --- |
| 17:19:01–17:24:01 | 2,463 / 1,392 | 0.460 / 0.608초 | 1 / 0 |
| 17:42:21–17:47:21 | 2,465 / 1,418 | 0.523 / 0.652초 | 2 / 0 |

두 기록 모두 원본 source stamp·seq 역행/중복 0건이며, 각 stream의
observer/epoch/subscription/graph fingerprint/topic/frame 조합은 하나다.
첫 번째 `motion-stream.ndjson`는 0바이트라 재생 증거가 없다.
마지막 두 600 ms 초과 점군 공백은 17:44:01과 17:46:26에 있다. 이는 현재
watchdog가 재접속할 수 있는 길이지만, 실제 브라우저 재접속의 증거는 아니다.
브라우저 수신과 로봇 내부 수신을 동일한 것으로 해석하지 않는다.

기록기는 pose 전체와 점군 metadata만 저장했다. XYZ는 저장하지 않았다.
원본 pose·문자열 source stamp·수신 간격을 제품 model/transport에 재생하고,
합성 점 하나와 native 좌표를 그대로 두는 시험용 anchor를 사용했다.
animation frame을 전부 멈추고 3회 목록 정보를 갱신했을 때, 초기 anchor 이후
50 ms 간격 검사 5,997/5,998회에서 위치 누락은 없었다. pose 소켓은 각 1개,
점군 소켓은 각 2/3개 생성됐다. 최신 프레임만 배출하는 큐 때문에 전달된 점군
수는 원본 기록 수보다 작다. 이 시험은 handshake 지연을 0으로 두며 실제
브라우저 이동 궤적 복구, ICP 재계산, 정밀도 검증을 의미하지 않는다.

## 미수렴 판단

17:43:31 보존 결과는 RMSE 0.058632607 m, overlap 1.0, 430/430 inliers,
40회 반복, `converged=false`, 수치 계산 156.84 ms/전체 220.21 ms다.
geometry 비율 0.03079/0.02860은 기존 0.002 기준을 통과한다.
solver는 한 step의 이동과 회전이 각각 1e-5 m/1e-5 rad 미만일 때 수렴하며
최대 40회 반복한다. 10 cm 잔차 비교 통과와 수렴은 다른 조건이다.
원래 5 cm 평가는 `HIGH_RESIDUAL`, 잠정 평가는 `NOT_CONVERGED`로 거절된다.

정확한 moving query XYZ와 반복별 변화 기록이 없어 느린 수렴·대응점 교대
등의 수치 원인을 구분할 수 없다. 이전 정지 scan으로 대체하거나 threshold,
반복 수, 계산 예산을 늘리지 않았다. 다음에 이 거절을 분석하려면 실제 정합에
쓰인 query 배열·시각이 연결된 pose·seed·reference hash를 함께 보존해야 한다.
표시용 preview 점군만으로 정확한 정합 입력을 확보했다고 간주하면 안 된다.

## 검증과 CI

- 전체 Python unittest: 2,628개, 성공, 4개 건너뜀.
- 전체 JavaScript: 643개 성공.
- 관측 Playwright 9개를 3회 실행: 27회 성공.
- Ruff, strict mypy 대상 4모듈, JS 100모듈 구문, tracked-source secret scan 성공.

이전 통합 [CI 39932567619](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/39932567619)는
Ubuntu 22.04 성공, Ubuntu 24.04의 관측 브라우저 1개 실패였다. 실패 지점은
재조회 전 fixture 초기 연결의 `WAITING_PAIRED_POSE`였다. 독립 timer로만 pose를
보내던 합성 FAST-LIO 입력은 점군에 대응하는 exact stamp를 빠뜨릴 수 있었다.
fixture가 각 점군에 대응 pose를 보내고, 소켓 재접속에도 seq를 유지하도록
수정했다. 제품의 시각 일치 조건과 실패 검사를 완화하지 않았다.
로컬 로그는 `/private/tmp/scope-offline-{python,js,browser-final}.log`에 있다.

## 다음 장비 적용 준비

private `offline-followup/static-candidate/`는 당시 설치 overlay를 기준으로 한
최소 **2파일** 후보다. 통합 main의 전체 UI를 장비에 덮어쓰는 묶음이 아니다.

| 파일 | 후보 SHA-256 |
| --- | --- |
| `robot_dashboard/static/app.js` | `3c899d975bb14ec5393b1e3ca507de3f985c5c15a7b91bb042ca7371a0af8600` |
| `robot_dashboard/static/features/maps/live_observation_contract.js` | `c46c2cb1d18baa42fb7f593adef2ed17585bb5854ac50dfde0992997b1c96894` |

원본 hash/metadata, 변경 patch, source manifest, 지도·설정 hash 조건을 포함한다.
로컬 임시 checkout에서 사전 확인→적용→원복 후 hash/mode/mtime 일치와
원본이 달라진 경우 적용 거절을 검증했다. 장비 적용과 최신 설치 hash 확인은
미실시다. 브라우저 새로고침이 필요하며 이 static 수정 자체는 서비스 재시작이
필요 없다. 이전 관측기는 17:47:27에 종료되어 새 관측 실행은 별도 범위다.

다음 장비 작업은 이 묶음의 명시적 적용·새 관측 실행 승인 후, 현재 설치 hash와
지도 ID `b9087113da92a1f2b477e932`/revision을 확인하고 새로운 세션으로 연결하는
것이다. 과거 시작점·anchor를 현재 위치로 재사용하지 않는다. 정지 연결 후
사용자가 직접 짧게 이동·회전하는 한 구간에서 source/수신 age/지도 identity와
연속 UI 궤적을 함께 기록한다. 같은 지도 재조회 동안 연결 유지, 실제 입력 중단
후 현재 위치 해제를 확인한다. G(연속 이동 UI)는 여전히 **시도했지만 미통과**,
독립 절대 정확도와 Go2 본체 좌표계 보정은 미측정이다.
