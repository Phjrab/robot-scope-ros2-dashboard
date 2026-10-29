# C3 후속 검증 — C1 0.2 · bulk asset · D3 native 기록 재생

2026-10-29. **최신 D1→D2→D3→C1 실제 core/저장/HTTP와 C3 표시 연결 PASS.**
C1 0.2 변환은 생산자 소유 구현을 그대로 실행한다. D3의 실제 원격 native
기록도 C1 HTTP를 거쳐 재생했다. 로컬 ROS/native 실행과 실장비 검증은 NOT_RUN이다.
이 보고서가 이전 [0.1 검증](ROUND2.md)의 남은 계약/자료 상태를 갱신한다.

## 제출 범위와 검증 소스

- 기존 clone/브랜치 `review/20261029-x-c3-scene-ui`를 유지했다. 시작 HEAD는
  `a2b6d37f61ac426ac8a21e941750099b28318fd8`; clean 상태에서 시작했다.
- 최종 소스·테스트·증거는 이 보고서를 처음 추가한 **동일 제출 커밋**에 있다.
  정확한 SHA는 `git log -1 --format=%H -- docs/parallel-expansion-20261029/C3/ROUND2_V02.md`로
  확인한다. 최종 채팅에서 40자리 SHA, 원격 일치, 해당 SHA의 CI 결과를 보고한다.
  자기 SHA를 문서 안에 가짜로 넣지 않는다. 테스트한 각 소스의 SHA256은
  [manifest](evidence/round2-v02/manifest.json)에 고정한다.
- 수정은 `static/features/obstacle_scene`, `tests/expansion_c3`, 전용 실험/C3 문서뿐이다.
  다른 역할 소스는 정확한 `git archive` export를 읽기 전용으로 import했다.
- 공용 기반 `f469155c2b0c505f3e472e878f75029d7b8d39df`, app/renderer/navigation/CI,
  main, 제품 연결은 그대로다. 새 채팅/PR/merge/cherry-pick/force-push 없음.
  로봇·카메라·운영 DDS 접속, 배포, TF/명령 발행, 실이동 없음.

## 정확한 의존성

| 역할 | 사용 SHA | 사용 경계 |
|---|---|---|
| D1 | `203c144f6b4a90966839c34b603ae12ee676cb12` | 실제 seeded solve, 합성 2개 지도 800점, C1 저장/reload |
| D2 | `7313f0a31c00ae87ae216b84ca41a23804e91917` | 실제 process_lidar / Tracker.step |
| D3 | `356d0a036eb62d546e159e12a0691d7f5ea278f6` | 실제 assess / scoped coverage / canonical_assessment |
| C1 | `4e1dd519a707169da5f88cf2a92a20ed3e701cc7` | 실제 0.2 validator / ClockBinding / SceneSnapshotService / authenticated HTTP / assets / BundleStore |
| C2 | `47a1d031d797c098c38a0147894523d07d30db8f` | 20개 짧은 최신 호환성 PASS 후 동결; 기존 exact_service_host를 읽기 전용 재사용 |
| C4 | `073d05b24c73b4de08c754833d4c05e537a23727` | 현재 계약·인계 읽기만 함. 이번 runtime/ROS 실행 의존성 아님 |

원격 조회는 사용자 재개 요청에 따라 한 번 수행하고 SHA를 고정했다. Dots 코드를
수정하거나 재지시하지 않았다. 실행은 D1 저장 참조를 만든 뒤 D2→D3 순서다.
D1/C2를 재개발·튜닝하지 않았으며 짧은 정합 실행은 C3가 실제 merged artifact를
소비하기 위한 생성 단계다. 출력 PCD SHA256은 이전 검증과 같은
`46be1a0ec38166fc78e7d0344d3e241d57e3c29807f22e819e22e04d1ec9dbde`이다.
PCD/지도 파일은 임시 디렉터리 종료 시 제거하고 Git에 게시하지 않는다.

C1 12개, D1 6개, D2 4개, D3 7개, C2 host 1개 Git blob을 import 전에 검증했다.
공용 PCD/SE3 의존성도 C1/D1/D2 각 SHA와 로컬 파일 5개씩 일치함을 확인했다.
C2의 DTO 검사에는 최신 C1 실제 Python validator를 사용했다. 20개 중 HTTP ports
검사는 mock transport이며, 이를 실제 HTTP 실행으로 계산하지 않는다.

