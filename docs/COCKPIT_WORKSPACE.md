# Robot Scope Cockpit Workspace 설계 계약

이 문서는 CWP-00에서 확인한 현재 코드 기준의 Cockpit 설계 계약이다. 조사
기준은 `main`의 `f91ef38affbd56a1b4f119aeeb958e38926ff5f4`이며, Cockpit을
구현하는 CWP-01 이후에는 이 문서와 실제 코드가 다르면 차이를 먼저 기록하고
소유권을 다시 확인해야 한다.

CWP-00 단계에서는 문서만 추가했다. 코드로 확인하지 못한 내용은 **확인 필요**로
표시한다.

### CWP-01 구현 기록

CWP-01에서 `#cockpit` route와 namespaced base workspace를 추가했다. Cockpit
`SceneHost`는 route가 보일 때만 `RobotScene3D`를 만들고 이탈, document hidden,
pagehide 시 `destroy()`한다. Go2 official-derived asset, 기존 pose/joint snapshot과
하나의 누적 PointCloud snapshot을 재사용한다. 기존 PointCloud WS/HTTP fallback은
`static/features/sensors/pointcloud_transport.js`의 단일 owner로 이동했으며 Mapping과
Cockpit route demand를 원자적으로 교체한다. 이전 transport session의 cached frame은
Cockpit에서 `LIVE`로 표시하지 않는다. Safety HUD와 sensor launcher는 계층만 예약한
비동작 placeholder이고 panel, control, camera 기능은 아직 추가하지 않았다.

### CWP-02 구현 기록

CWP-02에서 sensor와 무관한 범용 Floating Panel Manager를 추가했다. runtime state는
`id`, `panelType`, `title`, `mode`, `x/y/width/height`, bounded `zIndex`, `pinned`,
`locked`, `visible`, `restoreGeometry`만 투영한다. `panel_geometry.js`는 DOM 없이
clamp, edge/corner resize, compact/focus 전환과 exact restore, viewport recovery,
1~24 범위의 결정적 z-order 정규화를 담당한다. `panel_view.js`는 text-only DOM,
접근 가능한 action button, pointer capture 경계를 담당하고 `panel_manager.js`가
rAF-coalesced interaction과 content lifecycle을 소유한다.

현재 등록된 세 content는 명시적인 `mount/activate/deactivate/destroy` hook을 가진
데이터 비연결 placeholder다. Cockpit 이탈·document hidden·close 시 lifecycle과
진행 중 pointer capture를 정리한다. Panel layer 자체가 launcher 및 Safety HUD보다
낮은 stacking context에 있어 내부 z-index로 HUD 위에 올라갈 수 없다. 닫은
placeholder를 다시 여는 작은 임시 control만 제공하며, 실제 Sensor Launcher,
Snap, Dock, localStorage와 sensor/control 연결은 CWP-03 이후 범위로 남겼다.

### CWP-03 구현 기록

CWP-03에서 registry가 제공하는 fixed descriptor만 읽는 keyboard-accessible Sensor
Launcher를 추가했다. 현재 descriptor는 Camera, Map, Controller singleton 세 개이며
icon, label, default/minimum size를 표시한다. 모두 초기에는 닫혀 있고 launcher의
Enter/Space 또는 pointer 선택으로 열리며, 이미 열린 singleton은 새 DOM이나 content
runtime을 만들지 않고 bounded z-order의 앞으로만 이동한다. 실제 camera, map,
controller data/API/command는 연결하지 않았다.

DOM 없는 `snap_layout.js`가 viewport/panel edge snap, 8~32px configurable grid,
Alt 임시 우회, 좌·우·상·하 dock, 50:50 split, 2×2 tile, cascade와 compact fallback
계산을 담당한다. PanelManager는 drag rAF 안에서 계산 결과와 한 개의 preview만
투영하고 pointer 종료 시 preview를 정리한다. Dock은 `floating`의 `dock` 속성이며
undock용 floating geometry를 보존한다. 우선순위는 focus geometry, dock geometry,
일반 floating geometry 순서이고 focus 해제 후 기존 dock, undock 후 기존 floating
geometry가 복원된다. locked/pinned/focus panel은 자동 정렬 대상에서 제외된다.

Launcher와 layout controls는 panel stacking context보다 높은 고정 계층에 남는다.
Layout persistence, 실제 sensor transport, map/localization state, control lease와
control command는 계속 후속 CWP 범위다.

### CWP-06 구현 기록

CWP-06에서 `layout_schema.js`, `layout_migrations.js`, `layout_store.js`와
`layout_library.js`를 추가했다. 현재 layout schema는 version 1이며 UTF-8 JSON 및
profile별 전체 catalog를 32 KiB, preset 이름을 48자, profile별 preset을 12개,
panel을 24개로 제한한다. 실제 registry의 fixed panel type/id 쌍만 허용하고 unknown
field, 중복 ID, profile mismatch, 비정상 normalized geometry를 적용 전에 거부한다.

저장은 usable viewport 기준 normalized geometry를 사용하며 focus panel의 직전
non-focus `restore_geometry`도 함께 보존한다. 첫 preset은 자동으로 해당 profile의
default가 되고 reload 또는 profile 전환 시에만 자동 복원된다. Import는 bounded
JSON parse와 preview가 성공해도 현재 panel 및 storage를 바꾸지 않으며, 별도의
`APPLY IMPORT` 입력 후에만 저장·적용한다. localStorage 접근 실패나 손상 catalog는
control/robot 상태에 영향을 주지 않고 빈 기본 배치로 복구된다. lease, command,
telemetry, IP, path, frame과 runtime owner는 schema에 존재하지 않는다.

