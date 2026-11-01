# 조건부 prior 통합 검사 계획 — 합성 전용

기준 계약 `ambiguity-resolution/PRIOR_CONTRACT.json` SHA-256 `1f39f0b9b5a0b61e94570e050690c58dd8c04881598620b542ba2dce8c187a02`. 최신 지시상 staged-pair UI에서는 초안·범위·현재 정지 확인이 없으면 proposal POST를 보내지 않는다. no-prior 보존은 backend/기존 지도관리 global API 경로에 적용되며 UI에서 조용히 기존 global로 대체하지 않는다.

| 사례 | 필요한 관측·불변식 | 준비 상태 |
|---|---|---|
| 초안 없음, 범위 일부/전체 누락, 정지 체크 없음 | ① 부족 표시, proposal POST 0, start/pose/goal 0 | component browser probe 작성, 통합본 미실행 |
| 명시 초안·범위 + 두 retained 중 하나만 범위 안 | 합성 UI 작성값과 실제 ASGI POST의 map/pose/bounds/degree→rad 정확 일치, 실제 owner·global coordinator·manager, conditional proof, 원래 ambiguity true·global uniqueness false·실제 정확도 null; 확인 전 geometry 미저장 | probe 작성. 정확 통합본과 실제 retention 증거 생성 adapter 필요 |
| 원래 전역 결과 단일 + prior 범위 안/밖 | 범위 안은 ambiguity false 그대로 조건부 proof, 범위 밖은 PRIOR_NO_MATCH; 원래 단일이라는 이유로 prior gate 우회 금지 | synthetic unique-in/out probe 작성, 통합본 미실행 |
| 조건부 proof 전체 또는 원본 ambiguity 필드 누락 | geometry 미리보기·confirm 불가, 자동 POST 0 | 응답 변조 browser probe 작성, 통합본 미실행 |
| 동일 request_id/동일 prior, 동일 ID/변경 prior | 동일 요청은 같은 proposal과 solver 1회, 변경은 충돌, 자동 POST/재시도 없음 | probe 작성, 미실행 |
| 일치 0개/2개(높이·기울기만 다른 후보 포함), 품질 불명, 알려진 truncation | 거절, geometry 없음·confirm 없음. 평가 대상을 축소하거나 ambiguity를 false로 바꾸지 않음 | probe 작성; 실제 retention adapter가 유효·truncated 형식을 생성해야 함 |
| transient preparation 상태 조회 실패 | 사용자 원래 좌표 보존, 이전 초안은 미확인·활동 차단, 복구만으로 자동 재확인/전송 없음 | component probe 초안. 실제 지도 표시/앱 상태는 별도 전체 앱 검사 필요 |
| 초안 수정/범위 수정/지도 revision·generation 변경/늦은 응답 | 사용자 원본 변경으로 과거 결과 무효, 확인 해제 및 POST/confirm 자동 재시도 0 | 초안 변경 probe 작성. 늦은 응답·지도 변경은 계획 |
| 조건부 confirm과 stop | 서버 proof 재검증, conditional_prior_acknowledged=true를 포함하되 prior/proof를 client에서 재전송하지 않는 사용자 명시 confirm 1회, 실제 synthetic stop API의 exact session receipt 전에는 handoff 차단, proposal_confirmed source와 별도 conditional policy 유지, 원래 ambiguity true, confirm이 stop/Nav2/pose/goal을 자동 실행하지 않음 | probe 작성, 통합본 미실행 |
| confirm 처리 후 응답 유실 및 후속 상태 GET 실패 | 자동 confirm 재전송 금지, 불확실 상태 유지, 서버 readback 후에만 전이 | 서버 응답 유실 및 준비 상태 GET 실패 주입 probe 작성, 통합본 미실행 |
| ③ Nav2 mock → ④ 같은 초안 명시 송신·접수 → 정합 | Nav2는 오직 mock; UI 원본 초안 유지; 사용자의 명시 SEND 전 전송 0, 서버 0.25m/0.20rad 및 prior 양쪽 gate, 수신 receipt 전 alignment 0. 두 gate 중 하나라도 실패 시 거절 | **NOT IMPLEMENTED / NOT RUN**. 실제 handoff manager의 `preflight`, `snapshot_for_job`, `check_initial_pose`, coordinator receipt 경로를 유지하는 synthetic runtime과 전체 앱의 명시적 송신 adapter를 통합본 기준으로 작성 필요. fixture-only 가짜 수락을 실제 접수로 표현하지 않는다. |
| no-prior backend/지도관리 기존 경로 | 기존 v1 호환, 일반 ambiguity는 종전대로 거절 | 별도 실제 API 사례 계획. UI fallback은 허용하지 않음 |

품질 원본/모든 retained 후보/producer completeness 증거, source/session/calibration/expiry·one-use의 위변조 및 map frame 비항등 oracle도 별도 확인이 필요하다. 현재 fixture의 선택된 합성 map-family가 항등이므로 비항등 map-frame 통합을 주장하지 않는다. 실기 센서, 실제 NAV2, 로봇 정지·위치 정확도 및 현장 소유권은 모두 범위 밖이다.

C1.1 확정 필드 계약 `API_CONTRACT.json` SHA `d460de3cc9f922550047a126f00cb45874603afcbcb3d13796c37a8bc84da0a2`: confirm 동의 누락과 client proof 주입은 별도 거절 시나리오로 준비했다. 구현은 미완성이며 통합 실행은 하지 않았다.
