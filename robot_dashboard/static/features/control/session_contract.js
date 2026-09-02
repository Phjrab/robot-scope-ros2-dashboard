export const CONTROL_RELEASE_ACK_TIMEOUT_MS = 180;

export function controlBridgeConnectionState(snapshot, requestFailed = false) {
  const bridge = snapshot?.bridge || {};
  if (requestFailed) return { tone: 'error', label: 'Go2 Bridge 확인 실패' };
  if (bridge.authenticated === true && bridge.connected === true) {
    return { tone: 'ok', label: 'Go2 Bridge 연결' };
  }
  if (snapshot?.target_supported === false || snapshot?.configured === false) {
    return { tone: 'error', label: 'Go2 Bridge 차단' };
  }
  if (snapshot && ['error', 'offline', 'failed', 'stale'].includes(String(bridge.state || '').toLowerCase())) {
    return { tone: 'error', label: 'Go2 Bridge 오프라인' };
  }
  return { tone: 'waiting', label: 'Go2 Bridge 대기' };
}

export function renderHeaderConnections(ui, health = {}, snapshot = null, requestFailed = false) {
  const ready = Boolean(health.agent_ready);
  const targetConnected = health.robot_target_connected == null ? Boolean(health.robot_ip) : Boolean(health.robot_target_connected);
  const transport = health.ros_transport || {};
  const gatewayMode = health.connection_topology === 'onboard_gateway' || transport.mode === 'wireless_gateway';
  const interfaceReady = transport.interface_ready ?? health.ros_interface_ready;
  const offlineViewer = Boolean(transport.offline_viewer ?? health.ros_offline_viewer);
  ui.connectionChip.className = `connection-chip ${ready && interfaceReady === true && health.robot_online ? 'ok' : ready ? 'waiting' : 'error'}`;
  ui.connectionLabel.textContent = !ready ? (gatewayMode ? '탑재 Jetson 확인 실패' : '직접 ROS 연결 끊김')
    : !targetConnected ? (gatewayMode ? '탑재 Jetson 대상 해제' : '직접 ROS 대상 해제')
      : !health.robot_online ? (gatewayMode ? '탑재 Jetson 오프라인' : '직접 ROS 오프라인')
        : gatewayMode ? '탑재 Jetson 연결'
          : offlineViewer || interfaceReady === false ? '직접 ROS/DDS 오프라인 뷰어'
          : interfaceReady === true ? '직접 ROS/DDS 인터페이스 준비'
            : '직접 ROS 에이전트 연결';
  const bridgeState = controlBridgeConnectionState(snapshot, requestFailed);
  ui.controlConnectionChip.className = `connection-chip ${bridgeState.tone}`;
  ui.controlConnectionLabel.textContent = bridgeState.label;
}

export function overviewUnavailableReason(health = {}) {
  if (!health.agent_ready) return '에이전트 연결 끊김';
  const connected = health.robot_target_connected == null ? Boolean(health.robot_ip) : Boolean(health.robot_target_connected);
  if (health.connection_topology === 'onboard_gateway') return connected ? '탑재 Jetson 오프라인' : '탑재 Jetson 대상 연결 해제됨';
  return connected ? '로봇 오프라인' : '로봇 대상 연결 해제됨';
}

export function robotTargetLabel(health = {}, selectedType = '') {
  const identity = health.connection_topology === 'onboard_gateway' ? 'Go2 탑재 Jetson' : health.robot_type || selectedType || 'robot';
  return `${identity} · ${health.robot_ip || 'IP 확인 중'}`;
}

export function connectionOutcomeNote(robot = {}, bridgeState = '') {
  if (robot.restart_required) return ' DDS 재연결을 위해 해당 프로필로 대시보드를 다시 시작해야 하며, 그 전에는 Go2 제어가 차단됩니다.';
  if (robot.connection_topology !== 'onboard_gateway') return ' ROS 연결 설정은 별도로 확인하세요.';
  if (bridgeState === 'running') return ' 탑재 Jetson과 Go2 Bridge가 연결되어 있습니다.';
  if (bridgeState === 'scheduled') return ' 탑재 Jetson 연결 후 Go2 Bridge를 DISARMED·zero 상태로 시작하고 있습니다.';
  return ' 탑재 Jetson은 연결됐으며 Go2 Bridge 상태를 확인하세요.';
}

export function connectionButtonLabel(robotType) {
  return robotType === 'go2' ? 'Jetson + Go2 연결' : '연결';
}

export function createReleaseAckTracker(timeoutMs = CONTROL_RELEASE_ACK_TIMEOUT_MS) {
  const pending = new WeakMap();
  function settle(socket, acknowledged) {
    const entry = socket ? pending.get(socket) : null;
    if (!entry) return;
    pending.delete(socket);
    clearTimeout(entry.timer);
    entry.resolve(Boolean(acknowledged));
  }
  return Object.freeze({
    has: (socket) => pending.has(socket),
    settle,
    wait(socket) {
      if (!socket || socket.readyState !== 1) return Promise.resolve(false);
      return new Promise((resolve) => {
        const timer = setTimeout(() => settle(socket, false), timeoutMs);
        pending.set(socket, { resolve, timer });
      });
    },
  });
}