## 1. 제품 목적과 비목표

Cockpit은 Go2 URDF 모델과 실시간 LiDAR를 기본 장면으로 사용하고, 카메라,
지도, Localization, Controller, Navigation, Mission을 필요할 때 Floating
Panel로 여는 대회 조종 작업공간이다. 기존 화면의 데이터를 한곳에서 조합하되,
새 ROS/control 제품이나 두 번째 runtime을 만드는 기능이 아니다.

제품 목표는 다음과 같다.

- 기존 3D renderer와 검증된 sensor/control/navigation 경계를 재사용한다.
- panel 배치와 robot control 상태를 분리한다.
- 화면 구성 변경 중에도 STOP과 현재 모션 소유권을 항상 확인할 수 있게 한다.
- 보이지 않는 panel의 렌더링과 네트워크 수요를 중단하고, 다시 열 때 오래된
  callback을 거부한다.
- Overview, Live Mapping, Saved Maps, Sensors, ROS Graph, Controls,
  Navigation, Settings를 그대로 유지하는 추가 route가 된다.

비목표는 다음과 같다.

- 기존 페이지를 Cockpit으로 대체하거나 제거하지 않는다.
- ROS node, subscription, mapping/navigation/control manager를 복제하지 않는다.
- 브라우저가 임의 ROS topic, 카메라 URL, shell command, executable,
  filesystem path 또는 systemd unit을 지정하게 만들지 않는다.
- layout 저장소를 robot 상태, mission 실행 상태, lease 또는 인증 저장소로 쓰지
  않는다.
- CWP-00에서는 runtime 코드, route 또는 UI를 구현하지 않는다.
- 다중 모니터 pop-out, 계정 기반 workspace 공유와 기본 Go2 리모컨 통합은
  CWP-12 이후의 별도 범위다.

## 2. 확인한 현재 구조

### 2.1 브라우저

`robot_dashboard/static/index.html`은 hash route와 하나의 `.page-view`만 보이는
구조다. `robot_dashboard/static/app.js`가 route 전환과 아직 추출되지 않은
camera, mapping, saved-map, control, navigation UI 상태를 조합한다. 공용 API,
DOM, formatting, sticky log scroll은 `static/core/`에 있고, 추출된 기능은
`static/features/`가 각자의 bounded polling 및 mutation 상태를 소유한다.

`RobotScene3D`는 2D canvas 기반 3D renderer다. cloud, robot pose, trail,
joint positions, axes와 camera view를 renderer 인스턴스가 소유한다. `render()`는
중복 rAF를 coalesce하고 `destroy()`는 rAF, control binding, ResizeObserver와
pointer/wheel listener를 정리한다. 현재 앱은 Live Mapping, Saved Maps,
Navigation model용 인스턴스 세 개와 route 활성 중에만 존재하는 Cockpit 인스턴스를
만든다. 별도로 `animateRobot()`은 앱이
열린 동안 계속 rAF를 예약하고 활성 page에만 scene update를 적용한다.

현재 `pointcloud_transport.js`가 PointCloud WebSocket과 HTTP fallback을 하나만
소유한다. PointCloud는 `mapping`의 non-occupancy view 또는 `cockpit` route가 보이고
문서가 visible일 때만 필요하다. consumer demand 교체, connection/request generation과
최신-frame rAF queue로 늦은 결과를 거부한다. `pointcloud_stream.js`는 transport를
소유하지 않고 bounded binary decoder와 최대 1,000,000점의
`RegisteredCloudReservoir`를 제공하며, 누적 snapshot은 계속 `app.js` 한 곳에서
만든 뒤 활성 scene에 전달한다.

현재 camera UI도 `app.js`가 primary/secondary slot별 socket, decoder, reconnect
generation과 최신-frame decode queue를 소유한다. Sensors page가 visible할
때만 연결한다. 서버가 알리는 `max_active`는 브라우저에서 1~2로 제한된다.
layout preference에는 single/dual과 primary source ID만 저장한다.

`control_input.js`는 keyboard, pointer, standard gamepad 입력을 정규화하는 순수
모듈이다. lease, WebSocket, sequence, heartbeat, backpressure, ARM/DISARM과
STOP 상태는 현재 `app.js`의 control composition이 소유한다. 이 순수 입력
모듈이 control 권한을 소유하는 것은 아니다.

### 2.2 API와 runtime

FastAPI는 한 worker를 전제로 하고, `ApplicationRuntime` 한 인스턴스가 다음을
소유한다.

- 한 `RosAgent`
- saved-map catalog, dataset capture manager
- mapping, navigation, lifecycle coordinator
- operator-event timeline과 diagnostics service
- 공용 pipeline coordination lock
- response cache, PointCloud binary cache/lock, control binding
- bounded local robot discovery

`RosAgent`는 호환 facade다. 실제 mutable truth는 `robot_dashboard/ros/`의
`RosRuntime`, `RosGraphMonitor`, `SourceRegistry`, `TelemetryHub`, `CameraHub`,
`PointCloudHub`, `ControlTransport`, `NavigationRosGateway`가 나눠 가진다.
Cockpit이 facade의 private compatibility property를 새 소유자로 취급해서는 안
된다.

Camera API는 `go2_front`와 `realsense_color`만 허용한다. WebSocket은
same-origin 확인 후 정확한 source demand token을 발급하고 종료 시 그 token만
반납한다. `CameraHub`는 source별 실제 receiver를 한 번 시작하고 source의 마지막
demand가 사라질 때 정리한다. viewer는 전체 8, source별 4, 동시 active source는
2로 제한된다.

