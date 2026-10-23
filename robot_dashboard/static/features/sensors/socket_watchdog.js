// Transport liveness only. Never refresh source timestamps or observation validity.
export function createSocketWatchdog(onSilence, options = {}) {
  const schedule = options.setTimeout || globalThis.setTimeout;
  const cancel = options.clearTimeout || globalThis.clearTimeout;
  let timer = null, generation = 0, stopped = false;
  function arm(delay) {
    if (stopped) return;
    if (timer !== null) cancel(timer);
    const current = ++generation;
    timer = schedule(() => {
      if (stopped || current !== generation) return;
      timer = null;
      onSilence();
    }, delay);
  }
  arm(options.connectTimeoutMs ?? 3000);
  return {
    received() { arm(options.silenceMs ?? 600); },
    stop() { stopped = true; generation++; if (timer !== null) cancel(timer); timer = null; },
  };
}

export function createPoseTransport(options) {
  const schedule = options.setTimeout || globalThis.setTimeout;
  const cancel = options.clearTimeout || globalThis.clearTimeout;
  const makeSocket = options.socketFactory || (url => new WebSocket(url));
  let socket = null, watch = null, retry = null, stopped = false;
  function connect() {
    if (stopped || socket) return;
    const next = makeSocket(options.url);
    socket = next;
    const currentWatch = createSocketWatchdog(() => {
      if (socket !== next || stopped) return;
      socket = null;
      currentWatch.stop();
      next.close();
      connect();
    }, { ...options, setTimeout: schedule, clearTimeout: cancel });
    watch = currentWatch;
    next.onmessage = event => {
      if (socket !== next || stopped) return;
      try {
        const value = JSON.parse(event.data);
        currentWatch.received();
        options.onSnapshot(value);
      } catch (error) { options.onError?.(error); }
    };
    next.onclose = () => {
      currentWatch.stop();
      if (socket !== next || stopped) return;
      socket = null;
      retry = schedule(() => { retry = null; connect(); }, 1200);
    };
    next.onerror = () => { if (socket === next) next.close(); };
  }
  return {
    start: connect,
    destroy() {
      stopped = true;
      watch?.stop();
      if (retry !== null) cancel(retry);
      const old = socket; socket = null;
      old?.close();
    },
  };
}
