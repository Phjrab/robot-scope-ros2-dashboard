function metric(value, minimum = 0, maximum = 100_000) {
  if (value == null || value === '' || typeof value === 'boolean') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= minimum && number <= maximum ? number : null;
}

function count(value, maximum = 999_999_999) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(maximum, Math.floor(number))) : 0;
}

export function cameraObservabilityState(value, fallback = 'UNVERIFIED') {
  const state = String(value || '').trim().toUpperCase();
  if (['LIVE', 'DEGRADED', 'STALE', 'OFFLINE', 'UNVERIFIED'].includes(state)) return state;
  if (['OK', 'STREAMING'].includes(state)) return 'LIVE';
  if (['STARTING', 'WAITING', 'RESTARTING'].includes(state)) return 'DEGRADED';
  if (['ERROR', 'STOPPED', 'DISABLED'].includes(state)) return 'OFFLINE';
  return fallback;
}

export function projectCameraObservability(input = {}) {
  const metadata = input.metadata || {};
  const relay = metadata.relay_health && typeof metadata.relay_health === 'object' ? metadata.relay_health : {};
  const wifi = relay.wifi && typeof relay.wifi === 'object' ? relay.wifi : {};
  const profile = relay.profile && typeof relay.profile === 'object' ? relay.profile : {};
  const rssi = metric(wifi.rssi_dbm, -150, 0);
  const link = metric(wifi.link_mbps, 0, 100_000);
  const sourceFps = metric(relay.fps, 0, 240);
  const sourceAge = metric(relay.last_frame_age_s, 0, 86_400);
  const width = metric(profile.width, 1, 8192);
  const height = metric(profile.height, 1, 8192);
  const dimensions = width && height ? `${width}×${height} · ` : '';
  const receiveMbps = metric(metadata.receive_bitrate_mbps);
  const receiveFps = metric(metadata.receive_fps ?? metadata.fps, 0, 240);
  const transportState = input.fresh ? 'LIVE' : input.hadFrame ? 'STALE' : cameraObservabilityState(metadata.status_class || metadata.state, 'OFFLINE');
  const queue = input.queue || {};
  const decoded = count(queue.decodedFrames);
  const failures = count(queue.decodeFailures);
  const superseded = count(queue.supersededFrames);
  const depth = count(queue.queueDepth, 2);
  return Object.freeze({
    wifi: Object.freeze({ state: cameraObservabilityState(wifi.state), detail: `RSSI ${rssi == null ? '—' : `${rssi.toFixed(0)} dBm`} · LINK ${link == null ? '—' : `${link.toFixed(1)} Mbps`}` }),
    source: Object.freeze({ state: cameraObservabilityState(relay.state), detail: `${dimensions}${sourceFps == null ? '—' : sourceFps.toFixed(1)} FPS · AGE ${sourceAge == null ? '—' : `${sourceAge.toFixed(2)}s`}` }),
    transport: Object.freeze({ state: transportState, detail: `${receiveMbps == null ? '—' : receiveMbps.toFixed(3)} Mbps · ${receiveFps == null ? '—' : receiveFps.toFixed(1)} FPS · R${count(input.reconnects)}` }),
    decode: Object.freeze({ state: failures > 0 && decoded === 0 ? 'DEGRADED' : input.fresh ? 'LIVE' : transportState, detail: `OK ${decoded} · FAIL ${failures} · DROP ${superseded} · Q${depth}` }),
    clock: 'UNVERIFIED_CLOCK_DOMAIN',
  });
}

export function createLatestCameraFrameQueue({ decode, render, close, onError = () => {} }) {
  let generation = 0;
  let active = false;
  let pending = null;
  let decodedFrames = 0;
  let decodeFailures = 0;
  let supersededFrames = 0;

  async function drain(initialFrame) {
    let frame = initialFrame;
    while (frame) {
      let decoded = null;
      try {
        decoded = await decode(frame);
        decodedFrames += 1;
        if (frame.generation === generation) render(decoded, frame);
      } catch (error) {
        decodeFailures += 1;
        if (frame.generation === generation) onError(error, frame);
      } finally {
        if (decoded) close(decoded, frame);
      }
      frame = pending;
      pending = null;
    }
    active = false;
  }

  return Object.freeze({
    enqueue(frame) {
      const tagged = { ...frame, generation };
      if (active) {
        if (pending) supersededFrames += 1;
        pending = tagged;
      } else {
        active = true;
        void drain(tagged);
      }
      return generation;
    },
    reset() {
      generation += 1;
      pending = null;
      return generation;
    },
    snapshot() {
      return { generation, active, pending: pending ? 1 : 0, queueDepth: (active ? 1 : 0) + (pending ? 1 : 0), decodedFrames, decodeFailures, supersededFrames };
    },
  });
}
