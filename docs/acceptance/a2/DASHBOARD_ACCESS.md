# 확장 기능 사용과 A1 배포 인계

통합 기준은 A0 지도·프리셋 수정까지 포함한 main `03b58a6c6565af88f811ecd43867407ddfc55631`이다. A0와 A1은 더 보기·top-actions에 자기 미게시 수정이 없음을 기존 채팅에서 확인했다. A2는 기존 bootstrap/host의 HTML 연결 지점을 사용한다. 실제 장비 적용판은 A1이 승인한 전체 SHA로 고정한다.

## 사용자가 여는 방법

기존 대시보드의 **더 보기 → 확장 기능**으로 `/extensions`를 연다. 데스크톱 상단에도 링크가 있다. 모바일에서는 더 보기 메뉴를 사용한다. 확장 화면의 **← Robot Scope**로 돌아간다. 다섯 항목은 모든 flag가 OFF인 경우에도 안내와 함께 표시된다. 실제 처리에 필요한 flag·권한·입력 조건은 각 항목에서 확인한다.

| 화면 | 클릭 순서와 사용 조건 |
|---|---|
| 여러 지도 합치기 | HTTPS 검토 코드 로그인 → 3D 지도 2개 이상 선택 → 기준 지도 → XY/3D 비교 → 필요 시 XY/Yaw·XYZ 대응점 → 자동 정합 → 겹침률·RMSE·경고 검토 → 후보 수락 → 새 PCD 이름 → 저장. 재목록·재조회된 ID/revision/SHA를 확인한다. |
| 장애물 3D 관측 | 검증된 C1 입력이 연결되면 기존 C3·RobotScene3D로 관측한다. 입력 미연결은 UNAVAILABLE, 만료는 STALE, 합성은 SIMULATED로 안내한다. |
| 콘 표시 | 관측의 CONES 스위치를 직접 켠다. 새로 연 관측 화면의 초기값은 OFF다. 합성 데모의 좌표와 높이는 독립 평면 가정으로 표시한다. |
| 주행 기록 재생 | 실행 A에 로컬 C6 `review.private.json`, 실행 B에 비교 파일을 선택한다. 속도·이전/다음·seek를 사용한다. 원본 시각, 목표 결과, 정지, ACK, 오차와 누락 근거를 따로 확인한다. |
| 성능 진단 안내 | 기존 C7 오프라인 명령과 제공된 검증 기록의 고정 SHA를 확인한다. 표시된 26개 용량 사례는 2026-11-05 로컬 합성 결과다. Jetson 성능은 NOT_RUN, 센서→화면 지연은 UNKNOWN이다. |

샘플 미리보기는 화면용이다. 저장에는 전체 원본 점을 사용한다. 후보 수락 후 새 PCD 저장을 명시적으로 실행해야 사본이 만들어진다. 저장 위치는 검토용 BundleStore이며 목록에 새 사본이 나타난다. 운영 지도·Nav2 적용은 A1의 별도 검증 절차를 따른다. read는 조회·미리보기, review는 계산·수락·사본 저장 권한이다.

## A1 설정

모든 환경변수는 기존 서버 프로세스에 적용하는 값이다. 먼저 로컬 파일 재생만 개방할 때의 권장 구성은 다음과 같다.

```ini
ROBOT_SCOPE_EXPANSION_REPLAY=1
ROBOT_SCOPE_EXPANSION_USABILITY=1
ROBOT_SCOPE_EXPANSION_MULTIMAP=0
ROBOT_SCOPE_EXPANSION_SCENE=0
ROBOT_SCOPE_EXPANSION_RUNTIME=0
```

지도·관측은 HTTPS, 계정 DB, 검토용 catalogue 또는 검증된 scene provider가 준비된 후 해당 flag를 1로 올린다. 예시 origin과 경로는 A1이 실제 서비스 계정·호스트에 맞춰 결정한다.

```ini
ROBOT_SCOPE_EXPANSION_MULTIMAP=1
ROBOT_SCOPE_EXPANSION_SCENE=1
ROBOT_SCOPE_EXPANSION_REVIEW_DB=/private-review/access.sqlite3
ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN=https://review.example
ROBOT_SCOPE_EXPANSION_RUNTIME=0
```

DB는 서비스 계정 소유의 0700 디렉터리와 0600 파일을 사용한다. DB 생성·코드 발급·회수는 기존 `review_access` CLI를 사용한다. 코드의 TTL은 발급 시점부터 계산된다. 출력 코드는 의도한 검토자에게 사설 경로로 전달하고 원문을 로그·Git에 남기지 않는다.

```sh
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" init
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" issue read --ttl 900
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" issue review --ttl 900
python -m robot_dashboard.expansion_integration.review_access "$REVIEW_DB" revoke "$GRANT_ID"
```

