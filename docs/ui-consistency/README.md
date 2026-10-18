# Robot Scope UI 통일 · 로컬 검증 (2026-10-18)

기존 Robot Scope의 IBM Plex 글꼴, 크기 역할, 녹색 테마 변수, 5px 모서리와 패널 구성을 최근 추가된 지도·관측·설정 UI에 적용했다. 기준 소스는 기능 담당이 완료한 `1b7e191b89e7`이며, 기존 로컬 커밋 3개를 보존하고 `main`에서 작업했다. 장비 실행·배포·공개 push는 수행하지 않았다.

## 변경 파일

| 파일 | 변경 내용 |
| --- | --- |
| `robot_dashboard/static/features/map_editor3d/editor.css` | 2D/3D 편집기의 테마·간격·버튼·초점 통일. 밝은 모드 안내 대비 복구. 모바일 도구 줄·파일 입력·출처 줄바꿈. |
| `robot_dashboard/static/features/maps/live_observation.css` | 관측 입력과 버튼, 경고·출처·좌표 표시 통일. 좁은 화면에서 2열 입력. 후보는 주황색, stale·거절은 오류색. |
| `robot_dashboard/static/features/maps/live_observation.js` | 기존 상태를 CSS가 읽도록 `data-status` 속성 한 줄 추가. 계산·데이터·판정·제어 조건 변경 없음. |
| `robot_dashboard/static/features/settings/mount_calibration.css` | 10–12px 중심의 작은 본문을 기존 13px 보조 정보·15px 본문/컨트롤 체계로 조정. 표·메타데이터·모바일 카드 정리. |
| `robot_dashboard/static/features/settings/settings.css` | 설정·진단 카드 공통 간격, 상태 줄바꿈, 44px 주요 컨트롤, 테마 초점 표시. |
| `robot_dashboard/static/index.html` | 설정 CSS 연결 1개와 표 스크롤 영역 2개의 키보드 초점·접근성 이름 추가. |

`app.js`, 지도 편집 컨트롤러, 정합 계약, API·ROS·장비 설정은 수정하지 않았다. UI에서 후보·미검증·stale·preview-only·런타임 미적용 안내를 보존했다. 2D/3D는 기존 하나의 편집 창에서 선택한 모드만 표시하며, 모드 전환 시 각 초안을 유지한다.

## 검증

| 검사 | 결과 |
| --- | --- |
| `.venv/bin/python3 -m unittest discover -s tests -v` | 2,288개 실행, 3개 건너뜀, 성공 |
| `npm run test:unit` | 501개 통과 |
| `npx playwright test --reporter=line` | 기존 브라우저 회귀 159개 통과 |
| 최종 관측 표시 수정 후 `live_observation.spec.mjs` | 2개 재검사 통과 |
| 지도·관측·진단 관련 JS 단위 검사 | 42개 재검사 통과 |
| `node --check` · `git diff --check` | 성공 |
| 합성 브라우저 화면 검사 | 밝음/어두움 × 1440×900·1024×768·390×844. 단계별 42개 컴포넌트 상태 + 실제 뷰포트 8개 캡처 |

전체 159개 브라우저 검사가 진행되는 동안 마지막 `data-status` 속성·상태색 수정이 추가되었으므로, 최종 파일에서는 영향받은 관측 2개와 전체 6가지 테마/폭 조합의 캡처 검사를 다시 실행했다. Python 기본 환경에서 먼저 실행한 검사는 의존성 누락 및 임시 소켓 제한으로 실패했고, 저장소의 기존 가상환경과 로컬 소켓 실행 권한으로 전체 검사를 다시 실행해 통과했다. 제품 코드를 그 환경 오류에 맞춰 수정하지 않았다.

자동 측정한 활성 DOM 텍스트에서 대비 4.5:1 미만의 반복 측정 항목은 변경 전 45건에서 변경 후 0건으로 줄었다. 변경 후 측정 최솟값은 약 5.59:1이다. 화면 전체와 패널 본문 가로 넘침은 0건이다. 좁은 화면의 표는 의도한 내부 가로 스크롤을 사용하며, 표 밖으로 넘친 콘텐츠와 구분해 JSON에 기록했다. 비활성 컨트롤과 canvas 내부 그리기는 이 DOM 대비 수치의 대상이 아니다.

