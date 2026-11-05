# A2 비주행 인수표

시작 기준은 통합 main dce1e88995e5989d63fab257ea55b8d7d2ab8e24다. 해당 SHA의 표준 CI와 I0 제품 CI는 SUCCESS로 인수했다. 아래 상태는 A2 변경 전의 출발점이다. 1차 실측은 ROUND1_RESULTS에 별도로 고정한다.

| ID | 인수한 경로 | 이번에 확인할 경계 | 최초 상태 |
|---|---|---|---|
| N00 | 기본 OFF bootstrap | 라우트·worker·화면 변화, 미설정 권한 차단 | INHERITED |
| N01 | C1 DI·same-origin | 제품용 읽기/저장 principal, 수명·로그아웃, A1 소스 결합 | NOT_RUN |
| N02 | Maps history | 지연된 poll 동안 상세 요청 유실 및 오래된 응답 | NOT_RUN |
| N03 | SavedMapCatalog→D1/C1/C2 | 2/3개·AB+C 전체 사본 저장, 재조회·계보·revision | INHERITED |
| N04 | C1→C3→Canvas | 합성 콘 시간·좌표·세대, private asset, 실제 codec | INHERITED |
| N05 | C6 parser→로컬 picker | seek/비교/요약 및 외부 전송 | INHERITED |
| N06 | C7 byte/queue/cache | 고정 입력 baseline·경계, 시간축별 측정 | INHERITED |
| N07 | I0 제품 host | 반응형·테마·긴 오류·키보드·재열기·cleanup | INHERITED |

실제 지도/생산자 교정/운행 기록/Jetson 측정은 A1 제공 사본에 한정한다. A2는 장비·운영 상태를 조회하거나 변경하지 않는다. 공용 진입점의 최종 적용과 배포는 A1이 담당한다.

## 2차 마감

| 항목 | 로컬 인수 | 남은 의존성 |
|---|---|---|
| N00 | PASS · 미설정·기본 OFF 호환, 합성 fixture 및 index 원문 검사 | 장비 설정 NOT_RUN |
| N01 | PASS · OWNER_IMPLEMENTED_OFFLINE. 실제 TLS/브라우저 로그인·읽기/저장 분리·한 번만 발급 교환·만료·로그아웃·폐기·지연 POST 재검증. 장면/asset의 문맥 바인딩 | A1의 운영 TLS·권한 설정과 실측 producer INPUT_REQUIRED |
| N02 | PASS · 첫 클릭 상세 읽기, 마지막 사용자 선택 우선, 지연 성공·오류와 지도/화면 세대 무효화 | 장비 의존성 없음 |
| N03 | PASS · 2/3개·AB+C 합성 사본, 증거 종류 및 null 세션 보존. 저장과 fused-input 재검토가 교착 없이 종료 | 실지도 정합의 현장 평가 INPUT_REQUIRED |
| N04 | PASS · 실제 C1/C3/Canvas + 합성 콘. 유효 빈 관측 0 / 만료 —. 비공개 opaque bytes·교정 누락 차단 | 실제 모델·XYZ·codec별 디코딩 INPUT_REQUIRED |
| N05 | PASS · 기존 C6 parser→타임라인·seek·비교·요약·재열기. 제어 요청 0 | 실제 자료 평가 INPUT_REQUIRED |
| N06 | PASS · C7 고정 입력과 byte/queue/cache 경계. 센서→화면 시간 UNKNOWN | Jetson 측정 INPUT_REQUIRED |
| N07 | PASS · 390/768/1440px 양 테마, 로컬 한글 폰트, 긴 오류, 키보드·터치, 세션 만료 시 정리·재생 보존 | 실장비 화면 NOT_RUN |

로컬 전체 Python의 플랫폼 차이와 정확한 검사 수는 HANDOFF에 있다.
