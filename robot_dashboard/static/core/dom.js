export const $ = (selector) => document.querySelector(selector);

export function setStatePill(element, state, label) {
  element.className = `panel-state ${state === 'ok' || state === 'mapping' || state === 'cloud_only' || state === 'grid_live' || state === 'saved' ? 'ok' : state === 'stale' || state === 'error' ? 'error' : 'waiting'}`;
  element.innerHTML = `<span></span>${label || state.toUpperCase()}`;
}
