# 기능 보존표와 작업 경계

조사 기준: 2026-10-07, checkout `92194cad2f2f91add260791f2e73f86db6bcbd20`, remote `Phjrab/robot-scope-ros2-dashboard`. 시작 작업 트리는 clean. 기존 AGENTS.md의 main/push 기본 규칙은 사용자의 feature branch/local-only 요청으로 대체했다.

사용자가 지정한 팩은 저장소 루트에 없었다. 실제 읽은 위치는 workspace의 `prompt/dashboard-ui-redesign/robot-scope-ui-prompt-pack/{START_HERE,MASTER_PROMPT,01…06,ACCEPTANCE_CHECKLIST,REFERENCES}.md`. 팩은 사용자가 적용하라고 지정한 작업 명세로 사용하며, README의 과거 SHA/검증 결과를 이번 checkout의 증거로 간주하지 않는다.

| 기존 기능 | 기존 route / DOM / event / API | 새 접근 경로 | 보존 검증 |
|---|---|---|---|
| Overview·연결 상태 | #overview, connectionChip, /state, /control/status | Advanced / Overview, 상단 상태바 | overview_offline unit, dashboard offline E2E |
| Cockpit 3D·LOD·시점 | #cockpit, cockpitSceneCanvas, scene_host.js, shared pointcloud_transport | 기본 Mission Control / Cockpit | Cockpit lifecycle, point quality, camera persistence tests |
| floating panels·singleton | panel_registry/manager/view, launcher | Cockpit sensor launcher, task presets | panel/geometry/snap E2E·unit |
| layout·import/export·migration | layout_store/schema/migrations/library, localStorage | Cockpit Layouts + 기존 Edit/Apply | layout migration/persistence unit·E2E |
| 카메라 구독·perception | camera_demand.js, camera panels, /ws/camera | Observation/Capture + #sensors | camera demand·state·reconnect·cleanup tests |
| Safety·STOP | safety_hud.js, triggerEmergencyStop → /control/stop | 고정 안전 영역, Controls | mock STOP success/failure; focus-loss·lease·denied ARM tests |
| ARM·deadman·watchdog | control_input, session_contract, /control/* | Advanced / Controls | 기존 control unit·Python·E2E; gate/timeout 변경 없음 |
| Live Mapping | #mapping, liveSceneCanvas/liveMapCanvas, /mapping/* | Mapping: viewport + 설정 inspector | mapping smoke, viewport·no-write fixture |
| 저장 지도·다운로드·편집·crop | #maps, savedMapList, savedSceneCanvas/savedMapCanvas, /saved-maps/* | Saved Maps: 검색/preview/revision + 기존 tools | saved-map download/editor/crop tests |
| Nav2·초기 pose·readiness | #navigation, navigationMapCanvas, navigation_adapter, /navigation/* | Navigation + Cockpit Navigation preset | revision/readiness/takeover E2E·unit |
| Mission draft/execution | #missions, dashboardMissionHost, mission_client | Advanced / Missions, Cockpit Mission panel | mission unit·E2E |
| Route Planner·도식·음식 | #route-planner, dashboard_page, schematic/food controls | Advanced / Route Planner (기존 모든 하위 탭) | route-planner/schematic/food suites |
| Capture·dataset·model registry | #sensors, dataset capture feature, /datasets/*, /models | Capture / Perception: camera + 세션 설정 | capture·perception unit·E2E |
| ROS graph | #topics, topic table, /topics | Advanced / ROS Graph | topic filter fixture |
| Settings·service·diagnostics | #settings, lifecycle features, /system/* | Advanced / Settings | service/diagnostics denied mock·unit |
| offline experiments | /static/experiments.html | Advanced / Experiments | existing experiment tests |
| dedicated/fullscreen Cockpit | ?workspace=cockpit, window_mode.js | 기존 별도 창 버튼·named window | full-window bounds·reuse tests |

위험 액션: ARM/acquire, deadman/velocity/sport, Nav2 activate/goal, mapping start/save, map rename/delete/edit/crop, dataset start/stop/export, resolution apply, service/bridge lifecycle, model activation. 이번 실행은 static server + browser intercept만 사용한다. 실 API 쓰기·장비·운영 서비스 실행 없음. 테스트에서의 mutation은 in-memory mock 기록이다.

상태 fixture: connected synthetic camera/map, no Go2/ROS(503), absent cloud, stale camera/cloud, reconnect, corrupt/migrated layout, read-only lease, denied ARM, mock STOP success/failure, long text, narrow viewport. backend enum/payload/CSRF/ownership는 변경하지 않는다.


## 최종 보존 판정

위 표의 기존 접근 경로를 모두 유지했다. 기존 67개 mock UI 회귀와 JavaScript 340개 단위 검사의 결과·범위는 [VALIDATION](VALIDATION.md)에 있다. 대회/도식/모델/서비스 도구는 Advanced로 이동했으며 backend 기능·권한·payload를 삭제하거나 바꾸지 않았다. 실장비 검증은 별도다.

HUD는 Cockpit renderer와 별도로 기존 단일 control status poll을 사용해 visible route 전체에서 server-authoritative 상태를 읽는다. scene·camera·map·mission의 transport owner는 기존 모듈이다. 신호가 없는 renderer의 3D 로봇 모델은 PREVIEW이며 odometry 대체값으로 사용하지 않는다. Navigation의 `READY TO START`와 goal readiness/localization은 기존 서버 enum 의미를 유지한다.
