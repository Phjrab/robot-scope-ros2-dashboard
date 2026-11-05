# 1차 종료 후 원인 분석

| 관찰 | 원인과 구분 | 2차 확인 |
|---|---|---|
| N01 테스트 fixture만 보호된 API를 사용 | 제품 bootstrap이 빈 ExpansionOwner만 설치한다. 공용 웹 서버의 same-origin 검사는 사용자 권한을 부여하지 않는다. 확인된 제품 연결 공백 | 운영자가 범위와 만료를 명시해 발급한 일회용 코드→HTTPS 서버 세션. 승인된 로컬 사본으로만 지도 port 시험. A1 producer context 허용 필드 검증 |
| N02 history 첫 클릭 유실 | poll이 reading을 바꾸면서 UI 갱신을 알리지 않고 openHistorical의 실행 조건을 false로 만든다. promise gate 재현 | 상세 조회 우선순위·수명, 늦은 상태/상세/오류, 세대 전환, 화면 재열기 |
| N03 세션 미확인 값 | nullable C1 session을 C2 표시/preview pin에서 별도 문자열로 대체 | null을 end-to-end 보존, 해시·revision·DAG 확인 |
| N03 동시 리뷰/저장 멈춤 | 작성자와 분리한 검토에서 재현. 이미 융합한 지도 B의 review가 manager lock 상태에서 registry read를 기다리고, A의 publish가 registry write 상태에서 manager lock을 기다린다 | 고정된 순서로 두 작업 종료, 취소·revision·저장 원자성 회귀 |
| 첫 JS/HTTP/브라우저 실행 환경 오류 | Python 실행 경로, loopback 권한, 임시 경로의 symlink. 실제 디렉터리와 허용된 loopback으로 같은 코드 통과 | 안전 검사 유지 |
| 실자료·codec·장비 측정 부족 | 원본/context/codec 명세/기록이 전달되지 않았다. 현장 정확도와 지연은 판정 불가 | 해당 행만 INPUT_REQUIRED, 독립 기능 계속 |

2차 점검에서 C1이 합성 descriptor 두 개를 고정해 두고도 클라이언트가 제출한 REPLAY 표기로 작업을 접수하는 것을 재현했다. 기존 융합 사본 재조회도 첫 원본의 표기만 사용했다. 이제 C1은 이미 검증한 원본 전체에서 검토 표기를 결정한다. 전체 REPLAY는 REPLAY, SYNTHETIC이 섞이면 SYNTHETIC이며 LIVE 원본 및 잘못된 요청 표기는 409/REVIEW_EVIDENCE_MISMATCH로 거부한다. C2가 같은 규칙으로 요청한다. 기존 manifest 원본과 해시는 보존하고 재목록 시에만 원본별 표기를 읽는다. 양쪽 원본 순서의 저장/재조회를 회귀에 넣었다.

C3 상세 검사에서는 만료된 콘 입력의 개수를 0으로 표시하는 경로를 확인했다. 유효한 빈 관측은 0개, 만료·미확인은 —개로 표시한다. 명시적 401/403/409/503은 과거 장면 문맥을 지운다. 응답 지연 시에는 기존 source TTL 검사를 사용한다.

새 로그인 화면의 첫 DOM 검사에서는 로그아웃 요청이 끝나기 전에 로그인 입력이 보였지만 Enter 제출이 유실됐다. 요청 중에는 진행 상태를 보여 주고 완료 뒤 폼을 연다. 만료·백그라운드 조회 실패 때 이미 열어 둔 로컬 REPLAY를 유지하는 회귀도 추가했다.

마지막 HTTPS 점검에서 허가된 POST가 본문 첫 바이트만 보낸 뒤 다른 연결에서 로그아웃하고 나머지 바이트를 보내자, 대상 job의 404가 반환됐다. 권한이 사라진 요청이 job 조회까지 도달한 것이다. 세션을 사용하는 라우터는 유효한 JSON을 모두 받은 뒤 서비스 호출 직전에 권한을 다시 검사한다. 같은 두 TLS 연결 재현은 이제 401로 끝난다. 이미 접수한 작업은 기존 job의 취소·revision·원자적 게시 규칙을 따른다.