## 해결한 결함과 연결

1. C1 0.2를 거부하던 C3 adapter를 0.1/0.2 공존으로 보완했다. C1의
   `sources[slot].status`를 반영하고 expired/unavailable sequence를 기억해
   지연된 예전 응답이 pose/obstacle/path/costmap/평가를 되살리지 못한다.
   C1의 25자리 source stamp 범위와 JS-safe ns 처리를 맞췄다.
2. C3 테스트용 시간 키 변환과 full-ref 축약을 제거했다. **실제 D3
   canonical_assessment → 실제 C1 normalize_collision_assessment/ClockBinding**을
   호출하며 0.2 decimal ns, 원래 interval, epoch, clock, receipt, full refs를 유지한다.
   `9007199254740993` ns는 정확히 보존한다. 반복 fetch/변환이 TTL을 갱신하지 않는다.
3. 새로운 asset cache는 C1의 고정 인증 경로·opaque ID/revision만 처리한다.
   8개/각 2 MiB/합계 8 MiB, media/실제 byte 수/SHA256을 검사한다. 동일 ref는
   한 번 fetch/decode하고 map/revision/삭제/dispose 때 정리한다. 지연 응답은
   새 context에 재삽입되지 않는다. 표시 geometry는 관측 시각·신원·evidence를
   덮어쓰지 못한다. 실패도 숨기지 않고 명시하며 반복 poll마다 재시도하지 않는다.
4. 실제 D1→C1 저장 결과의 ID/revision을 선택한 scene map identity로 사용한다.
   C1이 제공한 160점 preview를 bulk reference로 표시한다. 800점 원본이나
   D2/D3 입력을 display decimation으로 바꾸지 않는다.
5. native 기록의 0–100 occupancy와 Nav2 0–255 cost 단위를 분리했다. 원본
   200×150 grid를 표시용 40×30으로 축약하되 extent/원점/축과 unknown을 보존한다.
   원본 path 좌표는 그대로다. coverage 요약과 protection을 따로 표시하고 상세
   원본은 inspector에 유지한다. 없는 joint/calibration/collision은 채우지 않는다.

C1은 asset 바이트의 cloud/costmap geometry schema를 규정하지 않는다.
`c3-test-display-v1` decoder는 **격리된 C3 테스트 host의 명시적 형식**이며
새 C1 공통 v1이 아니다. 제품 연결 때는 생산자 소유 geometry profile/decoder를
명시적으로 공급해야 한다. arbitrary URL/path를 해석하거나 공용 파일을 수정하지 않았다.

## 실제 실행과 mock 경계

| 검사 | 최종 로컬 결과 / 범위 |
|---|---|
| C3 unit | **38 PASS**: 기존 consumer 16 + canonical 17 + asset 5; asset transport fault는 mock/fault injection |
| C1 HTTP/core browser | **6/6 PASS + frozen source PASS**; 실제 D2/D3/C1 코드, 입력은 생성한 SYNTHETIC |
| Scoped CLEAR | 실제 D3 coverage qualifier에 finite volume/horizon/epoch/map/source refs 제공; 실제 관측 free-space 아님 |
| Native replay browser | **PASS**; 원격 native artifact의 실제 plan/costmap 기록 → C1 HTTP → C3 |
| 기존 fixture browser | **11 PASS**, 1200 packets 약 39.99 Hz, queue≤1/history≤3, post-GC +210084 bytes |
| C2 short compatibility | **20 PASS / 0 skip**; 이후 동결 |
| 전체 Python | **3117 run / 2 기존 optional skip / 0 failure**, 최종 로그 참조 |
| 공용 JS | **699 PASS** |
| JS syntax | **117 modules PASS** |
| secret scan / whitespace / 소유 경로 | PASS |
| 로컬 ROS / native 프로세스 | **NOT_RUN**; 기록 재생과 구분 |
| 실측 sensor/mount/clock/free coverage | **INPUT_REQUIRED** |

PREDICTED_CONTACT는 D3의 PREDICTED_COLLISION 표시명이다. NEAR는 시나리오명이고
실제 severity는 양의 거리와 함께 UNKNOWN이다. 범위가 명시된 합성 CLEAR만 CLEAR이며,
ACTIVE_UNKNOWN은 UNKNOWN/HOLD를 유지한다. EXPIRED는 C1 0.2가 모든 오래된 slot을
null/expired로 내보내고 C3가 그대로 차단한다. 기존 0.1 회귀도 유지한다.
동일 frozen seq의 추가 GET 9회에서도 stale을 유지했고 geometry copies=7과 asset
fetch/decode=1을 유지했다. 모든 브라우저 요청은 loopback GET이었다.

