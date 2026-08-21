// Resolve physical LiDAR identity only from backend metadata. Topic names are
// display data, not browser-side authority for a sensor make or model.
export const LidarSourceIdentity = (() => {
  const SENSOR_LABELS = Object.freeze({
    go2_builtin_lidar: 'GO2 BUILT-IN LIDAR',
    hesai_xt16: 'HESAI XT16',
    generic_pointcloud: 'GENERIC POINTCLOUD',
  });
  const STAGE_DETAILS = Object.freeze({
    raw: 'RAW', converted: 'CONVERTED', deskewed: 'DESKEWED', base_frame: 'BASE FRAME',
    registered: 'REGISTERED', local_map: 'LOCAL MAP', height_map: 'HEIGHT MAP',
    range_map: 'RANGE MAP', voxel_map: 'VOXEL MAP', map: 'MAP', sensor_output: 'SENSOR OUTPUT',
    slam_output: 'SLAM OUTPUT', unknown: 'UNKNOWN',
  });

  function text(value) { return value == null ? '' : String(value).trim(); }
  function topicOf(value) {
    if (typeof value === 'string') return value.trim();
    if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
    return text(value.topic || value.name || value.value);
  }
  function flattenMetadata(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const nested = [value.metadata, value.source_metadata, value.identity, value.lidar_metadata]
      .filter((entry) => entry && typeof entry === 'object' && !Array.isArray(entry));
    return Object.assign({}, ...nested, value);
  }
  function first(metadata, keys) {
    for (const key of keys) {
      const value = text(metadata?.[key]);
      if (value) return value;
    }
    return '';
  }
  function canonicalSensor(sensorId, sensorLabel) {
    const id = text(sensorId).toLowerCase().replace(/[\s-]+/g, '_');
    if (id) return id;
    const label = text(sensorLabel).toLowerCase();
    if (label === 'hesai xt16') return 'hesai_xt16';
    if (label === 'go2 built-in lidar') return 'go2_builtin_lidar';
    return 'generic_pointcloud';
  }
  function canonicalStage(value) {
    const token = text(value).toLowerCase().replace(/[\s-]+/g, '_');
    if (!token) return '';
    if (token === 'raw' || token === 'original' || token === 'raw_points') return 'raw';
    if (token.includes('deskew')) return 'deskewed';
    if (token.includes('base_frame') || token === 'base') return 'base_frame';
    if (token.includes('convert') || token.includes('correct') || token.includes('calibrat')) return 'converted';
    if (token.includes('register') || token.includes('fast_lio') || token === 'fastlio') return 'registered';
    if (token.includes('local_map')) return 'local_map';
    if (token === 'map' || token.includes('slam_map')) return 'map';
    if (token === 'sensor_output') return 'sensor_output';
    if (token === 'slam_output') return 'slam_output';
    if (token === 'unknown' || token === 'pointcloud') return 'unknown';
    return token;
  }
  function stagePrefix(stage, sensorId) {
    if (stage === 'raw') return '원본';
    if (['converted', 'deskewed', 'base_frame'].includes(stage)) return '보정';
    if (stage === 'registered' || (stage === 'map' && sensorId === 'hesai_xt16')) return 'FAST-LIO';
    if (['map', 'local_map', 'slam_output'].includes(stage)) return 'SLAM';
    if (['height_map', 'range_map', 'voxel_map'].includes(stage)) return '센서 맵';
    if (stage === 'sensor_output') return '센서 출력';
    return '단계 미확인';
  }
  function stageLabel(stage, sensorId, backendLabel = '') {
    const prefix = stagePrefix(stage, sensorId);
    if (stage === 'unknown' && !backendLabel) return prefix;
    const detail = text(backendLabel) || STAGE_DETAILS[stage] || stage.replace(/_/g, ' ');
    return `${prefix} · ${detail.toUpperCase()}`;
  }
  function normalizeReportedStatus(value) {
    const token = text(value).toLowerCase();
    if (['ok', 'live', 'online', 'fresh', 'active', 'streaming'].includes(token)) return 'LIVE';
    if (['stale', 'timeout', 'timed_out', 'expired'].includes(token)) return 'STALE';
    if (token) return 'WAITING';
    return '';
  }
  function describe(value, extraMetadata = {}) {
    const topic = topicOf(value) || topicOf(extraMetadata);
    const metadata = Object.assign({}, flattenMetadata(value), flattenMetadata(extraMetadata));
    const backendSensorId = first(metadata, ['sensor_id', 'lidar_sensor_id', 'sensor_family', 'lidar_model']);
    const backendSensorLabel = first(metadata, ['sensor_label', 'lidar_sensor_label', 'sensor_name', 'lidar_model_label']);
    const hasBackendSensor = Boolean(backendSensorId || backendSensorLabel);
    const sensorId = hasBackendSensor ? canonicalSensor(backendSensorId, backendSensorLabel) : 'generic_pointcloud';
    const sensorLabel = !topic && !hasBackendSensor
      ? 'LIDAR NOT SELECTED'
      : (backendSensorLabel ? backendSensorLabel.toUpperCase() : SENSOR_LABELS[sensorId])
        || sensorId.replace(/_/g, ' ').toUpperCase();
    const backendStage = first(metadata, ['pipeline_stage', 'processing_stage', 'cloud_stage', 'stage']);
    const stage = backendStage ? canonicalStage(backendStage) : 'unknown';
    const backendStageLabel = first(metadata, ['pipeline_stage_label', 'processing_stage_label', 'cloud_stage_label', 'stage_label']);
    const reportedStatus = normalizeReportedStatus(first(metadata, ['freshness', 'live_state', 'status', 'state']));
    return {
      topic, sensorId, sensorLabel, stage,
      stageLabel: stageLabel(stage, sensorId, backendStageLabel),
      reportedStatus,
      metadataPresent: Boolean(backendSensorId || backendSensorLabel || backendStage || backendStageLabel),
    };
  }
  function groupLabel(identity) {
    return identity.sensorLabel || 'OTHER POINTCLOUD';
  }
  return { describe, flattenMetadata, groupLabel, normalizeReportedStatus, topicOf };
})();