PointCloud API/WebSocket은 `PointCloudHub`의 동일 snapshot을 직렬화한다.
WebSocket은 same-origin을 확인하며 서버 안에 별도 ROS subscription을 만들지
않는다. binary frame은 공용 runtime cache를 사용한다.

Saved Maps는 configured root 아래에서 발견된 artifact에 opaque 24-hex ID와
64-hex revision을 부여한다. HTTP caller는 path를 전달하지 않는다. Navigation은
map ID, map revision과 parameter revision을 고정하고 `NavigationCoordinator`,
`NavigationJobManager`, `NavigationRosGateway`의 기존 transaction과 safety
gate를 통과한다.

### 2.3 현재 테스트 구조

- Python은 `tests/`의 `unittest` suite가 API, coordinator, ROS facade/component,
  filesystem, control 및 safety contract를 검증한다.
- JavaScript는 `tests/*.mjs`의 Node test가 순수 함수와 source/module contract를
  검증한다.
- `scripts/check_frontend_syntax.mjs`는 `static/` 아래 모든 `.js`를 재귀적으로
  `node --check`한다. Cockpit module도 그 디렉터리 아래에 두면 자동 포함된다.
- Playwright는 `tests/e2e/dashboard_backend.mjs`의 bounded mock backend와
  `dashboard.spec.mjs`를 사용한다. 현재 기존 12개 시나리오는 transport release,
  mutation 중복 방지, revision pinning, fail-closed 상태와 same-origin 거부를
  포함한다.

## 3. Cockpit 계층 구조

Cockpit 안에서는 다음 상대적 순서가 고정된다. 구현 시 기존 전역 `.topbar`의
`z-index: 20`이나 `.toast`의 `z-index: 40`과
그대로 섞지 않고 Cockpit stacking context 안에서 이름 있는 CSS custom
property로 정의한다.

```text
높음
  emergency/status notice 또는 기존 toast 호환 계층
  fixed Safety HUD + SOFTWARE STOP                 -- 절대 panel 아래로 가지 않음
  Sensor Launcher / layout mode controls           -- HUD의 reserved area 침범 금지
  focus panel                                      -- panel 범위의 최상단
  floating/compact/docked panels                   -- bounded z-order
  scene overlay (path, marker, selection)           -- pointer 정책 명시
  base 3D scene host (Go2 + shared live cloud)
낮음
```

Base scene은 workspace 전체를 채우고 panel layer와 독립된 host를 가진다. Panel
manager는 base canvas를 재부모화하거나 renderer 내부 상태를 직접 수정하지
않는다. scene overlay는 동일 scene host가 소유하고, panel DOM은 overlay geometry
소유자가 아니다.

Safety HUD가 차지하는 영역은 panel geometry의 usable viewport에서 제외한다.
Focus는 브라우저 fullscreen이 아니라 그 usable viewport를 채우는 panel 상태다.
따라서 Focus camera/map도 HUD와 STOP을 가릴 수 없다.

## 4. 데이터와 기능의 단일 소유권

| 데이터/기능 | 현재 단일 소유자 | Cockpit 사용 계약 |
| --- | --- | --- |
| ROS thread/node/executor | `RosRuntime` via one `RosAgent` | 기존 snapshot/API만 사용하고 node를 만들지 않는다. |
| ROS source 선택 | `SourceRegistry` | allowlisted `/api/v1/sources` 응답을 표시한다. layout에서 topic을 만들지 않는다. |
| PointCloud ROS state | `PointCloudHub` | 기존 선택 source의 bounded snapshot만 사용한다. 두 번째 subscription 금지. |
| PointCloud browser transport | 현재 `app.js`의 한 WS/HTTP fallback | 공용 transport owner로 추출하고 Mapping과 Cockpit이 snapshot subscriber가 된다. route별 socket 금지. |
| PointCloud decode/session cloud | `pointcloud_stream.js` decoder와 현재 `app.js` reservoir | frame은 한 번 decode/accumulate하고 immutable 또는 read-only snapshot을 scene consumer에 fan-out한다. |
| 3D render state | 각 `RobotScene3D` 인스턴스 | Cockpit `SceneHost`가 자기 canvas 인스턴스를 소유하되 transport/ROS state는 공유한다. inactive면 update를 중단하고 destroy 시 binding을 정리한다. |
| pose/joints browser state | 현재 `app.js`, `/ws/pose`, `/ws/joints` | 기존 최신 snapshot을 구독한다. Cockpit 전용 socket을 추가하지 않는다. 공용 store 추출 여부는 CWP-01에서 확인한다. |
| camera receiver/frame state | source별 한 `CameraHub` receiver | fixed source ID만 사용한다. backend의 token exactness를 보존한다. |
| camera browser transport/decoder | 현재 `app.js`의 source slot runtime | source-keyed demand broker로 추출한다. 같은 source를 보는 panel/page는 한 browser connection/decoder를 공유한다. |
| dataset camera demand | `DatasetCaptureManager`가 `RosAgent.camera_stream_open/close` 사용 | server-side capture lifecycle을 browser panel demand와 합치거나 대체하지 않는다. |
| manual control lease | `ControlManager` through `ControlTransport` | 기존 ARM/DISARM/WS 흐름만 사용한다. layout/panel manager는 lease를 읽거나 저장하지 않는다. |
| signed control bridge | `ControlTransport`와 standalone Go2 bridge | HMAC, epoch, sequence, freshness와 fixed topics를 그대로 유지한다. |
| control input mapping | `control_input.js`; session composition은 현재 `app.js` | Controller panel은 동일 input/session owner에 UI를 attach한다. 별도 lease/sequence loop 금지. |
| mapping process/operation | `MappingCoordinator` + `MappingJobManager` | 기존 API의 server-authoritative 상태와 cleanup을 사용한다. |
| saved maps/filesystem | `SavedMapCatalog` | opaque ID/revision/data URL만 사용한다. path를 layout이나 DOM에 넣지 않는다. |
| navigation transaction | `NavigationCoordinator` + `NavigationJobManager` | 기존 mutual exclusion, exact revision, confirmation, cleanup을 우회하지 않는다. |
| navigation ROS motion | `NavigationRosGateway` sharing `ControlTransport` | autonomous lease와 second preflight를 그대로 사용한다. |
| layout persistence | 신규 `WorkspaceStore` | 브라우저 UI 설정만 저장한다. robot 상태나 실행 상태는 저장하지 않는다. |
| panel runtime/geometry | 신규 `PanelManager` | DOM/geometry/lifecycle만 소유하고 sensor, control, navigation truth를 소유하지 않는다. |
| panel type/capability descriptors | 신규 `PanelRegistry` | fixed panel type, title, source mapping과 lifecycle factory를 등록한다. arbitrary plugin/URL/path 입력 금지. |
| Safety HUD presentation | 신규 `SafetyHudView`; truth는 기존 API owners | fail-closed projection만 렌더링한다. control grant나 freshness를 추론하지 않는다. |

