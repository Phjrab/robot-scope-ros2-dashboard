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

## 11월 5일 후속 실측 결과

12:10 KST까지 A1 인계와 로컬 사본을 대조했다. 11:15 정지 관측 2건을 담은 사본의 SHA-256은 `5e7f51613de28be88ee2de946988ad20c96ee5053d821f6bc725b333a38faf19`이다. 이후 A1이 보관한 재생 확인서는 A2 확인서와 바이트 단위로 같았다. A1이 A0에 넘긴 지도 계보·주석과 정지 관측도 기존 자료였다. 세 현장 지표에 쓸 새 측정은 0건이었다. [A1 인계 명세](../a1/A2_INPUT_HANDOFF.md) · [지도 계보와 현장 기록](../a1/FIELD_SESSION.md)

| 평가 | 판정 | 사본에서 확인한 값과 필요한 근거 |
|---|---|---|
| N03 · 실제 지도 정합 정확도 | INPUT_REQUIRED | 두 자세는 FAST-LIO 로컬 좌표다. 선택 지도·revision·generation, 해당 관측의 지도 변환, 독립적으로 측정한 대응 기준점이 없어 지도 정합 오차(m)를 산출할 수 없다. |
| N04 · 실제 콘 3D 좌표 | INPUT_REQUIRED | 대시보드의 두 점군 프레임에 기록된 점 개수는 353개와 347개다. 콘 관측값은 null이며 원본 점 좌표와 해당 시각의 센서→지도 교정이 없어 콘의 XYZ(m)를 산출할 수 없다. |
| N06 · Jetson 센서 취득→화면 표시 지연 | INPUT_REQUIRED | 원본 센서 시각과 관측기 수신 시각은 서로 다른 시계에 기록됐다. 검증된 시계 대응과 같은 표본의 화면 표시 시각이 없어 종단 지연(ms)을 산출할 수 없다. |
| N05 · 실제 정지 이력 재생 | PASS · BROWSER / HISTORICAL_ONLY | 기존 로컬 재생에서 두 표본을 0→1→0으로 탐색했고 원본 자세 시각을 보존했다. 이번 대조에서 원본·재생 파일 해시 및 양쪽 확인서가 일치했다. |
