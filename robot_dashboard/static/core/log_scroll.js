export const LOG_SCROLL_BOTTOM_TOLERANCE_PX = 16;
const stickyLogScrollGenerations = new WeakMap();

function nonnegativeScrollMetric(value) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function captureStickyLogScroll(element, followEnabled = true) {
  const scrollHeight = nonnegativeScrollMetric(element?.scrollHeight);
  const clientHeight = nonnegativeScrollMetric(element?.clientHeight);
  const maximumScrollTop = Math.max(0, scrollHeight - clientHeight);
  const scrollTop = Math.min(maximumScrollTop, nonnegativeScrollMetric(element?.scrollTop));
  return {
    scrollTop,
    follow: followEnabled === true && maximumScrollTop - scrollTop <= LOG_SCROLL_BOTTOM_TOLERANCE_PX,
  };
}

function applyStickyLogScroll(element, snapshot, forceBottom = false) {
  if (!element) return;
  const maximumScrollTop = Math.max(
    0,
    nonnegativeScrollMetric(element.scrollHeight) - nonnegativeScrollMetric(element.clientHeight),
  );
  element.scrollTop = forceBottom || snapshot?.follow === true
    ? maximumScrollTop
    : Math.min(maximumScrollTop, nonnegativeScrollMetric(snapshot?.scrollTop));
}

export function scheduleStickyLogScroll(element, snapshot, { forceBottom = false, shouldApply = null } = {}) {
  if (!element) return;
  const generation = (stickyLogScrollGenerations.get(element) || 0) + 1;
  stickyLogScrollGenerations.set(element, generation);
  const renderedScrollTop = nonnegativeScrollMetric(element.scrollTop);
  requestAnimationFrame(() => {
    if (stickyLogScrollGenerations.get(element) !== generation) return;
    if (typeof shouldApply === 'function' && !shouldApply()) return;
    if (Math.abs(nonnegativeScrollMetric(element.scrollTop) - renderedScrollTop) > 0.5) return;
    applyStickyLogScroll(element, snapshot, forceBottom);
  });
}
