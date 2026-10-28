// Share one bounded read across polling ticks; invalidate only on context changes.
export function createSnapshotPolling(readSnapshot) {
  let active = null;
  function refresh() {
    if (active) return active.promise;
    const controller = new AbortController();
    const request = { controller, promise: null };
    active = request;
    const timeout = setTimeout(() => controller.abort(), 5000);
    request.promise = readSnapshot({ signal: controller.signal, isCurrent: () => active === request })
      .finally(() => {
        clearTimeout(timeout);
        if (active === request) active = null;
      });
    return request.promise;
  }
  function invalidate() {
    const previous = active;
    active = null;
    previous?.controller.abort();
  }
  return Object.freeze({ refresh, invalidate });
}
