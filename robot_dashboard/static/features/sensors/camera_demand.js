const DEFAULT_ALLOWED_SOURCES = Object.freeze(['go2_front', 'realsense_color']);

function finite(value, fallback = null) {
  if (value == null || value === '' || typeof value === 'boolean') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeSource(entry, allowed) {
  const id = String(entry?.id || entry?.source_id || '');
  if (!allowed.has(id)) return null;
  return Object.freeze({
    id,
    source_id: id,
    label: String(entry?.label || id),
    available: entry?.available !== false && entry?.enabled !== false,
    state: String(entry?.state || 'waiting').toLowerCase(),
    fps: finite(entry?.fps),
    age_s: finite(entry?.age_s),
    width: Math.max(0, finite(entry?.width, 0)),
    height: Math.max(0, finite(entry?.height, 0)),
    transport: String(entry?.transport || '—'),
    topic: String(entry?.topic || '—'),
    receive_fps: finite(entry?.receive_fps),
    receive_bitrate_mbps: finite(entry?.receive_bitrate_mbps),
    restart_count: Math.max(0, finite(entry?.restart_count, 0)),
    status_class: String(entry?.status_class || ''),
    relay_health: entry?.relay_health && typeof entry.relay_health === 'object'
      ? Object.freeze({ ...entry.relay_health })
      : null,
    cross_host_latency_state: String(entry?.cross_host_latency_state || 'UNVERIFIED_CLOCK_DOMAIN'),
  });
}

export function createCameraDemandController(options = {}) {
  const allowed = new Set(options.allowedSourceIds || DEFAULT_ALLOWED_SOURCES);
  const sources = new Map();
  const runtimes = new Map();
  const consumers = new Map();
  const listeners = new Set();
  let nextToken = 1;
  let catalogGeneration = 0;

  function runtime(sourceId) {
    if (!runtimes.has(sourceId)) {
      runtimes.set(sourceId, { generation: 0, connection: 'waiting', metadata: null, lastFrameAt: 0, error: '' });
    }
    return runtimes.get(sourceId);
  }

  function consumersFor(sourceId) {
    return [...consumers.values()].filter((consumer) => consumer.sourceId === sourceId);
  }

  function sourceSnapshot(sourceId, now = Date.now()) {
    const source = sources.get(sourceId) || null;
    const current = runtime(sourceId);
    const ageMs = current.lastFrameAt ? Math.max(0, Number(now) - current.lastFrameAt) : null;
    return Object.freeze({
      ...(source || { id: sourceId, source_id: sourceId, label: sourceId, available: false, state: 'waiting', fps: null, age_s: null, width: 0, height: 0, transport: '—', topic: '—' }),
      connection: current.connection,
      reconnecting: current.connection === 'reconnecting',
      generation: current.generation,
      metadata: current.metadata ? Object.freeze({ ...current.metadata }) : null,
      lastFrameAt: current.lastFrameAt,
      ageMs: Number.isFinite(ageMs) ? ageMs : null,
      error: current.error,
      viewerCount: consumersFor(sourceId).length,
    });
  }

  function catalogSnapshot() {
    return Object.freeze({
      generation: catalogGeneration,
      sources: Object.freeze([...allowed].map((sourceId) => sourceSnapshot(sourceId))),
    });
  }

  function emitSource(sourceId) {
    const snapshot = sourceSnapshot(sourceId);
    for (const consumer of consumersFor(sourceId)) consumer.onState?.(snapshot);
    for (const listener of listeners) listener(catalogSnapshot());
  }

  function updateCatalog(entries = []) {
    catalogGeneration += 1;
    sources.clear();
    for (const entry of entries) {
      const source = normalizeSource(entry, allowed);
      if (source) sources.set(source.id, source);
    }
    for (const sourceId of allowed) emitSource(sourceId);
    return catalogSnapshot();
  }

  function acquire(sourceIdValue, consumer = {}) {
    const sourceId = String(sourceIdValue || '');
    if (!allowed.has(sourceId)) throw new RangeError('Camera source is not allowlisted.');
    const id = `camera-consumer-${nextToken++}`;
    const wasDemanded = consumersFor(sourceId).length > 0;
    consumers.set(id, { id, sourceId, onFrame: consumer.onFrame, onState: consumer.onState });
    consumer.onState?.(sourceSnapshot(sourceId));
    if (!wasDemanded) options.onDemandChange?.(sourceId, true);
    let released = false;
    return Object.freeze({
      id,
      sourceId,
      release() {
        if (released) return false;
        released = true;
        return release(id);
      },
    });
  }

  function release(tokenId) {
    const token = consumers.get(String(tokenId || ''));
    if (!token) return false;
    consumers.delete(token.id);
    if (!consumersFor(token.sourceId).length) options.onDemandChange?.(token.sourceId, false);
    emitSource(token.sourceId);
    return true;
  }

  function isDemanded(sourceId) {
    return consumersFor(String(sourceId || '')).length > 0;
  }

  function beginGeneration(sourceId, generation, connection = 'connecting') {
    if (!allowed.has(sourceId)) return false;
    const current = runtime(sourceId);
    current.generation = Number(generation) || current.generation + 1;
    current.connection = connection;
    current.metadata = null;
    current.lastFrameAt = 0;
    current.error = '';
    emitSource(sourceId);
    return true;
  }

  function generationCurrent(sourceId, generation) {
    return allowed.has(sourceId) && runtime(sourceId).generation === Number(generation);
  }

  function publishMetadata(sourceId, generation, metadata = {}) {
    if (!generationCurrent(sourceId, generation)) return false;
    const current = runtime(sourceId);
    current.metadata = { ...metadata, source_id: sourceId };
    current.connection = 'connected';
    current.error = '';
    emitSource(sourceId);
    return true;
  }

  function publishFrame(sourceId, generation, frame = {}) {
    if (!generationCurrent(sourceId, generation)) return false;
    const current = runtime(sourceId);
    current.connection = 'live';
    current.lastFrameAt = Number(frame.lastFrameAt) || Date.now();
    current.error = '';
    const snapshot = sourceSnapshot(sourceId, current.lastFrameAt);
    for (const consumer of consumersFor(sourceId)) consumer.onFrame?.(Object.freeze({ ...frame, source: snapshot, generation: current.generation }));
    emitSource(sourceId);
    return true;
  }

  function endGeneration(sourceId, generation, connection = 'waiting', error = '') {
    if (!generationCurrent(sourceId, generation)) return false;
    const current = runtime(sourceId);
    current.connection = connection;
    current.error = String(error || '');
    current.metadata = null;
    current.lastFrameAt = 0;
    emitSource(sourceId);
    return true;
  }

  function subscribe(listener) {
    listeners.add(listener);
    listener(catalogSnapshot());
    return () => listeners.delete(listener);
  }

  function snapshot() {
    return Object.freeze({
      catalogGeneration,
      sources: Object.freeze([...allowed].map((sourceId) => sourceSnapshot(sourceId))),
      totalConsumers: consumers.size,
    });
  }

  return Object.freeze({
    updateCatalog,
    acquire,
    release,
    isDemanded,
    beginGeneration,
    publishMetadata,
    publishFrame,
    endGeneration,
    subscribe,
    sourceSnapshot,
    snapshot,
  });
}

export { DEFAULT_ALLOWED_SOURCES };
