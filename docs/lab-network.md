# 실습 네트워크 주소 기록 방법

실습실마다 달라지는 Jetson 관리망 주소, DHCP 임대, MAC 주소와 IPv6 링크 로컬 주소는
공개 저장소에 커밋하지 않습니다. 저장소에서 이미 제외되는 루트의 `.env.lab`에만
기록하고, 비밀번호·SSH 키·토큰은 어떤 경우에도 넣지 않습니다.

~~~dotenv
LAST_VERIFIED_AT=<ISO-8601 timestamp>
JETSON_HOSTNAME=<hostname>
JETSON_MANAGEMENT_IP=<current Wi-Fi or shared-network IPv4>
JETSON_PREVIOUS_IP=<historical IPv4, if needed>
JETSON_DIRECT_CIDR=<robot-facing static CIDR>
JETSON_LINK_LOCAL_IPV6=<session-scoped IPv6 with interface scope>
DASHBOARD_URL=<current dashboard URL>
ROBOT_IP=<robot IPv4>
LIDAR_IP=<LiDAR IPv4>
~~~

다음 실습 전에 `ip -br -4 address`, `ip route`, `ndp -an`, ping, SSH와 대시보드
health API를 다시 확인하고 `LAST_VERIFIED_AT`을 갱신합니다. DHCP 또는 링크 로컬 주소는
과거에 동작했다는 이유만으로 현재 주소라고 가정하지 않습니다.

Go2/XT16 전용 NIC를 인터넷 공유용 DHCP로 바꾸면 ROS 2/DDS와 센서 경로가 끊길 수
있습니다. 관리망은 Jetson Wi-Fi나 별도의 USB Ethernet 어댑터를 사용하는 구성이
안전합니다.
