// Resolve LiDAR identity from backend metadata first and an exact-topic
// allowlist second. Never infer a physical sensor from topic fragments.
export const LidarSourceIdentity = (() => {
  const TOPIC_ALLOWLIST = Object.freeze({
    '/utlidar/cloud': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'raw' }),
    '/utlidar/cloud_deskewed': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'deskewed' }),
    '/utlidar/cloud_base': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'base_frame' }),
    '/utlidar/grid_map': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'local_map' }),
    '/utlidar/height_map': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'height_map' }),
    '/utlidar/range_map': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'range_map' }),
    '/utlidar/voxel_map': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'voxel_map' }),
    '/uslam/cloud_map': Object.freeze({ sensorId: 'go2_builtin_lidar', stage: 'map' }),
    '/lidar_points': Object.freeze({ sensorId: 'hesai_xt16', stage: 'raw' }),
    '/velodyne_points': Object.freeze({ sensorId: 'hesai_xt16', stage: 'converted' }),
    '/cloud_registered': Object.freeze({ sensorId: 'hesai_xt16', stage: 'registered' }),
    '/Laser_map': Object.freeze({ sensorId: 'hesai_xt16', stage: 'map' }),
  });
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
    const token = `${id} ${text(sensorLabel).toLowerCase()}`;
    if (/(hesai|xt\s*-?\s*16|pandar)/.test(token)) return 'hesai_xt16';
    if (/(go2|unitree|utlidar|built[\s_-]*in)/.test(token)) return 'go2_builtin_lidar';
    if (id) return id;
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
    const fallback = TOPIC_ALLOWLIST[topic] || { sensorId: 'generic_pointcloud', stage: 'unknown' };
    const backendSensorId = first(metadata, ['sensor_id', 'lidar_sensor_id', 'sensor_family', 'lidar_model']);
    const backendSensorLabel = first(metadata, ['sensor_label', 'lidar_sensor_label', 'sensor_name', 'lidar_model_label']);
    const hasBackendSensor = Boolean(backendSensorId || backendSensorLabel);
    const sensorId = hasBackendSensor ? canonicalSensor(backendSensorId, backendSensorLabel) : fallback.sensorId;
    const sensorLabel = !topic && !hasBackendSensor
      ? 'LIDAR NOT SELECTED'
      : SENSOR_LABELS[sensorId]
        || (backendSensorLabel ? backendSensorLabel.toUpperCase() : sensorId.replace(/_/g, ' ').toUpperCase());
    const backendStage = first(metadata, ['pipeline_stage', 'processing_stage', 'cloud_stage', 'stage']);
    const stage = backendStage ? canonicalStage(backendStage) : fallback.stage;
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
    if (identity.sensorId === 'go2_builtin_lidar') return 'GO2 BUILT-IN LIDAR';
    if (identity.sensorId === 'hesai_xt16') return 'HESAI XT16';
    return identity.sensorLabel || 'OTHER POINTCLOUD';
  }
  return { TOPIC_ALLOWLIST, describe, flattenMetadata, groupLabel, normalizeReportedStatus, topicOf };
})();
