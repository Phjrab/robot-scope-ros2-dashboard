function bounded(value, fallback = '—') { return String(value ?? '').trim().slice(0, 256) || fallback; }

export function projectMissionInspector(input = {}, now = Date.now()) {
  const fresh = input.stateUpdatedAt > 0 && now - input.stateUpdatedAt >= 0 && now - input.stateUpdatedAt <= 2500;
  const connected = fresh && input.state?.health?.robot_online === true && input.state?.health?.agent_ready === true;
  const map = input.map?.map;
  const navigation = input.navigation?.navigation;
  const readiness = navigation?.readiness || {};
  const missing = Object.entries(readiness).filter(([, value]) => value !== true).map(([key]) => key);
  const capture = input.dataset?.capture;
  const camera = input.cameras?.sources?.find((source) => source.id === 'go2_front');
  const cameraProvenance = camera?.metadata?.data_provenance === 'SYNTHETIC_FIXTURE' ? 'FIXTURE' : camera?.metadata?.data_provenance === 'REPLAY' ? 'REPLAY' : '';
  return Object.freeze({
    robot: connected ? 'CONNECTED' : fresh ? 'NOT_CONNECTED' : input.stateUpdatedAt ? 'STALE' : 'NOT_CONNECTED',
    lidar: input.freshness || 'WAITING',
    camera: !connected ? 'NOT_CONNECTED' : camera?.ageMs > 3000 ? 'STALE' : cameraProvenance || bounded(camera?.connection, 'WAITING').toUpperCase(),
    observed: input.stateUpdatedAt ? new Date(input.stateUpdatedAt).toLocaleTimeString('ko-KR', { hour12: false }) : '—',
    map: bounded(map?.name, '선택한 지도 없음'),
    revision: bounded(map?.revision), frame: bounded(map?.frameId),
    localization: bounded(input.map?.localization?.health, 'UNAVAILABLE'),
    readiness: !navigation || !connected ? 'NOT_CONNECTED' : missing.length ? `WAIT · ${missing.join(', ')}` : Object.keys(readiness).length ? 'SERVER READY' : 'UNAVAILABLE',
    selection: bounded(input.map?.selectedAnnotationId, '선택한 지점 없음'),
    mission: bounded(input.mission?.active?.state, '실행 중인 미션 없음'),
    capture: capture?.active ? `CAPTURING · ${bounded(capture.sessionId)}` : bounded(capture?.state, 'NOT_CONNECTED').toUpperCase(),
    samples: capture?.saved == null ? '—' : `${capture.saved} saved · ${capture.dropped ?? '—'} dropped`,
    next: connected ? '지도 revision과 localization readiness를 확인하세요.' : '로봇 전원·ROS gateway·센서 소스를 각각 확인하세요. 저장 지도는 계속 조회할 수 있습니다.',
  });
}

export function createMissionInspector(root) {
  if (!root) return null;
  const fields = [...root.querySelectorAll('[data-inspector-field]')];
  return Object.freeze({ render(input) {
    const projected = projectMissionInspector(input);
    for (const field of fields) {
      const value = projected[field.dataset.inspectorField];
      if (field.textContent !== value) field.textContent = value;
      field.title = value;
    }
    root.dataset.robotState = projected.robot.toLowerCase();
    return projected;
  } });
}
