# 기능 flag와 복구

flags.py는 아래 변수가 정확히 문자열 `1`인 경우만 켠다. 모두 기본 OFF이며 query/localStorage는 권한을 부여하지 않는다.

| 환경변수 | 효과 | 추가 조건 |
|---|---|---|
| ROBOT_SCOPE_EXPANSION_MULTIMAP | 지도 리뷰 화면/API | owner 인증·mutation 정책, catalogue/job/store |
| ROBOT_SCOPE_EXPANSION_SCENE | C1 관측 읽기 화면/API | 인증·별도 생산자 context/scene |
| ROBOT_SCOPE_EXPANSION_REPLAY | 로컬 파일 재생 화면 | 업로드 없이 사용자 picker |
| ROBOT_SCOPE_EXPANSION_USABILITY | C5 scoped helper | 활성 지도/관측 화면에서만 사용 |
| ROBOT_SCOPE_EXPANSION_RUNTIME | 명시 리뷰 factory 허용 | SCENE도 ON; synthetic/replay만. flag로 worker 자동 시작 없음 |

native flag는 없고 공개 상태는 항상 native=false, protection_mode=ADVISORY_ONLY다. C7은 별도 CLI이며 앱 import나 flag로 자동 실행되지 않는다.

전부 OFF이면 기존 index 파일/no-store 응답을 그대로 제공하며 확장 route/worker를 만들지 않는다. 기존 지도·Navigation·임무·STOP 동작은 기존 전체 E2E로 확인한다. ON은 화면 노출일 뿐 권한이 아니다. 기본 ExpansionOwner의 private API는 BLOCKED_AUTH다.

운영 owner 연결은 서버 초기화 단계에서 app.state.expansion_owner의 authorize/require_mutation 및 데이터 포트를 명시 공급한다. 권한 callback은 거부 시 HTTPException을 발생시킨다. mutation은 기존 require_same_origin도 통과해야 한다. 현재 main의 origin 검사만으로 인증을 대신하지 않는다.

로컬 합성 검토는 `python -m tests.integration_i0.fixture --all --port 4191`, 자동 제품 검증은 `npx playwright test --config playwright.i0.config.mjs`다. 권한과 source는 테스트 전용이며 운영 설정 예제가 아니다.

복구는 배포 설정에서 위 flag를 제거하는 것으로 시작한다. 환경변수 변경은 이미 실행 중인 프로세스에 소급되지 않는다. 승인된 로컬 검토 프로세스만 정상 lifespan 종료로 manager/worker를 닫는다. 브라우저 탭 전환/닫기는 abort·타이머·renderer·C3/C6/C5 handle을 해제한다. 로봇 서비스를 재시작하지 않는다.

immutable review bundle은 보존한다. 삭제·원본 덮어쓰기·운영 family 설치·현재 지도 전환은 복구에 필요하지 않다.
