# Robotics Mission Control

1440×900 기준 72px tool rail, 48px global status bar, 짧은 작업 heading, 328px context inspector, 36px observation strip. 중앙 3D/map/camera는 기존 renderer를 사용한다. 장면의 최소 목표는 cockpit 가용 폭의 60%; narrow/tablet에서는 inspector가 접히거나 아래로 흐른다.

토큰: bg #11161C, surface #1A222C, text #E9F0F5, muted #A7B7C6, action #59D3E5, boundary #516474, radius 5px. [IBM Plex 역할 토큰](../ui-typography/README.md): 영문 Sans, 한글 Sans KR, 기술 데이터 Mono; body 14~15px, labels 12px 이상, 패널 제목 16px. 숫자에 tabular-nums. warning/danger는 상태/STOP에 사용.

작업 preset은 패널 배치만 바꾼다. 사용자 저장값과 시점은 우선 복원하며 builtin 선택은 Edit mode에서만 가능하다. 이동/resize는 기존 pointer + launcher dock/tile/recover 버튼을 유지한다. 새로고침·선택·확대는 motion을 만들지 않는다.

Inspector: observation의 source/freshness/observed time와 현재 지도 exact revision, localization/readiness, Navigation draft 설명, Capture session을 작업별로 표시. STOP은 단일 기존 callback을 사용하고 pending/요청 응답/실패는 명시한다. 미연결은 robot/LiDAR/camera 각각 원인과 Settings 경로를 표시한다.

Fixture는 촬영 도구의 banner와 metadata로만 표시한다. 운영 페이지에는 demo를 임의로 붙이지 않는다. synthetic cloud/camera는 FIXTURE, stale은 STALE로 유지한다. ROS frame/도식 마커 의미는 변경하지 않는다.

접근성: semantic nav/aside/status, accessible names/title, focus-visible, reduced motion, wrap/overflow, 작은 화면·200% 검사. 인증 주장은 하지 않는다.
