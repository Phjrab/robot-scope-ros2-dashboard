export const COCKPIT_LAYOUT_MODES = Object.freeze({ OPERATE: 'operate', EDIT: 'layout-edit' });

function snapshot(state) {
  return Object.freeze({ mode: state.mode, armed: state.armed, generation: state.generation });
}

export function reduceLayoutMode(state, event = {}) {
  const current = snapshot(state || { mode: COCKPIT_LAYOUT_MODES.OPERATE, armed: false, generation: 0 });
  if (event.type === 'request-edit') {
    return current.armed ? current : snapshot({ ...current, mode: COCKPIT_LAYOUT_MODES.EDIT });
  }
  if (event.type === 'apply') return snapshot({ ...current, mode: COCKPIT_LAYOUT_MODES.OPERATE });
  if (event.type !== 'control') return current;
  const generation = Number(event.generation);
  if (!Number.isInteger(generation) || generation < current.generation) return current;
  const armed = Boolean(event.armed);
  return snapshot({
    mode: armed ? COCKPIT_LAYOUT_MODES.OPERATE : current.mode,
    armed,
    generation,
  });
}

export function createLayoutModeController(options = {}) {
  let state = snapshot({ mode: COCKPIT_LAYOUT_MODES.OPERATE, armed: false, generation: 0 });

  function dispatch(event) {
    const next = reduceLayoutMode(state, event);
    if (next.mode === state.mode && next.armed === state.armed && next.generation === state.generation) return state;
    state = next;
    options.onChange?.(state, event);
    return state;
  }

  return Object.freeze({
    requestEdit: () => dispatch({ type: 'request-edit' }),
    apply: () => dispatch({ type: 'apply' }),
    updateControl: (control) => dispatch({ type: 'control', ...control }),
    snapshot: () => state,
  });
}
