# 지도 중심 미션 workspace

실제 `mission_page.js`에 전용 workspace와 기존 advanced 미션/주문/도식 진입점을 연결했다. `.mr-workspace` scoped CSS와 기존 theme tokens를 사용한다. 공통 footer 규칙과 충돌하지 않도록 workspace footer를 local 배치한다.

## 사용 흐름

occupancy 지도 불러오기 → 지도/주석에서 방문 추가 → 목록 순서/복제/삭제·undo → 선택 방문 heading/hold/전후 확인 → 미션 저장 → 작성 검사 → native preview → FLEXIBLE compile → 별도 run 생성이다. start는 독립 요청이며 runtime 차단 이유를 표시한다. 편집 클릭/드래그와 가상 시작점은 goal/initialpose가 아니다. 운영 pose와 HOME 주석을 구분하고 HOME 복귀는 명시 방문으로 넣는다. pose가 없으면 현재 위치를 만들지 않는다.

상단은 이름·저장·운영 source/readiness·편집/검사/실행 모드, 좌측은 정의/E1/방문 목록, 중앙은 지도·범례·도구, 우측은 방문/구간 상세, 하단은 검사·run·이력/비교·상태다. 번호·yaw·현재/다음/완료/skipped 상태를 표시한다. pointer drag와 키보드 이동·순서 버튼, narrow panel tabs, pan/zoom을 제공한다.

focused/dirty 입력은 shared polling으로 교체하지 않는다. 늦은 저장 응답 뒤 추가 편집·CAS 충돌·reload draft·오래된 preview를 검증했다. 지도/annotation revision 변경은 stale 표시 후 명시 재연결을 요구한다. 이력을 다른 지도에서 조회해도 dirty editor와 원래 지도·주석을 보존한다. definition 삭제/복사와 token-free export를 연결했다.

## 경로·실행 표시

| 레이어 | 의미 |
|---|---|
| 파란 점선 | 작성 방문 연결선, collision-free 보장 없음 |
| E1 geometry | 원본 path/revision 보존, STOP 후보와 별도 표시·구간 선택 |
| 초록 native preview | actual_nav2_run=true인 검증된 ComputePathToPose 결과만 |
| synthetic preview | fixture 라벨, 실제 Nav2로 승격하지 않음 |
| 보라 dispatch 계획 | 각 leg 직전 preflight, 이후 controller path와 구분 |
| 주황 관측 궤적 | 운영 pose observation, map pin/epoch/gap별 분리 |
| 자홍 긴 점선 비교 | 같은 지도인 선택 이력의 epoch별 관측 궤적 |

unknown/occupied와 KEEP_OUT/지원되지 않는 zone의 표시·작성 검사·runtime 지원 상태를 구분한다. 개별 작성/E1 구간 상세는 검증 사유와 연결한다. live_plan은 unavailable이며 preview를 최신 controller path라 부르지 않는다. 근거 없는 ETA/위치오차 통계는 없다.

shared mission client의 동일 run을 workspace/Cockpit이 구독한다. phase·방문/다음점·대기 잔여·confirmation·pause/abort/retry/skip 상태를 읽는다. 수동 전환은 기존 adapter를 사용하며 cleanup/ready/failure를 표시하고 자동 ARM하지 않는다. disconnect/마지막 수신 시각을 표시하고 stale 운영 pose를 숨긴다. 공통 STOP/HUD와 기존 안전 owner를 유지한다. reload/패널 재진입은 start를 만들지 않는다.

## 검증 범위

전체 Node381/Chromium96 PASS에는 MR16개와 기존 cockpit/order/spatial/maps/SLAM 회귀가 포함된다. dark/light, 1440×900/1280×800/1024×768/768×1024/390×844, keyboard focus, CSS zoom200% fixture를 확인하고 캡처를 검토했다. evidence/의 모든 화면은 `UI fixture / 주행 검증 아님`이다. 실제 browser zoom200%·touch hardware는 NOT_RUN이다. fixture 화면·합성 궤적은 ROS/주행 검증으로 사용하지 않는다.
