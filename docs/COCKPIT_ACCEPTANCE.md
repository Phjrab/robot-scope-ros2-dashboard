# Cockpit 통합 Acceptance

이 문서는 CWP-12의 software-only 결과와 실제 장비 결과를 분리한다. 결과는 다음 네 값만
사용한다.

- `PASS`: 같은 commit에서 해당 검증을 실행해 기대 조건을 관찰했다.
- `FAIL`: 실행했으며 기대 조건을 만족하지 못했다.
- `BLOCKED`: prerequisite가 없어 실행 또는 판정할 수 없었다.
- `NOT_RUN`: 이번 검증에서 의도적으로 실행하지 않았다.

Hardware가 없거나 live stream을 사용하지 않은 시나리오는 테스트 코드가 존재해도
`PASS`로 추정하지 않는다. motion 시나리오는 물리 리모컨 또는 E-stop을 가진 운영자가
한 건씩 감독하고, 실패하면 다음 motion 시나리오를 자동 진행하지 않는다.

## 최종 Cockpit 기능 목록

- Go2 model과 shared PointCloud를 사용하는 base 3D scene
- LOW/MEDIUM/HIGH bounded adaptive LiDAR LOD와 stale 표시
- Go2 Front/RealSense fixed-source Camera panel과 source별 단일 demand owner
- bounded floating panel move, resize, compact, focus, dock, tile, cascade와 recovery
- profile-scoped bounded layout preset/import/export
- 고정 Safety HUD, SOFTWARE STOP과 Layout Edit/Operate interlock
- 읽기 전용 Xbox Controller panel과 기존 control session 기반 UI shortcut
- exact revision 기반 Map/Localization panel과 같은 renderer의 3D overlay
- 기존 NavigationCoordinator를 사용하는 Navigation/Takeover panel
- server-owned annotation Mission 목록, 순서, progress, pause/resume/skip/retry/abort

## Architecture와 data ownership

| 데이터 또는 동작 | 권위자 | Cockpit 경계 |
| --- | --- | --- |
| control lease, frame, watchdog | 기존 control session/bridge | HUD와 Controller panel은 projection만 사용하며 자동 ARM하지 않음 |
| PointCloud transport | shared `pointcloud_transport.js` 1개 | Mapping/Cockpit demand를 교체하며 panel별 socket을 만들지 않음 |
| Camera transport | fixed source별 `camera_demand.js` owner | panel lifecycle token만 acquire/release |
| panel geometry/layout | browser Cockpit manager/store | motion 권한, revision 또는 server operation을 저장하지 않음 |
| map/localization/Nav goal | SavedMapCatalog와 NavigationCoordinator | exact ID/revision projection과 기존 action만 사용 |
| Mission execution | runtime-owned MissionCoordinator | browser는 bounded GET/strict mutation client이며 실행 상태를 localStorage에 두지 않음 |

Panel close, route leave, reload와 BFCache 복귀는 server motion을 성공으로 간주하거나 새 lease를
발급하지 않는다. Mission/Navigation cleanup은 panel DOM보다 긴 server transaction이다.

## Software-only acceptance

### Workspace와 panel lifecycle

| 시나리오 | 결과 | 자동화 증거 |
| --- | --- | --- |
| Cockpit route 20회 진입/이탈, scene owner 1개 | `PASS` | Node SceneHost behavior + Playwright route 반복 |
| panel open/close/drag/resize/focus/lock/recover | `PASS` | PanelManager behavior + Playwright interaction |
| drag 중 Operate/ARM lock 전환 cleanup | `PASS` | pointer cancel과 layout lock behavior |
| viewport resize와 corrupted layout recovery | `PASS` | geometry/layout schema behavior + Playwright resize |
| Safety HUD/STOP이 focus panel 위에 유지 | `PASS` | Playwright stacking/focus 시나리오 |
| BFCache page lifecycle에서 stale async fence | `PASS` | camera/log/dataset generation behavior tests |
| robot-off 1366×768, 1920×1080, 2560×1440 layout/FPS | `PASS` | 2026-08-30: horizontal overflow 없음, 정적 LOW 10K 26 FPS, console warning/error 없음 |
| browser native fullscreen 진입/이탈 | `BLOCKED` | in-app browser가 단축키 후에도 fullscreen/viewport 변화를 노출하지 않음; reference PC 수동 확인 필요 |
| 실제 background tab visibility 전환 | `BLOCKED` | 자동화 tab 전환에서 대상 page가 계속 visible; software lifecycle tests만 PASS |
| 해상도별 browser JS heap/RSS | `BLOCKED` | in-app browser가 page heap을 노출하지 않고 macOS process inspection이 제한됨 |
| 20개 이하 panel stress | `PASS` | registry singleton과 bounded z-order/route stress |

