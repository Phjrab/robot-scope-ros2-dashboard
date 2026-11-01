# I0 보안·안전 경계

- 별도 일반 clone과 integration/20261101-expansion만 사용했다. main/C0에 쓰기, merge/cherry-pick/reset을 수행하지 않았다. 운영 SSH/HTTP/DDS, Jetson/Go2 접속·배포·서비스 재시작·주행은 0회다.
- ExpansionOwner 권한 포트는 기본 없음이다. public UI는 권한이 아니며 private API는401이다. mutation에는 기존 Origin 검사와 별도 owner 정책이 모두 필요하다. 미설정 mutation은403, 미설정 데이터는503이다. synthetic header는 tests fixture에만 정의한다.
- C1 byte/depth/duplicate-field 계약 검사를 유지한다. async 오류는 error.code/error_detail로 표시하며 문자열로 승인하지 않는다. 클라이언트 경로를 열지 않고 서버 resolver와 검증된 metadata의 ID/revision/hash/frame/units/ancestry를 사용한다.
- 저장은 명시 review/accept/name/save 뒤 별도 immutable bundle에만 수행한다. legacy mapping session을 위조하지 않는다. full-source/DAG/원본 hash를 유지하며 current map/3D source/위치추정 bundle을 자동 적용하지 않는다.
- 관측 context는 snapshot에서 임의 채택하지 않는다. source/epoch/map/generation/frame/clock/calibration, 원본 ns 및 host receipt/age를 보존한다. PAUSED/REPLAY·늦은 응답은 LIVE TTL을 갱신하지 않는다. pose/joints가 없으면 공식 모델을 숨긴다.
- C4는 current CanonicalCorePorts만 명시 선택한다. 1 executing+1 latest pending, whole-frame rejection, close/rebind 폐기를 검증했다. 기본 observation sink, ROS publisher/subscriber가 없다. TTL/빈 목록으로 free ray를 만들지 않으며 clearing은 NOT_PROVEN이다.
- D3 공식 URDF/UNITREE_LICENSE를 보존했다. 새 보호는 ADVISORY_ONLY다. 기존 STOP/watchdog/lease/signed bridge/cmd_vel authority는 변경하지 않았다. 과거 D3 native5개 기록은 C4 ingress 성공 근거가 아니다.
- C6는 로컬 picker로만 읽는다. 64MiB/depth/number/ns/schema 제한과 원래 clock을 보존한다. HTML은 text node다. 목표 재전송/업로드가 없다. 공개 요약은 allowlist이며 private bundle·지도·bag·키·장비 경로는 Git에 넣지 않았다.
- secret scan은 기존 추적 파일과 새 import/추가 파일까지 실행했다. 문서에는 실제 패킷·좌표·개인 경로를 제외한 집계/검증값만 포함한다. CI artifact는 합성 화면/trace로 한정한다.

미완료: production authentication/qualification owner, opaque asset decoder, C4 genuine identity와 marking/clearing/planner/actuator 근거, 실제 교정·성능·센서→화면 clock mapping. 해결 전 활성 주행 보호로 사용할 수 없다.
