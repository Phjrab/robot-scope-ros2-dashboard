# Cockpit 운영자 가이드

이 문서는 대회 운영자가 Robot Scope의 Cockpit 안에서 센서 확인, 수동 조종,
Navigation 전환과 Mission 정리를 수행하는 절차를 설명한다. Cockpit은 safety owner가
아니다. 서버의 control watchdog, NavigationCoordinator, MissionCoordinator와 물리 정지
수단이 권위자이며 화면을 다시 열어도 자동 ARM이나 motion 재개는 발생하지 않는다.

## Cockpit 진입

1. Ubuntu ROS host에서 승인된 실행 mode의 dashboard와 필요한 control bridge가 이미
   실행 중인지 확인한다.
2. 관리 PC에서 `http://JETSON_IP:8088`을 열고 상단의 **Cockpit**을 선택한다. 선택 시
   화면 크기에 맞춘 전용 Cockpit 창을 자동으로 열거나 이미 열린 전용 창을 앞으로 가져온다.
   팝업이 차단되면 현재 대시보드의 내장 Cockpit으로 진입한다.
3. 접힌 고정 Safety HUD의 ARM, DEADMAN, BRIDGE, LEASE 요약과 항상 노출되는
   **DASHBOARD SOFTWARE STOP**을 먼저 확인한다. Robot Link, LowState, battery, command
   등 상세 항목은 **상세 펼치기**로 확인한다.
4. `WAITING`, `STALE`, `OFFLINE`, revision conflict가 있으면 motion을 시작하지 않는다.

Cockpit 진입·reload·BFCache 복귀는 기존 lease를 새로 발급하거나 motion을 다시 보내지
않는다. 화면이 복구됐다는 사실만으로 로봇 상태가 복구됐다고 판단하지 않는다.

## 별도 전체 창과 브라우저 Fullscreen

정보가 많은 Cockpit은 기본 대시보드 안에서도 사용할 수 있지만, 실제 운용에서는 별도
전용 창을 권장한다.

1. 로봇이 stationary이고 manual control이 `DISARMED`인지 먼저 확인한다.
2. **Cockpit** 메뉴를 선택하면 전용 창을 자동으로 연다. 내장 Cockpit을 URL이나 팝업
   차단 fallback으로 연 경우에는 제목 옆의 **CWP 전체 창**을 사용할 수 있다. 브라우저가
   차단하면 해당 Jetson 주소의 팝업을 허용하고 다시 누른다.
3. 성공하면 이름이 고정된 Cockpit 창 하나를 열거나 기존 창을 다시 앞에 표시하고, 원래
   대시보드의 내장 Cockpit은 Overview로 돌아가 센서 demand를 정리한다.
4. 전용 창에서 고정 Safety HUD와 **DASHBOARD SOFTWARE STOP**이 보이는지 다시 확인한다.
5. OS/browser chrome까지 숨겨야 할 때만 **브라우저 전체 화면**을 명시적으로 누른다.
   브라우저 정책이 거부할 수 있고 일반적으로 `Esc`로 빠져나온다.
6. **창 닫기**로 전용 창을 종료한다. 브라우저가 script close를 거부하면 같은 창이 일반
   대시보드 Overview로 돌아간다.

전용 창 열기는 화면 배치 전환일 뿐 제어 세션 인계가 아니다. 창 focus 변화와 명시적 전용
창 전환은 기존 fail-safe zero/DISARM을 수행할 수 있으며 새 창은 자동 ARM하지 않는다.
새 창에서 authoritative 상태를 다시 확인한 뒤 필요한 경우에만 별도로 ARM한다. 창을 닫는
행위는 server-owned Navigation, Mission 또는 Dataset을 중지·완료·finalize했다는 뜻이
아니다.

지원된 버튼은 한 browser context에서 같은 이름의 창을 재사용한다. 전용 URL을 여러 탭에
직접 복사하거나 다른 browser profile에서 동시에 열면 각 document가 별도 telemetry
consumer가 될 수 있으므로 그렇게 운용하지 않는다.

Competition Status와 Control Authority는 장면을 가리지 않도록 기본 접힘 상태다.
Competition Status는 MODE, LOCK, AUTHORITY를, Control Authority는 ARM, DEADMAN,
BRIDGE, LEASE를 접힌 상태에서도 갱신한다. 각각 **상세 펼치기/상세 접기**로 전환하며,
Control Authority를 접어도 **DASHBOARD SOFTWARE STOP**은 숨겨지지 않는다.