### Camera와 LiDAR

| 시나리오 | 결과 | 자동화 증거 |
| --- | --- | --- |
| Go2/RealSense 단독 및 두 source 동시 demand | `PASS` | CameraDemand/CameraPanel behavior + Playwright dual panel |
| camera stall, reconnect, close 중 late decode fence | `PASS` | generation/latest-frame behavior tests |
| pointcloud 없음, stale, malformed frame | `PASS` | projection/binary decoder fail-closed behavior |
| high budget와 adaptive LOD 전환 | `PASS` | typed-buffer/LOD behavior + Playwright quality transition |
| route 전환 후 PointCloud owner 중복 없음 | `PASS` | shared transport unit + Playwright 20 route cycles |
| 실제 Go2+RealSense 동시 LIVE와 viewer lifecycle | `PASS` | 2026-08-30 및 2026-08-31: Go2 11–14 FPS/1280×720, RealSense 15 FPS/640×480, source별 viewer 1; route 이탈 후 모두 0과 RealSense producer idle |
| 실제 RealSense relay restart 중 panel 복구 | `PASS` | 2026-08-31: 즉시 restart의 8090 재바인드 실패를 재현하고 `f48ef07` 배포; panel `STALE` 뒤 자동 `LIVE`, systemd active/NRestarts 0, dashboard/relay viewer 각 1과 producer 1 확인 |
| 실제 Go2 relay restart와 source 격리 | `PASS` | 2026-08-31: Go2 MainPID 교체 후 자동 LIVE(1280×720, 약 11.6 FPS), NRestarts 0; RealSense는 계속 LIVE, source별 viewer 1 유지 |
| 실제 1화면↔2화면 preview demand 정리 | `PASS` | 2026-08-31: 2화면 1+1 → 1화면 RealSense 1/Go2 0 → 2화면 1+1; Overview 이탈 후 모두 0, RealSense producer idle. WP07 formal supervised record와는 별도 관찰 |
| 실제 camera cable 분리 fault injection | `NOT_RUN` | 감독된 케이블 분리 시나리오로 명시적 보류 |
| 실제 XT16 high-rate cloud와 adaptive LOD 단기 검증 | `PASS` | 2026-08-28: LOW/MEDIUM/HIGH와 AUTO 하향 전환, shared transport 확인 |
| 실제 XT16 high-rate cloud 60분 | `NOT_RUN` | 단기 검증만 수행; 60분 renderer/socket/heap soak 미실행 |

### Control, Navigation과 Mission

| 시나리오 | 결과 | 자동화 증거 |
| --- | --- | --- |
| Xbox connect/disconnect와 held-button replay 차단 | `PASS` | Gamepad mapper behavior + Playwright synthetic controller |
| deadman release, browser lifecycle, LowState/bridge loss fail-closed | `PASS` | 기존 control/transport/safety HUD suites |
| manual → Nav와 Nav → Manual Takeover | `PASS` | Navigation adapter unit + Playwright cleanup 순서 |
| map revision conflict와 initial-pose safety gate | `PASS` | Navigation/map unit + Playwright revision conflict |
| Mission pause/resume, failed retry와 explicit skip | `PASS` | MissionCoordinator behavior + Playwright recovery route |
| Mission browser reload와 server restart interrupted recovery | `PASS` | Playwright reload + persisted coordinator behavior |
| Nav goal terminal failure가 Mission을 멈춤 | `PASS` | terminal failure/retry behavior; 자동 retry 없음 |
| 실제 sensor/LowState loss, bridge loss, Nav child crash 중 정지 | `NOT_RUN` | 실제 service/hardware fault injection 미실행 |

