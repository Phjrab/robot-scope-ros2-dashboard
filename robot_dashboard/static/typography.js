// Font readiness invalidates text paint only. Renderers own their subscriptions.
(() => {
  const callbacks = new Set();
  const fallback = {
    ui: '"IBM Plex Sans", "IBM Plex Sans KR", system-ui, sans-serif',
    mono: '"IBM Plex Mono", "IBM Plex Sans KR", ui-monospace, monospace',
  };
  let scheduled = false;
  let families;
  function repaint() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; for (const callback of callbacks) callback(); });
  }
  document.fonts?.addEventListener('loadingdone', repaint);
  window.RobotScopeTypography = Object.freeze({
    canvasFont(role, size, weight = 400) {
      if (!families) {
        const style = getComputedStyle(document.documentElement);
        families = Object.fromEntries(['ui', 'mono'].map((name) => [name, style.getPropertyValue(`--font-${name}`).trim() || fallback[name]]));
      }
      const family = families[role] || families.ui;
      const supported = role === 'mono' ? Math.min(500, weight) : Math.min(600, weight);
      return `${supported} ${size}px ${family}`;
    },
    subscribe(callback) {
      callbacks.add(callback);
      document.fonts?.ready.then(() => { if (callbacks.has(callback)) repaint(); });
      return () => callbacks.delete(callback);
    },
  });
})();
