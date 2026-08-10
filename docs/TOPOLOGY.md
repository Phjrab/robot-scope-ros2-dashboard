# 권장 호스트 및 네트워크 토폴로지

Robot Scope는 브라우저, dashboard/ROS 호스트, 로봇과 센서가 서로 다른 네트워크 역할을
가질 수 있습니다. Settings에서 IP를 선택하는 기능은 DDS interface나 LiDAR 목적지를
자동 재설정하지 않습니다.

## 역할

| 역할 | 실행 구성 요소 | 비고 |
|---|---|---|
| Browser client | 웹 브라우저 | 관리 LAN을 통해 dashboard에 접속 |
| Dashboard/ROS host | `robot-scope.service`, ROS subscriptions | 센서 DDS와 지도 파일에 직접 접근 |
| Control host | `robot-scope-control-bridge.service` | 보통 dashboard host와 동일 |
| Mapping/Nav host | Hesai driver, bridge, FAST-LIO, Nav2 | 보통 dashboard host와 동일 |
| Optional relay host | `robot-scope-xt16-relay.service` | XT16이 원래 송신하는 수신 호스트에서만 실행 |
| Go2 | 제조사 DDS와 카메라 송신 | 전용 유선망 사용 |
| XT16 | UDP point packets | 목적지는 현장 설정에 따름 |

## 현재 Go2 + XT16 참조 배선

다음 값은 현재 검증한 전용 `192.168.123.0/24` 배선의 역할 계약입니다. 다른 현장에서는
충돌 여부를 확인해 호스트별 설정을 바꾸되, 한 주소를 서로 다른 역할에 재사용하지 마세요.

| 주소/계정 | 역할 | 실행 구성 요소 |
|---|---|---|
| Go2 `192.168.123.161` | 로봇 본체 | 제조사 DDS, camera multicast |
| XT16 `192.168.123.20` | 외장 LiDAR | 원본 UDP packet 송신 |
| `unitree@192.168.123.18` | 로봇 탑재 Jetson, 기존 XT16 수신/relay host | `robot-scope-xt16-relay.service`만 실행 |
| `192.168.123.99` | 외부 dashboard/mapping Jetson의 전용 NIC | Hesai driver, XT16 bridge, FAST-LIO, Robot Scope, 선택적 control/Nav2 |
| 관리 PC/브라우저 | 별도 관리 LAN | `http://DASHBOARD_MANAGEMENT_IP:8088` 접속 |