## 전체 테스트 결과

최종 CWP-12 working tree에서 실행한 결과를 기록한다. macOS host에는 Ubuntu 전용
`/etc/os-release`가 없어 installer test 한 건은 기존 환경 오류로 분리한다. 프로세스
timing test가 일시 실패하면 assertion을 바꾸지 않고 해당 test를 독립 재실행해 결과를
함께 기록한다.

| Suite | 결과 | 상세 |
| --- | --- | --- |
| Cockpit 전용 Node unit | `PASS` | 71/71 |
| 전체 JavaScript unit | `PASS` | 239/239; SavedMapCatalog `map_id` regression 포함 |
| frontend syntax | `PASS` | 48개 `robot_dashboard/static/**/*.js` 재귀 검사 |
| Cockpit Playwright | `PASS` | 13/13 |
| Playwright hardware-free E2E | `PASS` | 27/27, 기존 시나리오 삭제 없음 |
| Mission/API targeted Python | `PASS` | 13/13; strict schema, persistence, revision, lifecycle, recovery |
| CWP-12 documentation contract | `PASS` | 3/3 |
| 전체 Python | `BLOCKED` | 673개 중 672개 통과, macOS `/etc/os-release` baseline 오류 1개 |
| Python coverage | `PASS` | 전체 65%, MissionCoordinator 74%; 실패 1개 실행 결과도 포함 |

2026-08-31 follow-up: the installer test now verifies the Linux host-mismatch
gate on Linux and the earlier Ubuntu-only apply gate on macOS. Both paths keep
the filesystem unchanged and return failure. The current complete Python suite
is `PASS` at 796/796; no safety assertion was removed or weakened.

실행 명령:

```bash
npm run test:cockpit
npm run test:unit
node scripts/check_frontend_syntax.mjs
npm run test:cockpit:e2e
npm run test:e2e:ci
python3 -m unittest discover -s tests -v
python3 -m coverage run -m unittest discover -s tests -v
python3 -m coverage report --show-missing
```

Coverage는 static source contract만으로 대체하지 않는다. Mission coordinator behavior,
browser reconnect, route/panel lifecycle, camera late decode, PointCloud generation과 실제
Playwright multi-waypoint flow를 별도 behavior test로 유지한다.

## 성능 측정표

실제 sensor stream과 reference 장비가 없는 hardware-free fake backend 결과를 제품 성능값으로
사용하지 않는다. 아래 표의 미측정 값을 채우기 전에는 대회 성능 acceptance가 완료되지 않는다.

| 환경 | renderer FPS p50/p95 | PointCloud decode | Camera decode/render | control frame interval/jitter | WebSocket reconnect | main-thread long task | browser memory | Jetson CPU/memory | network throughput | 결과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1920×1080 Chromium | — | — | — | — | — | — | — | N/A | — | `NOT_RUN` |
| 2560×1440 Chromium | — | — | — | — | — | — | — | N/A | — | `NOT_RUN` |
| 저사양 관리 노트북 | — | — | — | — | — | — | — | N/A | — | `NOT_RUN` |
| Jetson local browser | — | — | — | — | — | — | — | — | — | `NOT_RUN` |
| 원격 PC browser | — | — | — | — | — | — | — | — | — | `NOT_RUN` |

측정은 10분, 60분, 3시간 시점마다 같은 commit, map, point budget, camera 조합과 network
topology를 기록한다. DevTools/브라우저 계측이 control loop의 source가 되어서는 안 되며,
Jetson CPU/memory와 network throughput은 read-only host telemetry로 별도 기록한다.

## 장시간 운용 결과

| 기간 | 환경 | 결과 | 관찰 |
| --- | --- | --- | --- |
| bounded automated route/panel stress | hardware-free Chromium/Node | `PASS` | renderer/socket/listener owner 상한 behavior 검증 |
| 10분 | reference live environment | `NOT_RUN` | live Camera/LiDAR/control telemetry 없음 |
| 60분 | reference live environment | `NOT_RUN` | CWP-12 필수 soak 미실행 |
| 3시간 | reference live environment | `NOT_RUN` | 장기 대회 운용 미실행 |

