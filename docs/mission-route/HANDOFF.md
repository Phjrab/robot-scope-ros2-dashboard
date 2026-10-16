# Current non-driving continuation

The user reopened all remaining work except driving on 2026-10-16.
See [NONMOTION_FOLLOWUP.md](../integration-acceptance/NONMOTION_FOLLOWUP.md) and its validation record for the
new candidate. The control bridge remains intentionally stopped for manual
handover; preserve that state across any separately approved deployment.
The historical windows and approvals below do not override this current record.

# MR 인계

기록 UTC: 2026-10-15T06:45:34.358571+00:00. source `22c7913c879afcca536a78d552dcdf98f0f53098` / base `7747ef7`. **전체 PARTIAL**: 실제 제품 코드와 software 통합은 적용·검증됐지만 MR-MS-003 policy_provider 미연결로 실행 시작이 차단된다. 먼저 PROGRESS, OWNERSHIP, INTEGRATION_REQUESTS와 VALIDATION을 읽는다.

제품 경로는 `mission workspace → additive API → MissionRoutes → 기존 MissionCoordinator → 기존 NavigationCoordinator → gateway`다. 별도 executor·ROS motion 우회 경로는 없다. 지도 중심 편집/검사/실행, 방문 상세, E1 초안/compile, run 조회·비교/export를 기존 미션 페이지에서 접근한다. 기존 advanced 주문/도식과 Cockpit 요약을 유지하며 client/polling owner는 하나다.

## 저장·실행 계약

1~32 stable visit, annotation_ref와 mission_local_pose 분리, semantic revision/CAS, active 정의 copy 요구, run immutable snapshot. 저장·validate·compile·run 생성은 motion을 만들지 않는다. 새 start와 매 dispatch는 최신 map/annotation/route/context/generation·effective 설정을 검사한다. heading override는 annotation 원본을 바꾸지 않고 실제 goal yaw로 전달한다.

마지막 hold·사후 확인까지 완료해야 completed다. 대기는 monotonic, pause 잔여 보존, resume holding은 재주행하지 않는다. 단계 token·request ledger로 중복/오래된 확인을 거부한다. goal ID/세대가 다른 성공은 방문을 완료시키지 않는다. cancel timeout·불확실 제출은 owner 유지/새 goal 차단이다. aborted/interrupted는 skip으로 재개 불가다. 저장 손상은 원본 bytes 보존/unavailable, restart는 paused 포함 interrupted이며 자동 ARM/resume/재전송이 없다.

저장/receipt 실패에도 pause/abort는 소유 goal 정리를 수행하며 audit_warning을 노출한다. 정의64/run32/receipt256/JSON512KiB/events·logs200/trajectory256 상한. maintenance/archive API 없음. export는 allowlist/token 제거/executable=false다.

## MR / MS 경계

MR active/paused/canceling의 공개 기존 경로는 `runtime.mission.blocks_navigation_goal()`이다. MR은 동일 lock에서 MS `require_context_idle()`과 `navigation_context()`를 읽는다. MS 미연결 시 실제 legacy read port를 사용하며 source 미상/설정 증거 부족은 실행 차단한다. pose sequence와 운영 source/process generation을 분리했다. alignment 증거가 없으면 identity transform을 만들지 않는다.

MR-MS-001/002는 MS 단독 공유 창에서 적용했고 software VERIFIED다. app/runtime/API inventory/workflow tests4개는 MS의 확인에 따라 MR coherent commit에 포함됐다. MR-MS-003은 PROPOSED/BLOCKED, MR-MS-004 추가 shared 수정은 PROPOSED다. MS 전용 source/UI/tests/docs, 사용자 지도·annotation·bag·영상·운영 root·서비스를 수정하지 말아야 한다. 새 공유 변경은 상호 확인된 단독 창에서 수행한다.

## 경로와 미지원 범위

작성선/원본 E1 geometry, actual native preview, dispatch preflight 계획, 관측 trajectory를 구분한다. live_plan은 unavailable이며 dispatch 계획을 최신 controller path라 부르지 않는다. run source_sha/runtime_sha는 null, runtime config 미확인이다. 실제 native adapter는 구현됐지만 자원 창 default false이고 native 호출은 NOT_RUN이다.

순차 STOP/TASK, none action, DEFAULT speed/NAV2_DEFAULT 도착을 지원한다. Nav2 action success는 물리 정지 증명이 아니다. photo/posture/dock, custom speed/tolerance, PASS_THROUGH/CORRIDOR/STRICT, SLOW_ZONE/WAIT_ZONE runtime은 거부한다. E1 원본은 보존하며 최대32 STOP 후보를 검토 후 저장한다. 주문 작업 의미의 자동 수입은 없다.

## 검증·다음 작업

source30개 manifest와 log hashes는 SOURCE_MANIFEST/VALIDATION에 있다. focused83 PASS(실제 MR/MS synthetic 교차8·NativePlanner synthetic transport4 포함), 전체 Python1939(skip2/fail0), Node381 PASS, Ruff·configured mypy4·syntax·diff·secrets PASS, Chromium96 PASS. 캡처는 synthetic UI fixture이며 주행 증거가 아니다. CSS 200% zoom PASS와 실제 browser zoom/touch NOT_RUN을 구분한다.

게시·CI는 아래 확정 기록을 참조한다. 다음은 MR-MS-003 계약 수락 후 read-only provider 연결·stale/정책 영향 검증이다. source rollback은 MR source commit만 검토해 정상 revert한다. 이전 strict reader와 새 coordinator 저장 필드의 data 호환성을 먼저 확인해야 하며 사용자 runtime root를 reset하지 않는다. data rollback과 service rollback은 별개이고 이번에 수행하지 않았다.

장비에 배포하지 않았다. 운영 서비스·카메라·SLAM에 가한 변경 없음. deployment/restart/initialpose/ARM/motion goal/실이동은 단계27의 별도 조건 전 수행 금지다. 이미 통과한 회귀를 변경 없이 반복하거나 외부 초안 apply 스크립트를 다시 실행하지 않는다.

## 원격 게시·CI 확정 기록

기록: 2026-10-15T06:57:10.887581+00:00 / KST 2026-10-15T15:57:10.887581+09:00. source `22c7913`와 문서 `b42b28f`를 origin/main에 정상 push했다. exact tip `b42b28f9a4fdbb98a60692e90c677aaf5f9ddf34`의 [CI 38694446361](https://github.com/Phjrab/robot-scope-ros2-dashboard/actions/runs/38694446361)는 **success**, UTC 2026-10-15T06:46:31Z → 2026-10-15T06:55:01Z다. Ubuntu24.04/Python3.12와 Ubuntu22.04/Python3.10 각각 Python1939(1938 PASS/skip1/fail0), JS381 PASS, Chromium96 PASS, 정적·secrets·의존성 감사·coverage74% 검사를 통과했다. skip은 optional rosbags backend 미설치다. 상세 job 시각·log hash는 CI.json, 로컬 dirty tree 실행과 원격 clean commit 검증의 구분은 VALIDATION.json에 있다.

이 기록은 source 변경 없는 문서 후속 commit으로 보존한다. 이후 문서 tip의 CI는 별도 확인하며, 위 run은 명시한 b42b28f만 검증한다. 전체 인수 PARTIAL과 MR-MS-003 software BLOCKED/native·실기 NOT_RUN은 그대로다. 장비/서비스 변경 없음. 다음은 소유권 수락 뒤 runtime policy provider 연결·실제 증거 검증이다.
