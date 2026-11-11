# 주행 검증 인계 — 2026-11-11

인수 원격 SHA: `4b244d4024327c070482cdd71f4732ea081962d7`. clean main에서 시작했다.
작업은 main 단일 브랜치에서 직렬 수행했고 이전 역할 브랜치를 병합하지 않았다.

## 변경

- 강제 preparation refresh를 버리지 않고 후속 조회로 합쳐 기다린다. 이전 snapshot이 최신 blockers를 덮거나 관측 시작을 열지 않도록 한다.
- 조회 중 시작 UI/handler 차단, 정확한 관측 종료 유지와 종료 후 최신 조회를 검증한다.
- 실제 API/server admission의 unsupported inhibit 거절과 무명령을 독립 검증한다. 서버 차단 조건은 이미 존재했으며 완화/중복 구현하지 않았다.
- 작은 양의 첫 거리 결함의 실행 재현 도구와 대조 결과를 추가했다. 이 위험은 **REPRODUCED / 미수정**이다.

## 게시 영수증

- 코드 commit: `090afc7ecc24cd0db49374fa4865084bd52cb45d` (`fix(navigation): preserve forced preparation refresh requests`).
- `git push origin main` 성공 후 `git ls-remote origin refs/heads/main`도 위 SHA와 일치했다. force push/이력 재작성 없음.
- exact-SHA CI: [42996364533](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42996364533), **success**, 7 jobs 모두 success. Ubuntu 22.04/Python 3.10 및 Ubuntu 24.04/Python 3.12의 Python/JavaScript/정적/의존성/API fixture와 browser shard 1·2를 포함한다. 확인 시각 2026-11-11 18:46:56 KST.
- 별도 I0: [42996364303](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42996364303), **success**.
- 로컬: Python 3,706 passed / 35 skipped (3,741 run), 관련 브라우저 127 passed, JavaScript 765 passed. 첫 환경 실패와 skip을 통과로 세지 않았다.
- 후보 source archive: `git archive --format=tar 090afc7ecc24cd0db49374fa4865084bd52cb45d`; SHA256 `5f9672c5bd1cfba7f84900c4b2c3c708691b9fc531b9c156720117b095934047`, **2,717 파일** 전체를 해당 Git blob과 대조했다. [검증 영수증](CANDIDATE_RECEIPT.json). 로컬 `/workspace/work/navigation-candidate-090afc7.tar`에 준비했으며 장비 전송/배포 없음.
- 후보 SHA에서 진행률 진단도 재실행: exit 1 / REPRODUCED, 대조 결과 및 production source hash가 인수 SHA 재현과 동일하다.
- 이 문서 후속 commit은 문서/합성 증거만 추가한다. 배포 후보는 위 코드 SHA로 고정하며 최종 main HEAD를 자동 배포 대상으로 사용하지 않는다.

로컬 전체 결과와 정확한 명령은 [TEST_RESULTS.md](TEST_RESULTS.md)에 기록한다. 원래 failure run과 새로운 CI를 구분한다.

## 다음 한 작업과 유효 장비 범위

다음 한 작업은 **현재 장비 접속 경로를 확인하고 실행본·mode/profile·지도/교정·STOP/lease·정지 상태를 읽기 전용으로 인수**하는 것이다.
현재 로봇 단계는 미확인이다. 장비가 꺼졌다고 단정하지 않는다.

이번에 배포·서비스 전환·센서 세션·INITIAL POSE·Nav2/match·목표/이동은 실행하지 않았다.
이 세션에서 그 장비 조작 승인은 확인되지 않았다. [FIELD_PLAN.md](FIELD_PLAN.md)의 후보/복구 준비 후 필요한 정지 시험 범위를 한 번에 확인한다. 실제 목표 이동은 현재 목표/횟수/시간을 고정한 별도 창이다.
과거 승인·A3 native·다른 모의 TF 시험은 재사용하지 않는다.

표시/health 진행률 결함, 실제 접근 정체, 정지 후 yaw 잔차는 서로 별개의 다음 문제다.
이 후보는 주행 전체 현장 통과판이 아니다. 지도·교정·사용자 프리셋·STOP/lease/watchdog/Safe mode는 보존한다.