60분 이상 실행에서는 renderer 수, camera source별 viewer 수, PointCloud socket 수,
reconnect count, dropped frame, JS heap 증가량과 main-thread long task를 시작/종료 시점에
비교한다. 증가가 계속되면 `FAIL`이며 GC 후 안정화되는 bounded cache와 구분해 기록한다.

## Hardware acceptance

초기 CWP-12 software phase에서는 실제 장비를 사용하지 않았다. 2026-08-28 후속 검증에서는
commit `3642d75`를 Jetson에 배포해 dashboard restart, live Go2/XT16 관찰, camera demand
lifecycle과 읽기 전용 map panel을 확인했다. Control Bridge, FAST-LIO, mapping과 Nav2는 시작하지
않았고 initial pose, goal, map mutation, dataset capture와 robot motion도 수행하지 않았다.

| 실제 시나리오 | 결과 |
| --- | --- |
| dashboard와 dedicated NIC/LowState freshness | `PASS` |
| 현재 commit의 Control Bridge lifecycle | `BLOCKED` — robot battery exhausted; software 18/18과 inactive/zero preflight만 PASS |
| Go2 camera LIVE와 exact viewer acquire/release | `PASS` |
| RealSense camera LIVE | `PASS` |
| XT16 rate와 adaptive LOD 단기 검증 | `PASS` |
| XT16 60분 rendering/owner/heap soak | `NOT_RUN` |
| 실제 Xbox Controller 연결/해제 | `BLOCKED` |
| deadman/browser close/software STOP/bridge loss 정지 | `NOT_RUN` |
| exact revision 저장 지도 read-only 표시 | `PASS` |
| 실제 localization과 initial pose | `NOT_RUN` |
| Nav goal, child crash, sensor loss와 Manual Takeover | `NOT_RUN` |
| 실제 annotation Mission pause/skip/retry/abort | `NOT_RUN` |
| Dataset 단독/동시 finalize, quota/reserve, 중단 복구와 보존 | `PASS` |

상세 수치, 최초 RealSense 실패와 2026-08-30 해결 결과는
[하드웨어 검증 기록](HARDWARE_VALIDATION_2026-08-28.md)의 CWP follow-up을 따른다.

실제 실행은 [하드웨어 인수 검증](HARDWARE_ACCEPTANCE.md)의 단일 supervised scenario,
물리 정지 수단, clear area와 stop-on-first-failure 원칙을 따른다.

## 알려진 제한 사항

- 현재 trusted LAN 모델에는 사용자 인증과 TLS가 포함되지 않는다.
- browser fullscreen, sleep/power 정책과 실제 GPU driver 차이는 hardware-free CI가 증명하지 못한다.
- arrival tolerance는 Mission metadata로 고정되지만 현재 Navigation의 기존 server policy를
  사용할 수 있다.
- fake backend의 frame/goal 완료는 real sensor timestamp, DDS graph나 physical stop을
  증명하지 않는다.
- hardware-free tests는 Jetson thermal throttling, Wi-Fi jitter와 실제 camera multicast
  비용을 재현하지 않는다.

## 대회 전 반드시 해결할 P0

1. reference remote PC의 1920×1080 및 2560×1440 Chromium 성능표를 live Camera/XT16으로 채운다.
2. 동일 commit으로 최소 60분 soak를 완료하고 socket/listener/heap 증가가 bounded임을 확인한다.
3. 물리 정지 운영자와 함께 deadman, browser close, LowState/bridge loss, SOFTWARE STOP을
   한 시나리오씩 검증한다.
4. 실제 대회 지도에서 localization, initial pose, Nav goal, Mission과 Manual Takeover를
   낮은 속도로 검증한다.
5. Jetson CPU/memory, disk reserve, network throughput과 browser power-saving 설정을 확인한다.

위 P0가 남아 있는 동안 software-only 결과만으로 대회 준비 완료를 선언하지 않는다.