Relay host의 초기 암호는 저장소와 문서에 포함하지 않습니다. 최초 접속은 대화형으로만
수행하고 [설치 가이드의 SSH 보안 설정](INSTALL.md#로봇-탑재-relay-host-최초-ssh-보안-설정)에
따라 암호 변경과 공개키 전환을 완료하세요.

## 가장 단순한 단일 호스트 구성

XT16이 dashboard host로 직접 송신할 수 있다면 릴레이를 사용하지 않습니다.

~~~text
Browser -- management LAN --> Dashboard/ROS host :8088
                                  | Go2 dedicated NIC
                                  +-------------------- Go2
                                  | XT16 sensor NIC
                                  +-------------------- XT16
~~~

이 구성에서는 dashboard host가 Go2 DDS, 카메라 multicast, Hesai driver, FAST-LIO와
Nav2를 실행합니다. 관리 LAN은 별도 Wi-Fi 또는 USB Ethernet을 권장합니다.

## 두 호스트 XT16 릴레이 구성

센서 목적지를 바꿀 수 없고 기존 수신 호스트의 처리도 유지해야 할 때만 제한된 단방향
릴레이를 사용합니다.

~~~text
XT16 -- original UDP --> Existing receiver / relay host
                                  |
                                  +-- allowlisted UDP copy --> Dashboard/ROS host

Browser -- management LAN -------------------------------> Dashboard :8088
Go2    -- dedicated robot LAN ----------------------------> Dashboard DDS
~~~

`robot-scope-xt16-relay.service`는 relay host에만 설치합니다. Dashboard host에는 Hesai
driver, XT16 bridge, FAST-LIO와 Robot Scope를 설치합니다. 릴레이는 센서 설정을 변경하지
않으며 저장소에 고정된 packet 계약과 맞지 않는 패킷을 전달하지 않습니다.

현재 참조 배선에서 relay service의 Unix 계정은 `unitree`, packet 수신 host는
`192.168.123.18`, 복제 목적지는 dashboard host의 `192.168.123.99:2368`입니다. Relay
host에 dashboard, Nav2 또는 control bridge를 중복 설치하지 않습니다.

다른 LiDAR 모델, 포트 또는 주소에 맞추기 위해 이 릴레이의 허용 조건을 느슨하게 바꾸지
마세요. 일반화가 필요하면 별도 driver 또는 현장별 adapter로 구현하고 독립 검증합니다.

## 관리망과 로봇망 분리

권장 인터페이스 역할은 다음과 같습니다.

| 네트워크 | 용도 | 공개 범위 |
|---|---|---|
| 관리 LAN | 브라우저, SSH, package update | 신뢰된 사용자만 |
| Go2 전용 LAN | DDS, 로봇 telemetry/command, camera multicast | 인터넷 공유 금지 |
| 센서 LAN | XT16 UDP와 driver | 필요한 호스트만 |

대시보드 실행 스크립트는 LAN 접속을 위해 `0.0.0.0:8088`에 bind합니다. Robot Scope의
일반 mutation API에는 사용자 로그인이나 TLS가 없으므로 인터넷, 행사 공용 Wi-Fi 또는
불특정 팀이 연결된 VLAN에 직접 노출하지 마세요. 넓은 관리망에서는 reverse proxy의
TLS와 접근 제어를 먼저 구성합니다.

## 호스트별 설치 모드

| 호스트 | 권장 mode | 설치 후 확인 |
|---|---|---|
| 관측 전용 개발 PC | `observer` | health API, Generic topic discovery |
| Go2 dashboard host | `go2` | DDS interface, `/lowstate`, camera |
| 수동 제어 host | `go2-control` | bridge key, fail-closed graph readiness |
| XT16 mapping host | `go2-xt16` | raw→converted→Laser map topic chain |
| Nav host | `go2-nav` | mapping 공유, `/scan`, TF, Nav2 lifecycle |
| 선택적 relay host | 현장별 relay service만 | packet counter와 dashboard raw topic |

Relay host는 dashboard 전체 설치가 필요하지 않습니다. 반대로 dashboard host에서 relay
service를 켜도 XT16의 원래 패킷을 받는 인터페이스가 아니면 아무 데이터도 복제할 수
없습니다.

## 환경 변수 계약

실제 값은 Git에 커밋하지 않고 호스트별 환경 파일 또는 systemd 설정에 둡니다.

| 변수 | 의미 |
|---|---|
| `ROBOT_SCOPE_ROBOT_IP` | 생존 확인용 로봇 주소 |
| `ROBOT_SCOPE_GO2_INTERFACE` | Go2 DDS/카메라 전용 NIC |
| `ROBOT_SCOPE_GO2_INTERFACE_CIDR` | 해당 NIC에 있어야 할 정확한 CIDR |
| `ROBOT_SCOPE_ROS_SETUP` | 기본값과 다른 ROS setup 파일을 쓸 때만 지정 |
| `ROBOT_SCOPE_UNITREE_SETUP` | 기본값과 다른 Unitree workspace setup 파일을 쓸 때만 지정 |
| `ROBOT_SCOPE_CAMERA_INTERFACE` | 허용된 카메라 multicast 수신 NIC |
| `ROBOT_SCOPE_WORKSPACE_ROOT` | 외부 ROS workspace 공통 root; 빈 값은 service 사용자 홈, custom 값은 절대 경로만 허용 |
| `ROBOT_SCOPE_LIVOX_SDK_PREFIX` | Livox SDK2 private prefix; 빈 값은 workspace root 아래 기본 경로 |
| `ROBOT_SCOPE_XT16_RELAY_HOST` | 선택적 XT16 relay host, 참조값 `192.168.123.18` |
| `ROBOT_SCOPE_XT16_RELAY_USER` | relay service/SSH 계정, 참조값 `unitree` |
| `ROBOT_SCOPE_OVERLAY` | Generic 모드 ROS overlay setup 파일 |
| `ROBOT_SCOPE_MAPS_DIR` | 관리 가능한 지도 폴더 |

Hesai와 FAST-LIO runner는 환경 변수로 임의 config를 받지 않고 각각 저장소의
`config/hesai_xt16.yaml`, `config/fastlio_xt16.yaml`을 고정 사용합니다. 다른 센서/배선에
맞춘 config는 review와 실기 검증을 거친 별도 commit으로 관리하세요.

서비스 예제에 보이는 사용자명, 홈 경로, NIC와 주소는 참조 장비 값입니다. 다른 사용자는
그 값을 그대로 사용하지 말고 installer가 현재 호스트에 맞게 생성한 설정을 검토하세요.

## 토픽 데이터 흐름

XT16 참조 흐름은 다음과 같습니다.

~~~text
Hesai driver        /lidar_points
XT16 bridge          /velodyne_points + /imu/body
FAST-LIO             /cloud_registered + /Laser_map + /Odometry
Robot Scope          live view, mapping save, navigation sensor gate
Navigation runtime   /scan + odom/base_link transforms
~~~

Live Mapping에서 선택한 시각화 토픽과 저장용 `/Laser_map`은 역할이 다릅니다. XT16 표시
소스를 고정한 경우 publisher가 잠시 사라져도 Go2 내장 LiDAR로 자동 전환하지 않습니다.
