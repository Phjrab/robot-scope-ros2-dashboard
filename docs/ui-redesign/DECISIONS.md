# 구현 결정

- framework/backend/API는 유지한다. 신규 패키지·CDN·analytics 없음.
- 저장소 루트에 없는 프롬프트 팩은 사용자가 첨부한 실제 경로에서 읽었다. 다른 프로젝트는 변경하지 않는다.
- Advanced는 기존 hash route를 유지하는 의미 있는 group이다. 기존 UI action IDs와 이벤트가 연결된 노드를 삭제/복제하지 않는다.
- HUD는 하나의 server-authoritative projection과 기존 STOP callback을 공유한다. 다른 화면에서도 같은 안전 surface를 노출하기 위해 활성 생명주기를 scene과 구분한다.
- schema version/key 변경 없이 builtin을 정상 layout document로 적용한다. default fallback은 Observation이고 기존 storage raw를 덮어쓰지 않는다.
- 공통 palette/type/layout tokens는 styles.css의 root 한 곳에서 선언한다. polish/mission-control의 중복 root 선언은 제거했다. 기존 renderer/panel 동작은 유지하고 mission-control은 제품 shell·workspace 구성·safety typography를 소유한다. 과거 polish 테스트의 operational exclusion은 유지한다.
- 패널 host는 상단 도구 아래·inspector 왼쪽·관측 strip 위로 제한한다. 우측으로 이동한 HUD를 위해 쓰던 host 하단 78px reserve는 12px로 조정했다. 기존 geometry/schema·정규화·snap/resize 계약은 유지하고 실제 viewport의 padding/reserve를 검증한다.
- 빈 지도 catalog의 기존 Public demo cloud fallback을 유지한다. 실제 저장 지도/실시간 신호로 라벨을 바꾸지 않는다.
- 신규 기본 camera 때문에 기존 테스트의 2-panel gamepad fixture는 먼저 camera를 명시적으로 닫는다. 겹친 panel은 launcher로 먼저 focus하고 action을 눌러 실제 운영 동작을 검증한다. 강제 click으로 가림을 숨기지 않는다.
- Foxglove Layouts와 QGroundControl Fly View 공식 문서를 2026-10-07 재열람했다. 작업별 layout 재사용과 주 viewport/상태/도구 분리 패턴만 참고; 코드/자산 복제 없음.
