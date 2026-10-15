import { worldToGrid, gridToWorld } from '../route_planner/spatial_editor.js';
export { worldToGrid, gridToWorld };
export const id = () => globalThis.crypto.randomUUID().replaceAll('-', '');
export const requestId = () => id();
export function newVisit(pose, label = '새 방문') {
  return { visit_id: id(), label, kind: 'STOP', target: 'mission_local_pose', annotation_id: null, pose: { x: pose.x, y: pose.y, yaw: pose.yaw || 0 }, heading_yaw: null, hold_seconds: 0, requires_operator_confirmation: false, after_arrival_confirmation: false, arrival_tolerance: null, speed: 'DEFAULT', action: 'none' };
}
export function resolvedTarget(visit, annotations) {
  const point = visit.pose || annotations?.points?.find((p) => p.id === visit.annotation_id)?.pose;
  return point ? { ...point, yaw: visit.heading_yaw ?? point.yaw ?? 0 } : null;
}
export function headingToNext(visits, selected, annotations) {
  const index = visits.findIndex((v) => v.visit_id === selected);
  const from = index < 0 ? null : resolvedTarget(visits[index], annotations);
  const to = visits[index + 1] && resolvedTarget(visits[index + 1], annotations);
  if (!from || !to || Math.hypot(to.x - from.x, to.y - from.y) < 0.000001) return null;
  return Math.atan2(to.y - from.y, to.x - from.x);
}
export function createDraftStore(onChange = () => {}) {
  let draft = null, saved = null, selected = null, dirty = false, history = [], generation = 0, preview = null, batching = false, batchRemembered = false;
  const clone = (v) => v == null ? v : structuredClone(v);
  const snapshot = () => ({ draft: clone(draft), saved: clone(saved), selected, dirty, generation, preview: clone(preview) });
  const notify = () => onChange(snapshot());
  function edit(change) { if (!draft) return; if (!batching || !batchRemembered) { history.push(clone(draft)); if (history.length > 30) history.shift(); batchRemembered = true; } change(draft); dirty = true; generation++; preview = null; notify(); }
  return {
    load(entry) { saved = clone(entry); draft = clone(entry.definition); selected = draft.visits.find((v) => v.visit_id === selected)?.visit_id || draft.visits[0]?.visit_id; dirty = false; preview = null; generation++; history = []; notify(); },
    fresh(definition) { this.load({ id: null, revision: null, definition }); dirty = true; notify(); },
    acceptSave(entry, expectedGeneration) {
      if (generation === expectedGeneration) { this.load(entry); return true; }
      // The response commits the submitted draft, not edits made while awaiting it.
      saved = clone(entry); dirty = true; preview = null; notify(); return false;
    },
    restore(value) {
      if (!value?.draft || typeof value.draft.label !== 'string' || !Array.isArray(value.draft.visits) || value.draft.visits.length > 32 || !value.draft.visits.every((v) => v && /^[0-9a-f]{32}$/.test(v.visit_id))) return false;
      draft = clone(value.draft); saved = clone(value.saved); selected = draft.visits.find((v) => v.visit_id === value.selected)?.visit_id || draft.visits[0]?.visit_id; dirty = value.dirty === true; preview = null; generation++; history = []; notify(); return true;
    },
    clear() { draft = null; saved = null; selected = null; dirty = false; history = []; preview = null; generation++; notify(); },
    snapshot,
    beginEdit() { batching = true; batchRemembered = false; },
    endEdit(cancel = false) { const revert = cancel && batching && batchRemembered; batching = false; batchRemembered = false; if (revert) this.undo(); },
    edit, select(value) { selected = value; notify(); },
    add(visit, after = selected) { if (!draft || draft.visits.length >= 32) throw new Error('방문은 최대 32개입니다.'); edit((d) => { const i = d.visits.findIndex((v) => v.visit_id === after); d.visits.splice(i < 0 ? d.visits.length : i + 1, 0, visit); }); selected = visit.visit_id; notify(); },
    update(patch) { edit((d) => { const visit = d.visits.find((v) => v.visit_id === selected); if (visit) Object.assign(visit, patch); }); },
    move(delta) { edit((d) => { const i = d.visits.findIndex((v) => v.visit_id === selected), j = i + delta; if (i >= 0 && j >= 0 && j < d.visits.length) [d.visits[i], d.visits[j]] = [d.visits[j], d.visits[i]]; }); },
    remove() { edit((d) => { d.visits = d.visits.filter((v) => v.visit_id !== selected); }); selected = draft?.visits[0]?.visit_id || null; notify(); },
    duplicate() { const v = draft?.visits.find((v) => v.visit_id === selected); if (v) this.add({ ...clone(v), visit_id: id() }); },
    undo() { if (history.length) { draft = history.pop(); selected = draft.visits.find((v) => v.visit_id === selected)?.visit_id || draft.visits[0]?.visit_id; dirty = true; preview = null; generation++; notify(); } },
    applyPreview(value, expectedGeneration) { if (expectedGeneration !== generation) return false; preview = clone(value); return true; },
    invalidate() { generation++; preview = null; },
    // Server polling intentionally cannot replace local draft or inputs.
    poll() { return this.snapshot(); },
  };
}