합성 core 검사의 pose/joint/path/costmap/clock correspondence는 test-host가 공급한다.
공식 Go2 visual asset은 재사용하지만 D3 합성 body-box의 실제 collision 등가성은
주장하지 않는다. ACTIVE_CONSTRAINT는 테스트 host의 명시적 표시 상태이며
C4 command authority 또는 실제 보호 활성화 증거가 아니다.

## Native 증거의 정확한 경계

- [D3 native run 40840774827](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827)
  **SUCCESS**, 실제 실행 SHA `fa8e26e02194d3c99ccc7b8e45eb3177a6fce19d`.
- [Artifact 12882393645](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840774827/artifacts/12882393645),
  ZIP 975251 bytes, SHA256
  `0f09cf101555dbef3368fc6913acd9cdd61e380ad45c51472ea5e6b1b3cdc6aa`.
  GitHub artifact digest와 로컬 ZIP을 대조하고 source-sha.txt도 확인했다.
- D3 summary는 5개 scenario의 native 성공을 기록한다. **C3는 appearing-obstacle의
  원본 plan/costmap/pose 기록 한 시점을 재생**했다. 5개 native 실행을 여기서
  다시 실행하거나 전체 trajectory를 C3에서 검증했다고 주장하지 않는다.
- 기록의 sim stamp와 원래 receipt를 유지한다. 원래 receipt는 float seconds여서
  ns로 반올림했음을 명시한다. 동일 기록에 고유 host alias를 주고 그 기록의 최대
  receipt를 historical service clock으로 사용한다. 서로 다른 호스트나 sim/host
  시각을 같다고 간주하지 않는다. browser elapsed는 별도로 더한다.
- NavFn + direct RPP의 기록이다. 새로운 D3 URDF 보호는 원래 native 실행에서도
  ADVISORY_ONLY였다. native joint/calibration/assessment가 없으므로 C3에서는
  해당 URDF/risk 표시가 차단된다. C4 production ROS port 연결 증거가 아니다.

원본 native 로그/지도는 외부 artifact와 `/tmp`에만 유지한다. 게시 증거에는
파일 해시, 정확한 endpoint bytes, 작은 요약과 screenshot을 남긴다. snapshot
fingerprint와 캡처의 연결은 browser report에서 확인할 수 있다.

## CI, 재현, 남은 한 가지

[재현 명령](../../../experiments/expansion_20261029/c3_scene_ui/README.md),
[현재 연결 hook](INTEGRATION_POINTS.md),
[검증 manifest](evidence/round2-v02/manifest.json).
Python 3.12.3 / Node 24.22.1 / Playwright 1.62.1 / Chromium 151.0.7922.34.
전체 테스트는 제외 없이 실행했다. 마지막 UI/source guard 변경 후 전체 회귀를
재실행했다. 성능검사 종료 확인 전에 시작된 중간 full run 하나는 즉시 중단하고
직렬 재실행했으며 PASS 수에 포함하지 않는다. 테스트/시간제한/CI는 완화하지 않았다.

이 제출의 push CI는 커밋 전에 실행될 수 없으므로 이 문서에서 PASS로 미리
주장하지 않는다. 최종 채팅에서 해당 정확한 HEAD의 원격 CI 결론/링크를 보고한다.
직전 C3 a2b6d37의 [CI 40840846267](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/40840846267)는
SUCCESS였고 공용 코드/CI 파일은 동일하다. 원격 CI는 C3 unit을 포함한 전체 회귀이며
새 peer SHA와 native artifact를 자동 fetch하는 workflow는 추가하지 않았다.
따라서 위 실제 cross-role HTTP/native replay PASS는 **로컬 명시 실행 증거**다.

**남은 한 가지: 실측 source→host clock·mount/calibration과 motion-volume coverage를
포함한 생산자 소유 canonical replay bundle.** 현재 generated core 및 recorded native
UI 연결은 완료했지만 실제 sensor 동기화/coverage를 자격 부여하지 않는다.
이 입력이 오기 전에는 새 D3 ACTIVE 보호 또는 실로봇 회피 성공을 주장하지 않는다.