## 후속 2회차 — 2026-11-11 재개

인수 SHA `488d279b3a97300db80fd32843008b3e83344c5a`; 원격 main과 일치.
기준 CI [42998127916](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42998127916),
I0 [42998127664](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/42998127664)
success 재확인. 과거 체크아웃의 사용자 변경을 보존하고 새 일반 main 체크아웃에서 작업했다.

실제 변경:
- 재현 도구가 일부 재현을 exit 0으로 놓치던 집계를 수정하고 대조 실패를 INCONCLUSIVE로 분리.
- 실제 gateway send/accept callback + matching endpoint 관측 후 거리열 재현 추가.
- 정상 짧은 목표, 큰 왕복, goal generation/ID 각각의 거절, plan 단독 비소비, 진단 판정 회귀 5건.
- 기존 4개 문서의 이력을 보존하여 이 회차를 append하고 후속 조사·JSON을 추가.

운영 progress 계산은 **SOFTWARE_REPRODUCED / 미수정**이다. 현재 feedback에 소비 path
식별자가 없어서 임의 baseline reset·최소거리 cutoff·timeout 완화를 채택하지 않았다.
신선한 matching `/plan`도 소비 증거가 아님을 분리했다. 현재 변경은 배포 후보가 아닌
진단·검증 변경이며 이전 090afc7 후보 archive 영수증을 대체하지 않는다.

최종 로컬: Python **3,711 passed / 35 skipped (3,746 run)**,
JS **765 passed**, browser 8파일 **127 passed**, syntax **135 modules**,
Ruff/mypy/pip check/diff 통과. 첫 환경 실패와 의도된 재현 exit 1은 통과에 포함하지 않았다.
정확한 명령·첫 실패·환경·skip은 [TEST_RESULTS.md](TEST_RESULTS.md)의 후속 절에 있다.

장비 루트 GET과 검증된 known_hosts를 쓴 BatchMode SSH는 모두 timeout.
실행본·mode/profile/source·지도/교정·STOP/lease·물리 정지는 미확인이다.
배포·서비스 전환·관측·Nav2 시작·INITIAL POSE·match·목표·이동은 전부 NOT_RUN.
다음 한 작업: **현재 유효한 장비 접속 경로에서 읽기 전용 실행본/상태 인수**.


### 후속 게시와 I0 probe 추가 수정

첫 후속 commit `a3f50c7f448c06140f51a9c31f447f2975db0395` 정상 push/원격 일치.
해당 CI [43005433103](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43005433103)는
**success / 7 jobs success**. I0 [43005433124](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/43005433124)는
attempt 1·2 모두 full-app 준비 predicate에서 실패했으며 원본 artifact/hash를 보존했다.
동일 SHA 로컬 component/full-app은 통과했다. 이 차이만으로 CI 원인을 확정하지 않는다.

짧은 유효 상태를 기본 expect.poll이 놓치는 경로를 합성 DOM으로 별도 재현한 뒤,
동일 predicate와 5000ms 한도를 유지하여 브라우저 RAF 관측 helper로 probe를 수정했다.
신선한 상태를 만들거나 gate를 우회하는 코드가 아니다. 관측 실패·stale 거절을 포함한
브라우저 3개 회귀를 추가했다. 후속 commit은 이 probe와 게시 영수증을 담는다.
운영 gateway/health/preparation.js 변경은 여전히 없고 진행률 결함은 미수정이다.


최종 probe 수정본 로컬 결과: Python **3,746 run / 3,711 passed / 35 skipped**,
153.940초, failures/errors 0. JavaScript **765 passed**. 기존 8파일 + 새 probe 파일의
브라우저 **130 passed**. C0 component/full-app 각각 PASS 및 소유 server 종료 확인.
Ruff/mypy/diff 재확인 통과. 기존 1초 freshness와 검사 5초 제한, 운영 source는 그대로다.
이 결과는 a3f50c7 + probe/문서 diff이며 후속 게시 commit의 CI와 구분한다.