## Layout Edit와 Operate

- **Layout Edit**에서만 panel 열기, 닫기, 이동, resize, dock, tile과 preset 적용이
  가능하다.
- **Operate**는 주행 중 실수로 geometry가 바뀌지 않게 잠근 상태다. compact와 focus는
  상태 확인을 위해 계속 사용할 수 있지만 Safety HUD와 SOFTWARE STOP을 가릴 수 없다.
- manual lease가 active이거나 Navigation/Mission이 motion ownership을 가지면 Cockpit은
  Operate로 잠긴다. 강제로 Layout Edit로 바꾸지 않는다.
- drag/resize 중 ARM 또는 Navigation ownership이 생기면 진행 중 pointer operation을
  취소하고 마지막 bounded geometry로 정리하는 것이 정상이다.

## Panel 열기와 Focus

1. Layout Edit에서 **Sensor Launcher**를 연다.
2. Go2 Camera, RealSense, Map, Navigation, Mission 또는 Controller를 선택한다.
3. title bar를 눌러 앞쪽으로 가져오고 panel의 Focus 버튼으로 usable viewport를 채운다.
4. Focus 중에도 상단 Safety HUD와 SOFTWARE STOP이 보이는지 확인한다.
5. camera/mission/navigation panel을 닫으면 그 panel의 viewer 또는 polling demand만
   해제된다. control lease나 진행 중인 server operation을 정리했다고 가정하지 않는다.

## Xbox 연결

표준 Gamepad를 브라우저가 인식한 뒤 Controller panel에서 장치, `CONNECTED`,
input freshness와 LB 상태를 확인한다. 연결 직후 이미 눌린 버튼은 재생되지 않는다.

- D-pad 좌/우: 열린 panel 선택
- Y: Focus/복원
- X: Compact/Floating
- View: Sensor Launcher
- Menu: Layout menu
- 왼쪽 stick: 전후·좌우, 오른쪽 stick X: 회전
- LB: 주행 deadman
- B: DASHBOARD SOFTWARE STOP

연결 해제 시 선택·축·deadman 표시가 즉시 지워지고 Gamepad lease는 fail-closed해야 한다.
재연결 후에는 Controls에서 상태를 확인하고 별도로 다시 ARM한다.

## ARM과 Deadman

1. 로봇 주변을 비우고 평평한 바닥에서 물리 정지 수단을 든 운영자를 배치한다.
2. Bridge와 LowState가 fresh이고 publisher cardinality blocker가 없는지 확인한다.
3. Controls에서 Gamepad 또는 Keyboard를 선택하고 명시적으로 ARM한다.
4. Gamepad는 LB, Keyboard는 Shift, 화면 패드는 HOLD를 누르는 동안에만 주행한다.
5. deadman 해제, browser blur/close, 장치 연결 해제, stale input 또는 bridge loss가
   발생하면 zero/StopMove와 DISARM이 확인되어야 한다.

ARM은 한 번의 명시적 manual lease다. Navigation/Mission 완료, Manual Takeover 완료,
panel reopen과 controller reconnect는 자동 ARM하지 않는다.

## STOP의 의미

고정된 **DASHBOARD SOFTWARE STOP**은 현재 dashboard lease를 폐기하고 signed StopMove를
요청하는 software latch다. 네트워크·브리지·소프트웨어가 동작해야 하며 다른 ROS
publisher나 로봇 전원을 전기적으로 차단하지 않는다. 물리 리모컨 또는 E-stop을 대체하지
않는다.

STOP 해제는 stationary 상태, 물리 정지 수단, clear area를 다시 확인한 뒤 명시적으로
수행한다. STOP 해제 자체는 ARM이 아니며 이후에도 별도 ARM이 필요하다.

## Camera와 LiDAR stale 판별

- Camera는 source label, transport, FPS와 최신 frame age가 `LIVE`일 때만 신뢰한다.
  이전 frame이 보이거나 catalog entry만 존재하는 것은 live 증거가 아니다.
- LiDAR는 `LIVE`, point rate, frame age와 selected source identity를 함께 확인한다.
  `WAITING`은 아직 현재 session frame이 없다는 뜻이고 `STALE`은 최근 frame이 멈췄다는
  뜻이다.
