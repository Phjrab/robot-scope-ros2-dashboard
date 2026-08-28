const RESIZE_HANDLES = Object.freeze(['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw']);

function actionButton(documentValue, action, label, text) {
  const button = documentValue.createElement('button');
  button.type = 'button';
  button.dataset.panelAction = action;
  button.setAttribute('aria-label', label);
  button.title = label;
  button.textContent = text;
  return button;
}

export function createPanelView(options = {}) {
  const documentValue = options.document || globalThis.document;
  const host = options.host;
  const descriptor = options.descriptor;
  if (!host || !descriptor) throw new TypeError('Panel view requires host and descriptor.');

  const panel = documentValue.createElement('article');
  panel.className = 'cockpit-floating-panel';
  panel.dataset.panelId = descriptor.id;
  panel.dataset.panelType = descriptor.panelType;
  panel.tabIndex = -1;
  panel.setAttribute('aria-label', descriptor.title);

  const titlebar = documentValue.createElement('header');
  titlebar.className = 'cockpit-panel-titlebar';
  titlebar.dataset.panelDragHandle = '';
  const identity = documentValue.createElement('div');
  identity.className = 'cockpit-panel-identity';
  const eyebrow = documentValue.createElement('span');
  eyebrow.textContent = descriptor.eyebrow;
  const title = documentValue.createElement('h2');
  title.textContent = descriptor.title;
  identity.append(eyebrow, title);

  const actions = documentValue.createElement('div');
  actions.className = 'cockpit-panel-actions';
  const pin = actionButton(documentValue, 'pin', `${descriptor.title} 고정 전환`, 'PIN');
  const lock = actionButton(documentValue, 'lock', `${descriptor.title} 위치 잠금 전환`, 'LOCK');
  const compact = actionButton(documentValue, 'compact', `${descriptor.title} 최소화 전환`, '—');
  const focus = actionButton(documentValue, 'focus', `${descriptor.title} Focus 전환`, '□');
  const close = actionButton(documentValue, 'close', `${descriptor.title} 닫기`, '×');
  actions.append(pin, lock, compact, focus, close);
  titlebar.append(identity, actions);

  const content = documentValue.createElement('div');
  content.className = 'cockpit-panel-content';
  panel.append(titlebar, content);

  const handles = new Map();
  for (const direction of RESIZE_HANDLES) {
    const handle = documentValue.createElement('div');
    handle.className = `cockpit-panel-resize cockpit-panel-resize-${direction}`;
    handle.dataset.panelResize = direction;
    handle.setAttribute('aria-hidden', 'true');
    panel.append(handle);
    handles.set(direction, handle);
  }
  host.append(panel);

  const disposers = [];
  function listen(element, name, listener, settings) {
    element.addEventListener(name, listener, settings);
    disposers.push(() => element.removeEventListener(name, listener, settings));
  }

  listen(panel, 'pointerdown', (event) => {
    options.onBringFront?.(descriptor.id);
    event.stopPropagation();
  });
  listen(panel, 'wheel', (event) => event.stopPropagation());
  listen(panel, 'dblclick', (event) => event.stopPropagation());
  listen(titlebar, 'pointerdown', (event) => {
    if (event.button !== 0 || event.target.closest('button')) return;
    event.preventDefault();
    event.stopPropagation();
    options.onInteractionStart?.(event, descriptor.id, 'move', '');
  });
  for (const [direction, handle] of handles) {
    listen(handle, 'pointerdown', (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      options.onInteractionStart?.(event, descriptor.id, 'resize', direction);
    });
  }
  for (const button of actions.querySelectorAll('button')) {
    listen(button, 'click', (event) => {
      event.stopPropagation();
      options.onAction?.(descriptor.id, button.dataset.panelAction);
    });
  }

  function update(state, interaction = {}) {
    const layoutEditable = interaction.layoutEditable !== false;
    panel.hidden = !state.visible;
    panel.dataset.mode = state.mode;
    panel.dataset.dock = state.dock || '';
    panel.dataset.layoutEditable = String(layoutEditable);
    panel.classList.toggle('is-compact', state.mode === 'compact');
    panel.classList.toggle('is-focus', state.mode === 'focus');
    panel.classList.toggle('is-pinned', state.pinned);
    panel.classList.toggle('is-locked', state.locked);
    panel.classList.toggle('is-docked', Boolean(state.dock));
    panel.classList.toggle('is-gamepad-selected', Boolean(interaction.gamepadSelected));
    panel.setAttribute('aria-current', interaction.gamepadSelected ? 'true' : 'false');
    panel.style.width = `${state.width}px`;
    panel.style.height = `${state.height}px`;
    panel.style.transform = `translate3d(${state.x}px, ${state.y}px, 0)`;
    panel.style.zIndex = String(state.zIndex);
    pin.setAttribute('aria-pressed', String(state.pinned));
    lock.setAttribute('aria-pressed', String(state.locked));
    pin.disabled = !layoutEditable;
    lock.disabled = !layoutEditable;
    close.disabled = !layoutEditable;
    compact.setAttribute('aria-pressed', String(state.mode === 'compact'));
    focus.setAttribute('aria-pressed', String(state.mode === 'focus'));
    compact.setAttribute('aria-label', `${descriptor.title} ${state.mode === 'compact' ? '복원' : '최소화'}`);
    focus.setAttribute('aria-label', `${descriptor.title} ${state.mode === 'focus' ? 'Focus 해제' : 'Focus'}`);
  }

  function destroy() {
    disposers.splice(0).forEach((dispose) => dispose());
    panel.remove();
  }

  return Object.freeze({ panel, titlebar, content, update, focus: () => panel.focus(), destroy });
}