### HTTPS와 배포 영향

현재 앱 실행 CLI의 `uvicorn.run`에는 TLS 인증서 인자가 연결되어 있지 않다. A1은 승인된 TLS 종단 프록시를 구성하거나 공용 실행 진입점에 검토된 최소 TLS 패치를 적용한다. 기존 운영 프로세스 전체를 가져와야 하므로 단순 ASGI import 실행으로 운영 초기화를 대체하지 않는다.

- HTTPS 호스트명/SAN이 일치하는 인증서·체인과 만료 상태를 확인한다. 사설 CA를 쓰면 클라이언트의 신뢰 저장소에 CA를 배포한다. 검증을 완료한 HTTPS 주소를 사용자에게 제공한다.
- 같은 호스트의 프록시를 쓸 경우 backend 수신 주소와 `FORWARDED_ALLOW_IPS=127.0.0.1`을 명시적으로 제한한다. 프록시는 외부 `Host`와 Origin을 보존하고, HTTPS 요청의 `X-Forwarded-Proto=https`를 신뢰된 연결에서만 전달한다. WebSocket upgrade 전달도 구성한다. 다른 배치에서는 실제 신뢰 프록시 주소만 허용한다.
- `ROBOT_SCOPE_EXPANSION_REVIEW_ORIGIN`은 브라우저의 scheme·host·port와 정확하게 일치하는 origin이어야 한다. 경로와 후행 slash를 붙이지 않는다. SessionPolicy가 HTTPS·Host·Origin을 검증한다.
- 수신 주소·포트 변경은 기존 HTTP 클라이언트, 대시보드 WebSocket, health 조회와 배포 경로에 영향을 줄 수 있다. A1이 기존 이용 경로를 열거하고 새 경로에서 재검증한다. HTTP로 확장 페이지를 열면 준비 안내와 로컬 REPLAY를 사용할 수 있고, 검토 코드 입력은 HTTPS에서 열린다.
- 세션 쿠키는 Secure·HttpOnly·SameSite=Strict와 `/api/v1/extensions` 범위를 유지한다. flag ON, HTTPS 연결, 로그인, provider 결속을 각각 확인한다.

### catalogue와 관측 입력

기존 `configure_expansion(app, os.environ, review_inputs=ReviewInputs(...))` keyword가 유일한 추가 연결 지점이다. 상세 필드·시간/세대 거부 규칙과 공용 app.py 예시는 [A1_FIELD_HANDOFF](A1_FIELD_HANDOFF.md)에 있다. 이 작업에서 공용 app.py/app.js/index.html 및 Navigation 파일의 직접 수정은 0건이다.

- `maps_factory`는 승인된 로컬 지도 사본의 `SavedMapCatalog`, 실제 자격 metadata 조회, 독립 private bundle root를 기존 `compose_maps`에 전달한다. metadata의 원본 ID/revision/SHA, m 단위, frame·epoch, REPLAY/SYNTHETIC, 원본 session/DAG를 검증한다. 공용 운영 catalogue를 변경하는 callback은 연결하지 않는다.
- `scene`과 `scene_context`는 기존 C1 읽기 포트다. 현재 지도 ID/revision/generation, source/stream epoch, clock, 생산자 신원, 교정을 동일 snapshot에 결속한다. 실제 producer가 없는 상태는 503/UNAVAILABLE로 인수한다.
- RUNTIME은 기본 OFF이며 native protection 표시는 ADVISORY_ONLY다. 공개 안내 페이지는 private API/worker를 생성하지 않는다. 원본 PCD·기존 지도·프리셋·운영 파라미터의 변경 요청과 ROS 입력·제어 명령은 확장 기능 진입 과정에서 발생하지 않는다.

### 합성 데모와 C7

개발 환경에서 다음 명령으로 기존 합성 데모를 시작하고 `http://127.0.0.1:4192/`를 연다. 생성되는 정보는 독립 평면의 SIMULATED 자료다. 데모의 로컬 cookie 정책은 운영 검토 세션과 별도의 실험 설정이다.

```sh
python -m experiments.expansion_20261101.cone_display.demo --port 4192
```

C7 명령은 화면의 성능 진단 안내에 있다. `prepare`는 고정된 Git 객체를 읽고 `run`은 기존 baseline/bounded CLI를 실행한다. Git 객체와 Python/Node 의존성이 준비된 개발 환경에서 수행하며 원본 결과·입력 hash·설정 snapshot을 보관한다.

## A1 적용·확인·복구