### 4.1 PointCloud 재사용 전략

CWP-01에서 기존 `app.js`의 transport를 **하나의 공용
PointCloudTransport**로 추출하는 것이 선행 조건이다. owner는 다음 계약을
가진다.

1. consumer ID별 `acquire()`/`release()` 또는 subscribe disposer를 제공한다.
2. visible consumer가 하나 이상일 때만 `/api/v1/ws/pointcloud`를 하나 연다.
3. WebSocket이 열리지 않았을 때 사용하는 HTTP fallback도 owner 하나만 실행한다.
4. binary frame을 한 번 decode하고 stream ID/sequence를 검증한 뒤 latest
   snapshot을 consumer에 fan-out한다.
5. connection generation, request generation과 stream ID를 함께 fence로 사용한다.
6. 마지막 consumer가 사라지거나 문서가 hidden/pagehide 되면 socket, pending
   frame, reconnect timer를 정리한다.
7. Mapping과 Cockpit이 동시에 DOM에 남아 있어도 active demand만 등록하며,
   socket 수는 하나를 넘지 않는다.
8. SceneHost는 transport를 생성하거나 닫지 않고 subscriber disposer만 소유한다.

현재 live accumulated reservoir를 transport에 둘지 별도 shared cloud store에 둘지는
성능 측정 후 결정해야 한다. 다만 consumer마다 같은 binary frame을 다시 decode하거나
1M-point reservoir를 복제하는 설계는 금지한다. **확인 필요:** CWP-08의 adaptive
budget이 도입될 때 Mapping과 Cockpit이 서로 다른 표시 budget을 요청할 경우,
server acquisition budget과 consumer render sampling을 분리하는 정확한 정책.

### 4.2 Camera demand 재사용 전략

브라우저에는 fixed source ID를 key로 하는 **CameraDemandController**를 둔다.
동일 source의 panel 또는 기존 Sensors view가 여러 번 열려도 owner가 유지하는
WebSocket, decoder, reconnect generation은 하나다. consumer는 최신 frame/status를
구독하고 자기 canvas render cadence만 선택한다.

- 첫 visible consumer가 source connection을 열고 backend demand token을 얻는다.
- compact consumer는 rendering을 중단하거나 낮은 cadence로 그리되, 다른 visible
  consumer가 있으면 source connection을 닫지 않는다.
- consumer 하나가 닫힐 때는 그 subscription만 제거한다. 마지막 consumer가
  닫혀야 WebSocket이 닫히고 backend가 그 연결의 정확한 token을 반납한다.
- source 변경, reconnect, pagehide와 BFCache 복귀는 source generation을 올린다.
- panel resize는 canvas만 resize하며 decoder/WebSocket을 재생성하지 않는다.
- stale frame은 정상 영상처럼 남기지 않고 명시적인 STALE/age overlay를 쓴다.

Backend `CameraHub`는 여러 viewer token을 허용하지만 실제 receiver는 source별
하나다. Cockpit의 browser broker는 불필요한 같은-source viewer 연결까지
방지하는 더 좁은 UI 계약이다. **확인 필요:** 한 decoded frame을 여러 canvas에
복사할 때 지원 브라우저별 `VideoFrame`/`ImageBitmap` 수명과 최저비용 fan-out
방식은 실제 Jetson/원격 Mac 브라우저에서 측정해야 한다.

## 5. Panel lifecycle 상태 모델

Panel의 UI mode와 resource lifecycle을 분리한다. UI mode는 `compact`,
`floating`, `focus`, `closed`이고, content resource lifecycle은 다음과 같다.

```text
registered
  -> mount -> mounted/inactive
  -> activate -> active
  -> deactivate -> mounted/inactive
  -> destroy -> registered 또는 제거됨

closed --open--> mounted/inactive --workspace active--> active
active --workspace leave/document hidden/panel close--> deactivate
deactivated --panel close/route disposal--> destroy
```

Hook 계약은 다음과 같다.

- `mount(host, context)`: DOM을 한 번 만들고 disposer를 등록한다. network를
  자동으로 열지 않는다.
