export const CONTROL_RELEASE_ACK_TIMEOUT_MS = 180;

export function controlBridgeConnectionState(snapshot, requestFailed = false) {
  const bridge = snapshot?.bridge || {};
  if (requestFailed) return { tone: 'error', label: '원격 제어 Bridge 확인 실패' };
  if (bridge.authenticated === true && bridge.connected === true) {
    return { tone: 'ok', label: '원격 제어 Bridge 연결' };
  }
  if (snapshot?.target_supported === false || snapshot?.configured === false) {
    return { tone: 'error', label: '원격 제어 Bridge 차단' };
  }
  if (snapshot && ['error', 'offline', 'failed', 'stale'].includes(String(bridge.state || '').toLowerCase())) {
    return { tone: 'error', label: '원격 제어 Bridge 오프라인' };
  }
  return { tone: 'waiting', label: '원격 제어 Bridge 대기' };
}

export function renderHeaderConnections(ui, health = {}, snapshot = null, requestFailed = false) {
  const ready = Boolean(health.agent_ready);
  const targetConnected = health.robot_target_connected == null ? Boolean(health.robot_ip) : Boolean(health.robot_target_connected);
  const transport = health.ros_transport || {};
  const interfaceReady = transport.interface_ready ?? health.ros_interface_ready;
  const offlineViewer = Boolean(transport.offline_viewer ?? health.ros_offline_viewer);
  ui.connectionChip.className = `connection-chip ${ready && interfaceReady === true && health.robot_online ? 'ok' : ready ? 'waiting' : 'error'}`;
  ui.connectionLabel.textContent = !ready ? '직접 ROS 연결 끊김'
    : !targetConnected ? '직접 ROS 대상 해제'
      : !health.robot_online ? '직접 ROS 오프라인'
        : offlineViewer || interfaceReady === false ? '직접 ROS/DDS 오프라인 뷰어'
          : interfaceReady === true ? '직접 ROS/DDS 인터페이스 준비'
            : '직접 ROS 에이전트 연결';
  const bridgeState = controlBridgeConnectionState(snapshot, requestFailed);
  ui.controlConnectionChip.className = `connection-chip ${bridgeState.tone}`;
  ui.controlConnectionLabel.textContent = bridgeState.label;
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