1. 검증된 전체 SHA와 기존 release·서비스 설정·프록시 설정을 함께 기록한다. 배포 대상은 저장소의 Python/확장 static/C2 자산이며 추가 외부 CDN·웹 폰트 의존성은 0건이다. 이 문서에 따라 기존 설치 의존성을 사용한다.
2. 기본 OFF에서 더 보기→확장 기능의 다섯 안내, private API 404, 기존 대시보드·Navigation·STOP 경로를 확인한다. 이어서 REPLAY flag만 켠 상태의 로컬 파일 재생을 확인한다.
3. HTTPS에서 무세션 401, read의 mutation 403, review의 합성 2지도 후보 수락·새 사본 저장·재조회, 로그아웃과 만료의 401을 확인한다. 장비에 실제 지도 사본을 전달했다면 사본 hash와 운영 지도 선택을 별도 대조한다.
4. 실제 입력 연결 전 Scene은 UNAVAILABLE, 별도 합성 데모는 SIMULATED, CONES 초기값은 OFF다. 세대·권한이 바뀌면 관측 레이어가 정리되는지 확인한다.
5. 기능 회수는 해당 grant revoke와 flag OFF, 다음 승인된 시험창에서 설정 재적용으로 진행한다. 코드 복구가 필요하면 검증한 이전 release와 기존 서비스·프록시 설정을 함께 복원한다. 새 리뷰 사본은 독립 보관한다. 기본 OFF로도 공개 안내·진입 링크는 제공된다.

## A0 공용 UI 인계

A0의 `03b58a6`에 있는 지도·프리셋 변경을 fast-forward로 인수했다. 추가 링크는 A2 host가 응답 HTML에 삽입한다. 더 보기의 닫는 nav/details 구조와 top-actions hook에 의존하며, 경계 검사에서 삽입 링크와 전용 CSS 참조를 제거한 HTML이 원본과 정확히 같은지 비교한다. 메뉴 구조를 후속 변경할 때 이 검사와 실제 모바일 클릭을 실행한다. A2 전용 entry.css는 800px 이하에서 추가 상단 링크를 숨겨 더 보기 경로를 사용한다.

## 로컬 검증 기록

최초 브라우저 실행에서 모바일 상단 바와 첫 확장 링크가 겹쳤고, XYZ 대응점의 긴 숫자 목록이 가로로 넘쳤다. 메뉴 링크 위치와 해당 목록의 줄바꿈을 수정했다. 테스트의 flat XYZ 배열 해석과 대응점 경고 행 계산 오류도 별도로 바로잡았다. timeout 증가나 강제 클릭으로 처리하지 않았다.

최종 macOS 전체 Python은 3,701개 실행에서 실패 5·오류 59·skip 37이었다. 실패·오류의 이름은 A2 이전 회차와 일치한다. 최초에 추가로 발생했던 공개 route 기대값 실패와 native benchmark 오류는 최종 실행에서 해소됐다. 지원 Linux 결과는 게시 인계 메시지의 exact SHA CI와 함께 확인한다. 지원 Linux CI와 macOS의 기존 /proc 환경 차이는 이전 [HANDOFF](HANDOFF.md)의 설명을 따른다. 실제 지도 정합 정확도·콘 XYZ·Jetson 지연은 [현장 수집 계약](A1_FIELD_HANDOFF.md#다음-현장-시험의-최소-수집판정)에 따른 입력이 필요하다.

| 검사 | 로컬 결과 |
|---|---|
| 기본 OFF | 공개 GET /extensions 한 경로 추가, private API 404, expansion service import 0·추가 thread 0. 기존 index에서 추가 링크/CSS를 제거한 원문 일치 |
| 실제 제품 브라우저 | 14개. 390/768/1440px·양 테마, 기본 OFF 메뉴와 명시 STOP, HTTP 코드 입력 차단, 실제 TLS read/review·수동 XYZ·800점 저장/재조회, 만료·재생/비교·제어 쓰기 0 |
| 콘 브라우저 | 11개. 기존 독립 합성 demo, 초기 CONES OFF·Canvas 표시·TTL·세대·지연·탭 종료 |
| I0 Python | 52개 통과. 로컬 TLS 권한/출처·원본 보존·단계 경계 |
| JavaScript | 기본 실행 847개 통과·선택 2개 skip. 고정 C1 export/fixture를 제공한 두 선택 비교도 별도 통과 |
| 소스 검사 | 134개 JS 모듈 syntax, 변경 Python의 Ruff, diff 공백 검사 통과 |

기존 독립 콘 demo의 초기 탭이 REPLAY로 선택되는 회귀도 발견해 multimap→scene→replay의 기존 우선순위를 복구했다. HTTPS POST 응답에 대한 브라우저 디버거의 body 조회가 한 차례 실패해, 저장 완료 후 실제 catalogue→export GET으로 사본을 검증하도록 테스트를 수정했다. 첫 macOS 전체 실행의 독립 native 정합 benchmark 오류는 단독 재검사에서 통과했으며 최초 실패 로그를 보존했다.