- `activate(session)`: visible 상태에서 필요한 shared demand를 등록한다.
  중복 호출은 idempotent해야 한다.
- `deactivate(reason)`: demand, animation, timer, pending decode를 정리하고
  generation을 올린다. robot 작업을 성공으로 간주하지 않는다.
- `destroy()`: DOM/listener/observer와 모든 disposer를 최종 정리한다. 여러 번
  호출해도 안전해야 한다.

`closed`는 runtime lifecycle 상태다. 저장 schema에서는 CWP-02의 최소 state와
호환되도록 `visible: false`와 마지막 non-closed `mode`를 보존한다. 다시 열 때
마지막 geometry를 복구하되 새 sensor/control session을 자동 복구하지 않는다.

Panel error는 해당 content만 `ERROR`로 만들고 panel chrome과 close/retry는
유지한다. Error, close 또는 focus 전환이 backend watchdog, STOP route,
navigation cleanup을 막아서는 안 된다.

## 6. Panel UI mode 정의

| Mode | Geometry | Content 정책 | 복구 정보 |
| --- | --- | --- | --- |
| `compact` | title/status가 보이는 최소 bounded 크기 | 고비용 render 중단 또는 낮은 cadence; control truth는 정상/stale로 표시 | 이전 floating geometry 유지 |
| `floating` | usable viewport 안의 x/y/width/height | visible content 활성 | 현재 geometry가 기본 restore geometry |
| `focus` | Safety HUD reserved area를 제외한 workspace 대부분 | content 활성, resize만 수행 | focus 직전 non-focus mode와 geometry를 정확히 저장 |
| `closed` | 화면에 없음 | deactivate 후 필요 시 destroy; demand 0 | 마지막 non-closed mode/geometry만 layout에 보존 가능 |

Dock은 CWP-03에서 floating의 배치 속성으로 추가한다. Pin은 panel을 항상
보이게 하는 layout 속성이지 control 권한이 아니다. `locked`는 해당 geometry
mutation을 막는 UI 속성이지 ARM 또는 navigation readiness가 아니다.

## 7. Layout Edit와 Operate 상태 전이

기본 mode는 `operate`다.

```text
DISARMED + NAV INACTIVE + explicit Edit -> layout-edit
layout-edit + Apply/Exit                 -> operate
ARM request accepted                    -> operate + geometry locked
NAV startup/active observed             -> operate + geometry locked
ARMED or NAV active                     -X-> layout-edit
DISARM observed                         -> operate 유지
NAV terminal/cleanup observed           -> operate 유지
```

- `layout-edit`에서만 drag, resize, dock, close, panel 추가를 허용한다.
- `operate`에서는 선택, compact, focus, focus 해제와 안전한 source view 전환을
  허용할 수 있다.
- ARM 또는 Nav active snapshot이 들어오면 진행 중 pointer capture를 취소하고
  마지막 일관된 geometry를 확정한 뒤 `operate`로 전환한다.
- stale/unknown control 또는 navigation 상태에서는 layout edit 허용을 보수적으로
  판단한다. 정확한 fail-closed 조건은 CWP-05 테스트와 함께 확정한다.
- layout mode 전환은 control WebSocket을 연결하거나 재연결하지 않는다.

## 8. ARM/DISARM과 layout lock의 관계

ARM/DISARM은 기존 control owner와 backend가 결정한다. Layout lock은 그 상태를
구독하는 파생 UI 정책이다.

- ARM 성공 전 layout lock을 control 준비 신호로 사용하지 않는다.
- ARM 성공을 관찰하면 edit pointer 작업을 취소하고 geometry만 잠근다.
- DISARM은 자동으로 layout-edit에 들어가지 않는다.
- layout-edit 진입은 DISARM, STOP clear 또는 Nav cleanup을 호출하지 않는다.
- panel 이동, focus, pin, preset 저장/복원은 lease를 만들거나 연장하지 않는다.
- layout에는 lease ID, binding, sequence, command, shared key 또는 bridge epoch를
  저장하지 않는다.
- control-owner content가 deactivate/close될 때는 기존 `failSafeDisarm`과 같은
  명시적 cleanup adapter를 호출해야 하지만, 그것을 유일한 정지 보장으로 삼지
  않는다. backend command/lease watchdog은 panel과 독립적으로 계속 동작한다.
- panel 재오픈, browser reload와 BFCache 복귀는 절대 자동 ARM 또는 motion
  resume을 하지 않는다.

Safety HUD의 SOFTWARE STOP은 layout manager가 아니라 기존 bounded control
mutation을 호출한다. STOP clear는 기존 local confirmation과 재ARM 요구를 그대로
유지한다. 한 번의 Xbox button press로 ARM, STOP clear, Nav start 또는 위험
action을 실행하지 않는다.

## 9. Fixed Safety HUD 계약

Safety HUD는 단순 panel이 아니다. 다음 이유로 panel registry, z-order,
compact/focus/close 대상에서 제외된 고정 계층이다.

1. 현재 모션 소유권, ARM, deadman, software STOP, lease, Go2 link, LowState
   freshness가 focus panel 뒤에 숨으면 조작 판단이 불가능하다.
2. panel drag/resize 오류가 STOP pointer target을 가로채면 안 된다.
3. panel lifecycle failure와 별개로 backend watchdog/cleanup 상태를 보여야 한다.
4. 좁은 viewport에서도 STOP과 control owner 정보가 먼저 남아야 한다.