- source stall 또는 relay restart 시 마지막 frame을 운용 판단에 재사용하지 않는다.
- 부하가 높으면 Cockpit point quality를 LOW 10K로 낮출 수 있지만 sensor freshness,
  Nav readiness, watchdog timeout이나 저장 원본을 완화하지 않는다.

Camera 또는 LiDAR가 stale이면 motion을 정지하고 원인을 확인한다. 화면이 다시 그려졌다는
이유만으로 Nav/Mission을 자동 resume하지 않는다.

## Manual Takeover

1. Navigation panel에서 **MANUAL TAKEOVER**를 한 번 요청한다.
2. active Mission이 있으면 Mission abort 확인이 먼저 끝나야 한다.
3. current goal cancel, Navigation stop, control lease release 순서를 기다린다.
4. 화면이 `READY_TO_ARM`이고 Nav inactive·lease released를 모두 표시하는지 확인한다.
5. 물리적으로 stationary인지 확인한 뒤 Controls에서 별도로 ARM한다.

15초 안에 cleanup이 확인되지 않으면 `FAILED`로 남는 것이 정상이다. 이 경우 자동 ARM하거나
manual input을 보내지 말고 `RETRY CLEANUP`, Navigation STOP과 물리 정지 수단을 사용한다.

## Mission Pause와 Abort

- **Pause**는 현재 Nav goal cancel이 terminal 상태가 된 뒤에만 `PAUSED`가 된다.
- **Resume**은 현재 map/annotation revision과 Nav readiness를 다시 확인하며 manual
  lease를 빼앗지 않는다.
- **Skip**과 **Retry**는 운영자가 누를 때만 한 번 실행된다. 실패 후 자동 무한 retry는 없다.
- **Abort**는 active goal cleanup을 수행하고 Mission을 terminal failed/aborted로 만든다.
- browser reload 후에는 server Mission 목록, current waypoint와 log를 다시 확인한다.
- server restart로 중단된 Mission은 자동 재개되지 않는다. `failed/interrupted` 또는
  안전한 `paused` 상태를 확인한 뒤 새 판단을 한다.

## 대회 시작 전 체크리스트

- [ ] dashboard와 control bridge 상태
- [ ] Go2 dedicated interface와 LowState freshness
- [ ] Xbox 연결 및 deadman 확인
- [ ] Go2 기본 리모컨과 물리 정지 수단 확보
- [ ] Go2 camera LIVE
- [ ] RealSense LIVE
- [ ] LiDAR LIVE와 point rate
- [ ] Cockpit layout 복원
- [ ] Cockpit 팝업 허용과 전용 창 하나만 활성
- [ ] 전용 창에서 Safety HUD와 STOP 접근 가능
- [ ] 브라우저 전체 화면 진입·`Esc` 복귀 확인
- [ ] live 검증 시 camera viewer·PointCloud demand 중복 없음
- [ ] STOP 버튼 접근 가능
- [ ] 지도 revision 확인
- [ ] Localization 상태 확인
- [ ] Mission revision 확인
- [ ] manual/Nav takeover 절차 리허설
- [ ] storage free space
- [ ] browser sleep 및 power saving 비활성화

한 항목이라도 확인되지 않으면 해당 motion 시나리오는 `BLOCKED` 또는 `NOT_RUN`으로 남긴다.
timeout, speed limit, freshness, cardinality 또는 disk reserve를 완화해 체크를 통과시키지 않는다.

## 대회 종료 후 로그와 Dataset 보존

1. Mission을 완료 또는 Abort하고 Navigation STOP과 lease release를 확인한다.
2. manual control이 DISARMED이고 로봇이 stationary인지 확인한다.
3. 진행 중 Dataset은 **STOP & FINALIZE**로 마무리한다. 브라우저를 닫는 것으로 finalize를
   대신하지 않는다.
4. Settings에서 redacted diagnostics ZIP을 내려받고 commit SHA와 운영 시각을 기록한다.
5. runtime의 지도, Mission state, Dataset과 private logs는 원본 호스트에 보존한다.
6. 외부 공유 전 IP, 경기장 지도, credential, bridge key와 private path를 검토해 제거한다.

실패가 있었다면 다음 motion test로 자동 진행하지 않는다. 물리 정지 후 현재 시나리오를
`FAIL`로 기록하고 관련 자료를 보존한 다음 원인을 조사한다.
