# 실장비 1차 종료 뒤 bridge stop 진단·단일 보완 후보

LIVE_ROUND1_RESULTS와 CLOSED 영수증을 먼저 생성한 뒤 작성했다. 기존 FAIL 표는 보존한다.

확인 사실: 기존 bridge-service/stop API operation은 succeeded였지만, systemd는 TimeoutStopUSec=2s, Result=timeout, MainPID=0, ExecMainCode=2, ExecMainStatus=9, failed였다. journal에는 SIGINT handler의 KeyboardInterrupt가 rclpy Future.__del__에서 무시된 뒤 2초 후 SIGKILL된 기록이 있다. 그 stop 이후 관측 start는 전송하지 않았다.

현재 소스의 request_shutdown은 예외를 던지며 executor.spin을 빠져나오려 한다. Python finalizer 경계에서 예외가 삼켜지면 shutdown_requested가 true여도 spin이 이를 확인하지 않는다. 별도로 lifecycle._desired_state는 stop의 failed를 succeeded로 받아들인다. 관측 전용 gate는 정확히 inactive를 요구하므로 두 상태 계약이 충돌한다.

최소 후보는 go2_control_bridge.py에서 신호 handler가 플래그만 설정하고 기존 MultiThreadedExecutor를 0.1초 상한 spin_once 루프로 진행하는 것이다. 기존 stop_safely→executor 종료→node 파괴→ROS shutdown 순서·StopMove·200ms watchdog은 보존한다. lifecycle은 failed를 성공으로 표시하지 않고 service_stop_failed로 명시한다. failed를 inactive로 바꾸거나 gate를 낮추지 않는다. TimeoutStopSec2s, controller, 속도, tolerance, progress, 후방 가중치와 SDK 명령 경로는 바꾸지 않는다.

ROS 없는 실제 main 실행 회귀는 signal이 finalizer처럼 예외를 삼키는 경계, node 생성 중 signal, executor 실패 시 정지/소유권 정리를 검사한다. lifecycle 회귀는 stop 뒤 failed와 이미 failed인 상태의 거짓 성공·중복 변이를 차단한다. 관련62개 검사는 PASS이며 전체 검사 결과는 후보 제출 영수증에 기록한다. 이는 아직 장비 후보 성공이 아니다.

후보 적용이 필요하면 기존 idle·소유권을 재확인하고 사용자 dirty checkout·map·DB·control.env·프리셋은 보존한다. 현재 mode0600의 기존 robot-scope.env를 private 원격 백업하고 ROBOT_SCOPE_DIR 한 행만 exact-SHA 별도 release로 전환한다. 기존 API로 dashboard를 재시작한 뒤 candidate PID/cwd/source와 overlay·saved revision을 대조한다. 자동 시작되는 bridge에는 goal/lease/비영 명령이 없어야 한다.

2차 비교는 이동 없는 bridge start/stop1회만 한다. inactive/Result success와 기존 최종 stop 경로를 확인하지 못하면 반복 start/stop이나 timeout 조정을 하지 않는다. 이후 독립 관측 start도 기존 gate가 충족됐을 때1회만 허용한다. 실제 이동은 여전히 현재 현장·새 시험창 확인이 필요하다.

복구는 백업 selector를 그대로 복원하고 기존 API로 이전 release를 재시작하는 것이다. 이전5154761의 stop 결함이 다시 나타날 수 있음을 숨기지 않는다. 새 C0 PCD 사본은 보존하고 운영 source에 임의 적용하지 않는다. 장비 인증 정보·키·환경 원문·raw PCD·센서는 공개 Git에서 제외한다.