HUD는 기존 `/api/v1/control`, navigation, state/health snapshot의
server-authoritative 값을 투영한다. fetch 실패나 stale telemetry에서는 cached
정상값을 유지하지 않고 `UNKNOWN`, `STALE`, `DISARMED` 또는 차단 상태로
fail-closed한다. SOFTWARE STOP을 물리 E-stop이라고 표시하지 않는다.

최소 표시 항목은 control source(`MANUAL`/`NAVIGATION`/`NONE`),
ARMED/DISARMED, deadman, software STOP latch, lease 존재 여부, Go2 link,
LowState freshness, battery, 현재 `vx`/`vy`/`wz`와 speed scale이다. 이 값들은
layout schema나 panel content의 cached 값이 아니라 기존 authoritative snapshot의
freshness와 함께 표시한다.

Panel의 최대 z-index는 HUD의 최소 z-index보다 작아야 한다. HUD root가
`pointer-events: none`을 사용하더라도 STOP과 필요한 control은 명시적으로
`pointer-events: auto`여야 하며, HUD reserved rect는 panel clamp 입력에 포함한다.

## 10. Viewport resize와 panel recovery

Panel geometry 계산은 DOM과 분리된 순수 module이 담당한다.

- 저장은 CWP-06 요구대로 usable viewport 기준 normalized 좌표를 사용한다.
- restore 시 현재 viewport, safe-area inset, Safety HUD, launcher/dock reserved rect를
  먼저 계산한 뒤 pixel geometry로 변환한다.
- title bar의 최소 grab 영역은 항상 viewport 안에 남긴다.
- width/height는 panel type의 bounded min/max와 현재 usable viewport에 clamp한다.
- viewport가 너무 작으면 dock/focus보다 접근 가능한 compact를 우선하며 content는
  overflow 처리한다. STOP/HUD를 줄이거나 숨기지 않는다.
- focus 중 resize하면 focus geometry만 다시 계산하고 원래 floating
  `restore_geometry`는 normalized 형태로 유지한다.
- viewport가 커져도 사용자 geometry를 임의 확대하지 않는다.
- off-screen/corrupted/NaN/Infinity geometry는 기본 preset 위치로 복구한다.
- resize/drag는 rAF로 coalesce하고 storage write는 pointer 종료 또는 명시적 저장
  시점에만 한다.
- recovery는 z-order를 bounded normalization한 뒤 적용한다.

화면 회전, monitor 이동, browser zoom, BFCache 복귀를 Playwright와 실제
브라우저에서 각각 확인해야 한다. **확인 필요:** macOS Safari와 대회용 Chromium의
safe-area 및 visual viewport 차이에 사용할 기준 API.

## 11. Layout schema 초안

영속 schema는 runtime panel object의 안전한 projection이다. 숫자는 0~1의
normalized usable viewport 좌표이며 snake_case를 사용한다.

```json
{
  "schema_version": 1,
  "name": "competition-drive",
  "profile_id": "go2",
  "scene": {
    "view": "robot-follow",
    "follow_robot": true,
    "point_size": 2.0,
    "range_m": 30.0
  },
  "panels": [
    {
      "id": "camera-go2-front",
      "panel_type": "camera",
      "source_id": "go2_front",
      "mode": "floating",
      "visible": true,
      "x": 0.65,
      "y": 0.08,
      "width": 0.30,
      "height": 0.28,
      "z_index": 3,
      "pinned": true,
      "locked": false,
      "dock": null,
      "restore_geometry": null
    }
  ]
}
```

초안 검증 규칙은 다음과 같다.

- `schema_version`은 필수이며 migration module만 이전 version을 변환한다.
- profile별 storage namespace를 사용한다. profile mismatch는 적용하지 않는다.
- name 48자, profile별 preset 12개, panel 24개, UTF-8 JSON 및 profile catalog
  32 KiB 상한을 적용한다.
- unknown top-level/panel field, unknown panel type, duplicate ID, unsupported source
  ID, non-finite/out-of-range 수치를 거부한다.
- panel title, capability와 endpoint는 registry가 제공한다. import 문자열을
  `innerHTML`로 렌더링하지 않는다.
- runtime `title`, DOM node, socket, decoder, timer, generation, current frame,
  raw telemetry와 pending operation은 저장하지 않는다.
- lease token, control binding, bridge key, credential, IP, URL, absolute path,
  raw child output와 map filesystem path는 절대 저장하지 않는다.
- map panel이 선택을 보존해야 한다면 opaque map ID만 저장할 수 있으나 revision
  mismatch 시 자동 실행하지 않고 재선택을 요구한다. **확인 필요:** CWP-09에서
  map selection을 layout preference로 보존할 제품 요구.
- focus 저장 시 `restore_geometry`에 직전 floating/compact 상태를 보존한다.
- `layout-edit/operate`는 session UI mode이므로 preset 적용 후 기본 `operate`로
  시작한다. ARMED/NAV 상태는 어떤 경우에도 저장하지 않는다.
- import는 parse -> validate -> preview -> explicit apply 순서이며 실패 시 현재
  workspace를 원자적으로 유지한다.

## 12. Map, Navigation, Mission 통합 경계

### Map과 Localization — CWP-09

Map panel은 existing saved-map data API와 navigation status를 읽는다. map path를
받지 않으며 opaque ID와 exact revision을 함께 유지한다. pose, path, annotation은
map frame/revision이 일치할 때만 표시하고 stale localization/TF는 마지막 정상
marker로 위장하지 않는다. Map panel open/close는 manual lease에 영향이 없다.
CWP-09에서는 map click goal이나 initial-pose mutation을 구현하지 않는다.

### Navigation — CWP-10

