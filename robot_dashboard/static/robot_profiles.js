(function installRobotProfiles(global, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  global.RobotProfiles = api;
})(typeof window !== 'undefined' ? window : globalThis, function createRobotProfiles() {
  'use strict';

  const CAPABILITY_NAMES = Object.freeze([
    'observability',
    'camera',
    'pointcloud',
    'mapping',
    'localization',
    'navigation',
    'manual_control',
    'autonomous_control',
  ]);

  const OBSERVATION_CAPABILITIES = Object.freeze({
    observability: true,
    camera: true,
    pointcloud: true,
    mapping: false,
    localization: false,
    navigation: false,
    manual_control: false,
    autonomous_control: false,
  });

  const GO2_CAPABILITIES = Object.freeze(
    Object.fromEntries(CAPABILITY_NAMES.map((name) => [name, true])),
  );

  const DEFAULT_TYPES = Object.freeze([
    Object.freeze({
      id: 'go2',
      label: 'Unitree Go2',
      description: 'Unitree Go2 사족보행 로봇',
      capabilities: GO2_CAPABILITIES,
      model: Object.freeze({
        kind: 'robot-model-lite',
        asset_url: '/static/assets/go2/go2-official-lite.json',
        urdf_url: '',
        label: 'Official Go2 URDF',
        fidelity: 'official-derived',
      }),
    }),
    Object.freeze({
      id: 'turtlebot',
      label: 'TurtleBot',
      description: 'ROS 2 이동 로봇 플랫폼',
      capabilities: OBSERVATION_CAPABILITIES,
      model: Object.freeze({
        kind: 'robot-model-lite',
        asset_url: '/static/assets/turtlebot/turtlebot3-burger-official-lite.json',
        urdf_url: '/static/assets/turtlebot/source/turtlebot3_description/urdf/turtlebot3_burger.urdf',
        label: 'Official TurtleBot3 Burger URDF',
        fidelity: 'official-derived',
      }),
    }),
  ]);

  function cleanText(value, fallback = '') {
    const text = String(value == null ? '' : value).trim();
    return text || fallback;
  }

  function robotTypeId(value) {
    return cleanText(value).toLowerCase().replace(/_/g, '-').replace(/[^a-z0-9-]/g, '');
  }

  function defaultType(typeId) {
    const normalized = robotTypeId(typeId);
    return DEFAULT_TYPES.find((profile) => profile.id === normalized) || null;
  }

  function normalizeModel(value, fallback = {}) {
    const model = value && typeof value === 'object' ? value : {};
    return {
      kind: cleanText(model.kind || model.renderer, fallback.kind || 'robot-model-lite'),
      asset_url: cleanText(model.asset_url || model.assetUrl, fallback.asset_url || ''),
      urdf_url: cleanText(model.urdf_url || model.urdfUrl, fallback.urdf_url || ''),
      label: cleanText(model.label || model.name, fallback.label || 'Robot model'),
      fidelity: cleanText(model.fidelity, fallback.fidelity || 'preview'),
    };
  }

  function normalizeCapabilities(value, fallback = {}) {
    const supplied = value && typeof value === 'object' && !Array.isArray(value);
    const source = supplied ? value : fallback;
    return Object.fromEntries(
      CAPABILITY_NAMES.map((name) => [name, source?.[name] === true]),
    );
  }

  function normalizeType(value) {
    const candidate = typeof value === 'string' ? { id: value } : (value || {});
    const id = robotTypeId(candidate.id || candidate.type || candidate.key || candidate.profile);
    if (!id) return null;
    const fallback = defaultType(id);
    if (!fallback) return null;
    return {
      id,
      label: cleanText(candidate.label || candidate.name, fallback.label || id.toUpperCase()),
      description: cleanText(candidate.description, fallback.description || ''),
      capabilities: normalizeCapabilities(candidate.capabilities, fallback.capabilities),
      model: normalizeModel(candidate.model || candidate.urdf, fallback.model || {}),
    };
  }

  function profileSupports(profile, capability) {
    const name = cleanText(capability).toLowerCase();
    if (!CAPABILITY_NAMES.includes(name)) return false;
    return normalizeCapabilities(profile?.capabilities)[name];
  }

  function normalizeTypes(payload) {
    const values = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.types)
        ? payload.types
        : Array.isArray(payload?.robot_types)
          ? payload.robot_types
          : [];
    const byId = new Map();
    values.map(normalizeType).filter(Boolean).forEach((profile) => byId.set(profile.id, profile));
    if (!byId.size) DEFAULT_TYPES.forEach((profile) => byId.set(profile.id, normalizeType(profile)));
    return Array.from(byId.values());
  }

  function validIpv4(value) {
    const parts = cleanText(value).split('.');
    return parts.length === 4 && parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
  }

  function normalizeCandidate(value) {
    const candidate = value && typeof value === 'object' ? value : {};
    const ip = cleanText(candidate.ip || candidate.address || candidate.host);
    if (!validIpv4(ip)) return null;
    const latency = Number(candidate.latency_ms ?? candidate.latency);
    const confidence = Number(candidate.confidence);
    return {
      ip,
      hostname: cleanText(candidate.hostname || candidate.host_name, 'hostname 없음'),
      interface: cleanText(candidate.interface || candidate.iface, ''),
      latency_ms: Number.isFinite(latency) && latency >= 0 ? latency : null,
      confidence: Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence)) : null,
      reason: cleanText(candidate.reason, ''),
    };
  }

  function normalizeDiscovery(payload) {
    const values = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.candidates)
        ? payload.candidates
        : Array.isArray(payload?.robots)
          ? payload.robots
          : Array.isArray(payload?.results)
            ? payload.results
            : [];
    const byIp = new Map();
    values.map(normalizeCandidate).filter(Boolean).forEach((candidate) => {
      const previous = byIp.get(candidate.ip);
      if (!previous || (candidate.confidence ?? -1) > (previous.confidence ?? -1)) byIp.set(candidate.ip, candidate);
    });
    return Array.from(byIp.values()).sort((a, b) => {
      const confidence = (b.confidence ?? -1) - (a.confidence ?? -1);
      return confidence || (a.latency_ms ?? Infinity) - (b.latency_ms ?? Infinity) || a.ip.localeCompare(b.ip);
    });
  }

  function connectionPayload(profile, candidate, ip) {
    const type = normalizeType(profile);
    const targetIp = cleanText(ip || candidate?.ip);
    const payload = { ip: targetIp, robot_type: type?.id || robotTypeId(profile) };
    const hostname = cleanText(candidate?.hostname);
    if (hostname && hostname !== 'hostname 없음') payload.hostname = hostname;
    return payload;
  }

  return {
    CAPABILITY_NAMES,
    DEFAULT_TYPES,
    robotTypeId,
    normalizeType,
    normalizeTypes,
    normalizeCapabilities,
    profileSupports,
    normalizeCandidate,
    normalizeDiscovery,
    connectionPayload,
  };
});
