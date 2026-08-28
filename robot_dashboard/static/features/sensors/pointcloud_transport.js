const DEFAULT_RECONNECT_DELAY_MS = 1200;

function defaultSocketUrl(locationValue) {
  const scheme = locationValue.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${locationValue.host}/api/v1/ws/pointcloud`;
}

function safeClose(socket, reason) {
  if (!socket || ![0, 1].includes(socket.readyState)) return;
  try {
    socket.close(1000, reason);
  } catch (_) {
    socket.close();
  }
}

export function createPointcloudTransport(options = {}) {
  const environment = options.environment || globalThis;
  const decodeFrame = options.decodeFrame;
  const fetchFn = options.fetchFn || environment.fetch?.bind(environment);
  const socketFactory = options.socketFactory || ((url) => new environment.WebSocket(url));
  const requestFrame = options.requestAnimationFrame
    || environment.requestAnimationFrame?.bind(environment)
    || ((callback) => environment.setTimeout(callback, 16));
  const cancelFrame = options.cancelAnimationFrame
    || environment.cancelAnimationFrame?.bind(environment)
    || environment.clearTimeout?.bind(environment);
  const setTimer = options.setTimeout || environment.setTimeout?.bind(environment);
  const clearTimer = options.clearTimeout || environment.clearTimeout?.bind(environment);
  const locationValue = options.location || environment.location || { protocol: 'http:', host: 'localhost' };
  const socketUrl = options.socketUrl || defaultSocketUrl(locationValue);
  const reconnectDelayMs = Math.max(0, Number(options.reconnectDelayMs ?? DEFAULT_RECONNECT_DELAY_MS));

  if (typeof decodeFrame !== 'function') throw new TypeError('Pointcloud transport requires decodeFrame.');
  if (typeof fetchFn !== 'function') throw new TypeError('Pointcloud transport requires fetch.');

  const consumers = new Set();
  const subscribers = new Map();
  let socket = null;
  let connectionGeneration = 0;
  let requestGeneration = 0;
  let reconnectTimer = 0;
  let pendingFrame = null;
  let pendingFrameRequest = 0;
  let requestInFlight = false;
  let binaryHttpAvailable = true;
  let lastSequence = -1;
  let streamId = '';
  let destroyed = false;
  let connectionCount = 0;
  let closeCount = 0;

  const wanted = () => !destroyed && consumers.size > 0;

  function diagnostics() {
    return Object.freeze({
      activeConsumers: Object.freeze([...consumers].sort()),
      subscriberCount: subscribers.size,
      connected: Boolean(socket && [0, 1].includes(socket.readyState)),
      connectionCount,
      closeCount,
      requestInFlight,
      lastSequence,
      streamId,
      destroyed,
    });
  }

  function dispatch(cloud) {
    for (const subscriber of subscribers.values()) {
      try {
        subscriber(cloud);
      } catch (error) {
        options.onError?.(error);
      }
    }
  }

  function acceptCloud(cloud) {
    const sequence = Number(cloud?.seq);
    if (!Number.isSafeInteger(sequence) || sequence <= 0 || !cloud?.points?.length) return false;
    const incomingStreamId = String(cloud.stream_id || '');
    const streamChanged = Boolean(incomingStreamId && streamId && incomingStreamId !== streamId);
    const legacyRollback = !incomingStreamId && lastSequence >= 0 && sequence < lastSequence;
    if (streamChanged || legacyRollback) lastSequence = -1;
    if (incomingStreamId) streamId = incomingStreamId;
    if (sequence <= lastSequence) return false;
    lastSequence = sequence;
    dispatch(cloud);
    return true;
  }

  function drainFrame() {
    pendingFrameRequest = 0;
    const pending = pendingFrame;
    pendingFrame = null;
    if (pending && pending.generation === connectionGeneration && wanted()) {
      try {
        acceptCloud(decodeFrame(pending.buffer));
      } catch (error) {
        options.onError?.(error);
      }
    }
    if (pendingFrame && !pendingFrameRequest) pendingFrameRequest = requestFrame(drainFrame);
  }

  function queueFrame(buffer, generation) {
    pendingFrame = { buffer, generation };
    if (!pendingFrameRequest) pendingFrameRequest = requestFrame(drainFrame);
  }

  function disconnect(reason = 'pointcloud demand inactive') {
    requestGeneration += 1;
    connectionGeneration += 1;
    if (reconnectTimer) clearTimer?.(reconnectTimer);
    reconnectTimer = 0;
    pendingFrame = null;
    if (pendingFrameRequest) cancelFrame?.(pendingFrameRequest);
    pendingFrameRequest = 0;
    const previous = socket;
    socket = null;
    if (previous && [0, 1].includes(previous.readyState)) {
      closeCount += 1;
      safeClose(previous, reason);
    }
  }

  function connect() {
    if (!wanted() || socket && [0, 1].includes(socket.readyState)) return;
    const generation = ++connectionGeneration;
    const nextSocket = socketFactory(socketUrl);
    socket = nextSocket;
    connectionCount += 1;
    nextSocket.binaryType = 'arraybuffer';
    nextSocket.onmessage = (event) => {
      if (socket !== nextSocket || generation !== connectionGeneration || !(event.data instanceof ArrayBuffer)) return;
      queueFrame(event.data, generation);
    };
    nextSocket.onclose = () => {
      if (socket !== nextSocket || generation !== connectionGeneration) return;
      socket = null;
      if (wanted()) {
        reconnectTimer = setTimer?.(() => {
          reconnectTimer = 0;
          connect();
        }, reconnectDelayMs) || 0;
      }
    };
    nextSocket.onerror = () => safeClose(nextSocket, 'pointcloud transport error');
  }

  function replaceDemand(consumerIds = []) {
    if (destroyed) return diagnostics();
    const hadDemand = wanted();
    consumers.clear();
    for (const id of consumerIds) {
      const normalized = String(id || '').trim();
      if (normalized) consumers.add(normalized);
    }
    const hasDemand = wanted();
    if (hasDemand) connect();
    else if (hadDemand || socket) disconnect();
    return diagnostics();
  }

  function subscribe(id, callback) {
    if (destroyed) throw new Error('Pointcloud transport is destroyed.');
    const normalized = String(id || '').trim();
    if (!normalized) throw new TypeError('Pointcloud subscriber id is required.');
    if (typeof callback !== 'function') throw new TypeError('Pointcloud subscriber callback is required.');
    subscribers.set(normalized, callback);
    let disposed = false;
    return () => {
      if (disposed) return;
      disposed = true;
      subscribers.delete(normalized);
      if (consumers.delete(normalized) && !wanted()) disconnect();
    };
  }

  async function fetchLatest() {
    const query = `since=${encodeURIComponent(lastSequence)}`;
    if (binaryHttpAvailable) {
      const response = await fetchFn(`/api/v1/pointcloud.bin?${query}`, { cache: 'no-store' });
      if (response.status === 204) return null;
      if (response.status !== 404 && response.status !== 415) {
        if (!response.ok) throw new Error(String(response.status));
        return decodeFrame(await response.arrayBuffer());
      }
      binaryHttpAvailable = false;
    }
    const response = await fetchFn(`/api/v1/pointcloud?${query}`, { cache: 'no-store' });
    if (response.status === 204) return null;
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  async function poll() {
    if (!wanted() || socket && [0, 1].includes(socket.readyState) || requestInFlight) return false;
    requestInFlight = true;
    const generation = requestGeneration;
    try {
      const cloud = await fetchLatest();
      if (generation !== requestGeneration || !wanted()) return false;
      return cloud ? acceptCloud(cloud) : false;
    } catch (error) {
      if (generation === requestGeneration) options.onError?.(error);
      return false;
    } finally {
      requestInFlight = false;
    }
  }

  function reset(nextStreamId = '') {
    lastSequence = -1;
    streamId = String(nextStreamId || '');
    requestGeneration += 1;
  }

  function destroy() {
    if (destroyed) return;
    disconnect('pointcloud transport destroyed');
    destroyed = true;
    consumers.clear();
    subscribers.clear();
  }

  return Object.freeze({ replaceDemand, subscribe, poll, reset, disconnect, destroy, diagnostics });
}