Navigation panel은 기존 NavigationCoordinator API의 UI adapter다. Start,
initial pose, goal, annotation goal, cancel, stop, clear costmaps는 현재 strict body,
same-origin, known-free validation, confirmation과 revision pinning을 그대로 거친다.
수동과 navigation의 상호 배타는 server가 계속 권위자다.

Manual Takeover는 cancel -> navigation zero/stop/deactivation -> autonomous lease
release 확인 뒤에만 manual ARM 가능 상태를 표시한다. 자동 ARM하지 않는다.
Panel close나 route change가 진행 중 cleanup을 취소하지 않도록 takeover operation은
panel DOM보다 긴 application adapter 수명을 가져야 한다.

### Mission — CWP-11

Mission은 신규 server-authoritative bounded state machine이 필요하다. browser
layout/localStorage가 실행 queue를 소유해서는 안 된다. mission은 exact `map_id`,
`map_revision`, `annotation_revision`과 allowlisted annotation ID만 사용하며 한 번에
goal 하나만 제출한다. pause/abort/takeover cleanup, duplicate request fencing,
restart 후 비자동 재개를 backend가 소유해야 한다. 임의 script, ROS topic, URL,
shell 또는 executable을 waypoint에 넣지 않는다.

## 13. 제어와 보안 불변 조건

후속 CWP는 아래 조건을 약화할 수 없다.

### Control

- exclusive lease와 manual/navigation 단일 모션 소유권
- deadman release 시 zero + DISARM, 50 ms browser tick과 server/bridge watchdog
- lease binding, monotonic sequence, heartbeat와 client command freshness
- browser socket backpressure fail-safe와 socket/page/visibility/blur cleanup
- software STOP latch, explicit confirmed clear와 이후 재ARM
- one-shot action confirmation, lease consumption과 action guard
- authenticated bridge readiness, LowState freshness와 publisher cardinality
- HMAC, bridge epoch/sequence, fixed command/status topic과 final StopMove
- server-authoritative speed/motion/action allowlist

Layout 또는 panel state는 위 항목을 grant, clear, extend, persist하거나 우회하지
않는다. UI close는 watchdog을 대체하지 않고 UI open은 motion을 재개하지 않는다.

### Web/API

- 모든 mutation과 browser WebSocket의 same-origin 확인
- Pydantic `extra="forbid"`, strict type, length/pattern/range bounds
- fixed API path와 fixed camera/source/service identifiers
- opaque map ID와 revision/parameter/annotation compare-and-swap
- no-store operational response와 bounded/redacted public diagnostic
- arbitrary ROS name, subnet, camera URL, filesystem path, executable, shell,
  systemd unit 또는 plugin surface 금지
- layout import의 크기/개수/schema bound와 문자열의 text-only 렌더링

현재 경계는 trusted LAN이지 인증 체계가 아니다. 외부 노출 시 필요한 TLS와
access control은 Cockpit layout 기능으로 해결하지 않는다.

## 14. 예상 신규 module과 책임

파일명은 실제 구현 전 충돌을 다시 확인하지만, 책임 방향은 고정한다.

### 공용 frontend owner

| 예상 파일 | 단일 책임 |
| --- | --- |
| `static/features/sensors/pointcloud_transport.js` | 기존 한 PointCloud WS/HTTP fallback, decode, generation과 subscriber fan-out |
| `static/features/sensors/camera_demand.js` | fixed source별 한 browser connection/decoder와 reference-counted consumer demand |
| `static/features/robot/live_state.js` | 기존 pose/joint 최신 snapshot을 여러 renderer에 read-only fan-out. 필요성은 CWP-01에서 확인 |
| `static/features/control/session.js` | 현재 `app.js` control composition을 공유해야 할 때만 추출하는 유일 lease/input/socket owner. CWP-05/07 이전 성급한 추출 금지 |

공용 owner를 `cockpit/` 아래에 두어 기존 Mapping/Sensors가 Cockpit module에
의존하게 만들지 않는다.

### Cockpit workspace

| 예상 파일 | 단일 책임 |
| --- | --- |
| `static/features/cockpit/workspace.js` | route enter/leave, 하위 lifecycle 조합, session generation |
| `static/features/cockpit/scene_host.js` | `RobotScene3D` canvas lifecycle과 shared snapshot attach/detach |
| `static/features/cockpit/cockpit.css` | Cockpit stacking context와 namespaced layout |
| `static/features/cockpit/panel_registry.js` | fixed panel descriptors, factories와 capability visibility |
| `static/features/cockpit/panel_geometry.js` | DOM 없는 clamp, normalized conversion, focus restore, viewport recovery |
| `static/features/cockpit/panel_manager.js` | runtime state, lifecycle hook, bounded z-order, mode transition 조합 |
| `static/features/cockpit/panel_view.js` | panel chrome DOM, pointer capture와 accessible controls |
| `static/features/cockpit/sensor_launcher.js` | registry 기반 open/availability UI; sensor truth 소유 금지 |
| `static/features/cockpit/snap_layout.js` | CWP-03의 pure snap/dock/auto-arrange 계산 |
| `static/features/cockpit/layout_mode.js` | CWP-05 layout-edit/operate pure state machine |
| `static/features/cockpit/safety_hud.js` | 기존 authoritative snapshot의 fail-closed 고정 표현 |
| `static/features/cockpit/layout_schema.js` | CWP-06 bounded schema parse/validation/projection |
| `static/features/cockpit/layout_migrations.js` | version 간 순수 migration만 담당 |
| `static/features/cockpit/layout_store.js` | profile-namespaced local preset atomic save/load/import/export 조합 |
| `static/features/cockpit/layout_library.js` | text-only preset/save/default/reset/import preview UI |

