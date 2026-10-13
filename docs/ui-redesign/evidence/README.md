# 검증 로그

저장소 루트에서 실행한 실제 명령 출력이다. 텍스트 로그의 줄 끝 공백만 정리했다. 결과/오류/측정값은 수정하지 않았다.

- baseline-* 및 before-capture-events: 원본 UI/초기 환경.
- after-js-unit, after-cockpit-unit, after-cockpit-e2e, after-all-e2e, after-ui-e2e, after-architecture, after-python: 검증 결과. 최종 전체 E2E 67개는 Cockpit 21개를 포함한다.
- after-capture-events, browser-geometry-contrast: 최종 fixture 캡처의 network/error/mutation 및 실제 geometry/token 대비.
- iterations/: 구현 중 회귀 발견·수정·추가 확인 기록. 이 로그의 FAIL은 최종 판정과 구분한다. 현재 최종 FAIL은 기존 Python offline registration 1개뿐이다.

각 로그의 명령/exit code/검사 한계는 ../VALIDATION.md에 정리했다. 404 optional private map과 503 disconnected state는 의도된 fixture 경로다. 캡처와 mutation 기록은 실제 로봇 작업 증거가 아니다.