2D 회전 초안·3D 영역 초안 보존, 모드 상호 배타 표시, stale 시 후보 중심 비활성화, 거절·소스 교체 시 형상 제거를 확인했다. 결과 표는 키보드로 초점을 옮기고 오른쪽 화살표로 스크롤했다. 진단 내보내기 버튼은 Tab/Shift+Tab으로 접근되며 3px 초점 테두리가 표시되고 고정 UI에 가려지지 않는다. 기존 브라우저 회귀는 지도 canvas의 Escape 취소를, 단위 검사는 Backspace로 마지막 점 삭제를 확인한다.

## 전후 캡처

**100장 모두 SYNTHETIC_BROWSER_FIXTURE_ONLY**다. 저장 지도·점군·pose·Depth·분석 결과는 UI 검사용 합성 데이터이며 실제 운영·센서·위치 정확도를 검증한 화면이 아니다. 장비 요청을 보내지 않았고 브라우저 요청은 localhost로 제한했다. 이미지에 표시된 정합 수치와 상대 각도도 합성 응답이다.

컴포넌트 캡처는 비교를 위해 촬영 순간에만 전역 상단바·안전 HUD·토스트·푸터를 숨겼다. `*-viewport.png` 16장은 실제 전역 UI를 유지한다. 제품 표시 동작은 변경하지 않았다.

| 화면 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 밝은 3D 편집 · 1440 | [전](captures/before/light-editor-3d-1440.png) | [후](captures/after/light-editor-3d-1440.png) |
| 어두운 2D 편집 · 390 | [전](captures/before/dark-editor-2d-390.png) | [후](captures/after/dark-editor-2d-390.png) |
| 밝은 관측 후보 · 1440 | [전](captures/before/light-observation-1440.png) | [후](captures/after/light-observation-1440.png) |
| 밝은 stale · 1440 | [전](captures/before/light-observation-stale-1440.png) | [후](captures/after/light-observation-stale-1440.png) |
| 어두운 관측 · 390 | [전](captures/before/dark-observation-390.png) | [후](captures/after/dark-observation-390.png) |
| 어두운 교정 · 1024 | [전](captures/before/dark-calibration-1024.png) | [후](captures/after/dark-calibration-1024.png) |
| 밝은 결과 표 · 390 | [전](captures/before/light-results-390.png) | [후](captures/after/light-results-390.png) |
| 밝은 진단 내보내기 · 390 | [전](captures/before/light-diagnostics-390.png) | [후](captures/after/light-diagnostics-390.png) |
| 실제 모바일 뷰포트 · 설정 | [전](captures/before/dark-calibration-390-viewport.png) | [후](captures/after/dark-calibration-390-viewport.png) |

[before.json](before.json)·[after.json](after.json)에 전체 측정 및 캡처 경로를, [source-manifest.json](source-manifest.json)에 수정 파일·이미지 SHA256을 보관했다. 원시 검사 로그는 [evidence/](evidence/)에 있다.

재현 명령: `node docs/ui-consistency/audit.mjs before`와 `node docs/ui-consistency/audit.mjs after`. `before`는 Git의 고정 기준 버전에서 해당 HTML·스타일·관측 렌더러를 읽어 응답하며 작업 파일을 되돌리지 않는다. 로컬 포트 4187·4188과 설치된 Playwright Chromium을 사용한다.

## 남은 사항

공유 파일 충돌이나 미완료 통합은 없다. 다른 기능 담당의 변경·커밋을 수정하거나 되돌리지 않았다. 장비 실행·운영 검증은 이번 UI 범위 밖이며 진행하지 않았다. 3D 다각형 꼭짓점 추가는 기존 포인터 방식이고, 키보드는 초점·취소·히스토리·폼 조작을 지원한다. 키보드만으로 꼭짓점을 추가하는 기능은 포함하지 않았다.