### Panel content

| 예상 파일 | 단일 책임 |
| --- | --- |
| `static/features/cockpit/panels/camera_panel.js` | source ID를 받는 공용 CameraPanel lifecycle |
| `static/features/cockpit/panels/controller_panel.js` | 기존 control session UI adapter; lease owner 금지 |
| `static/features/cockpit/panels/lidar_panel.js` | CWP-08 quality/status UI와 shared scene budget request |
| `static/features/cockpit/panels/map_panel.js` | revision-pinned read-only map/localization projection |
| `static/features/cockpit/panels/navigation_panel.js` | 기존 navigation API UI adapter와 cleanup 표시 |
| `static/features/cockpit/manual_takeover.js` | panel DOM과 분리된 takeover transaction presentation/controller |
| `static/features/cockpit/panels/mission_panel.js` | backend mission state의 bounded UI adapter |

### Mission backend — CWP-11에서만

`application/mission_coordinator.py`, strict request model/mission router와 bounded
mission persistence module이 필요할 가능성이 높다. 정확한 파일은 CWP-11 당시
현재 backend 구조를 다시 조사한다. Mission owner는 `ApplicationRuntime`에 정확히
하나만 조합하며 NavigationCoordinator를 우회하지 않는다.

### 변경 가능성이 높은 기존 파일

- `static/index.html`: Cockpit nav/page host와 script/style 연결
- `static/app.js`: route composition과 기존 transport/control state의 focused 추출
- `static/scene3d.js`: CWP-09 overlay나 CWP-08 quality hook이 기존 API로 부족할 때만
  additive 확장
- `static/styles.css`: 전역 nav/workspace integration만; Cockpit 상세 CSS는
  namespaced 파일
- `scripts/check_frontend_syntax.mjs`: 현재 재귀 수집으로 자동 포함되므로 변경은
  **예상되지 않음**
- `tests/*.mjs`, `tests/e2e/dashboard.spec.mjs`, `tests/e2e/dashboard_backend.mjs`
- CWP-11의 `application/runtime.py`, `api/models.py`, router composition과 Python
  tests

`app.js`, `app.py`, `ros_agent.py`의 크기만 줄이기 위한 재설계는 하지 않는다.
각 extraction은 기존 owner를 하나의 새 owner로 옮길 때만 허용하고 compatibility와
전체 suite를 유지한다.

## 15. CWP dependency map

```text
CWP-00  이 문서: ownership와 safety 계약
  -> CWP-01  Cockpit route + base SceneHost + single PointCloud transport
      -> CWP-02  sensor-independent PanelManager/geometry/lifecycle
          -> CWP-03  launcher + snap + dock + bounded arrange
              -> CWP-04  fixed-source camera panels + shared demand
              -> CWP-05  fixed Safety HUD + layout-edit/operate lock
              -> CWP-06  schema + profile presets + atomic import/export
                  -> CWP-07  Xbox UI navigation + existing control session adapter
                      -> CWP-08  adaptive PointCloud budget and performance policy
                          -> CWP-09  revision-pinned map/localization panel + overlays
                              -> CWP-10  navigation panel + explicit takeover
                                  -> CWP-11  server-owned revision-pinned missions
                                      -> CWP-12  integration, soak, performance,
                                                 hardware acceptance and operator docs
```

순서상 뒤 CWP의 module 이름을 앞 단계에서 빈 껍데기로 만들지 않는다. 각 CWP는
직전 결과를 실제 HEAD에서 검증하고 자기 acceptance 범위만 구현한다. Hardware가
필요한 검증은 software test green과 분리해 `PASS`로 추정하지 않는다.

## 16. 후속 작업의 주요 위험과 확인 필요 항목

1. **전역 frontend state:** PointCloud, camera, pose/joint와 control state가 아직
   `app.js`에 집중되어 있다. route를 먼저 추가하고 기존 코드도 유지하면 socket,
   rAF 또는 lease loop를 쉽게 복제할 수 있다.
2. **다중 canvas 비용:** transport를 공유해도 1M-point reservoir, scene sampling,
   camera frame draw를 consumer마다 복제하면 Jetson/원격 browser 비용이 커진다.
3. **lifecycle race:** page switch, visibility, BFCache, panel close와 reconnect가
   겹칠 때 old callback이 새 panel을 덮을 수 있다. 모든 async owner에 generation과
   idempotent disposer가 필요하다.
4. **geometry와 safety 겹침:** focus, 작은 화면, import layout이 HUD/STOP을
   가릴 수 있다. HUD reserved rect가 pure geometry 입력이어야 한다.
5. **control UI extraction:** Controller panel을 위해 기존 control composition을
   복사하면 lease, sequence, heartbeat와 cleanup owner가 둘이 된다. 기능을 붙이기
   전에 하나의 shared session owner로만 이동해야 한다.

실제 하드웨어 없이는 다음을 확인할 수 없다.

- Go2/XT16의 실제 cloud rate, frame 크기, pose/frame 정합성과 Cockpit 3D FPS
- Go2 multicast 및 RealSense MJPEG 동시 영상의 FPS, 지연, stall/reconnect
- Jetson CPU/memory/network와 원격 Mac browser의 장시간 증가량
- 실제 LowState/bridge freshness, deadman 정지와 software/physical stop 절차
- 실제 Nav2 start, localization, goal, cancel과 Manual Takeover 정지 시간
- 대회장 지도/annotation revision의 pose와 heading 정합성
