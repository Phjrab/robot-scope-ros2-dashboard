import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const start = source.indexOf("window.addEventListener('blur',");
const end = source.indexOf("window.addEventListener('pagehide',", start);
assert.ok(start >= 0 && end > start, 'blur and visibility event registrations must exist');
const pauseStart = source.indexOf('function pausePreNavigationPlacement()');
const pauseEnd = source.indexOf('function navigationPosePlacementAllowed(', pauseStart);
assert.ok(pauseStart >= 0 && pauseEnd > pauseStart, 'the real placement pause handler must exist');

function fixture(failure = null, hidden = true, dragging = false) {
  const calls = [], errors = [];
  function target(extra = {}) {
    const handlers = new Map();
    return { ...extra, addEventListener(name, fn) { handlers.set(name, [...(handlers.get(name) || []), fn]); },
      dispatch(name) { for (const fn of handlers.get(name) || []) { try { fn(); } catch (error) { errors.push(error.message); } } } };
  }
  const window = target(), document = target({ hidden });
  const draft = { preBinding: 'draft', stale: false };
  const mark = name => () => { calls.push(name); if (failure === name) throw new Error(name); };
  const sandbox = { window, document, navigationPointer: dragging ? { preBinding: 'draft' } : null, navigationStagedPose: draft, navigationPreDraftToolBinding: null,
    navigationMapTool: 'initial', navigationPreparation: { draftChanged: mark('revoke') },
    preNavigationDraft: { suspend() { calls.push('suspend'); if (failure === 'suspend') throw new Error('suspend'); draft.stale = true; } },
    renderNavigationPoseSelection: mark('render'), scheduleNavigationMapDraw: mark('draw'), controlArmBusy: true,
    invalidatePendingArm: mark('invalidate'), controlLeaseId: 'lease', failSafeDisarm: reason => calls.push(`disarm:${reason}`),
    syncPointcloudTransport: mark('pointcloud'), cameraRecording: {},
    cameraRecordingCleanupPolicy: reason => ({ reason, discard: false }), stopCameraRecording: policy => calls.push(`recording:${policy.reason}:${policy.discard}`),
    cockpitWorkspace: { deactivate: mark('deactivate'), activate: mark('activate') }, activePage: 'navigation',
    syncCameraTransport: mark('camera'), syncCockpitScene: mark('cockpitScene'), Date };
  runInNewContext(source.slice(pauseStart, pauseEnd) + source.slice(start, end), sandbox);
  return { window, document, calls, errors, draft };
}

for (const dragging of [false, true]) for (const failure of [null, 'revoke', 'render', ...(dragging ? ['suspend'] : [])]) {
  test(`blur preserves fail-safe before ${dragging ? 'partial' : 'completed'} draft work (${failure || 'normal'})`, () => {
    const f = fixture(failure, true, dragging); f.window.dispatch('blur');
    assert.deepEqual(f.calls.slice(0, 2), ['invalidate', 'disarm:window_blurred']);
    assert.equal(f.calls.includes('suspend'), dragging);
    assert.equal(f.calls.includes('revoke'), failure !== 'suspend');
    assert.equal(f.draft.stale, dragging && failure !== 'suspend');
    assert.deepEqual(f.errors, failure ? [failure] : []);
  });
  test(`hidden visibility preserves disarm and recording cleanup for ${dragging ? 'partial' : 'completed'} draft (${failure || 'normal'})`, () => {
    const f = fixture(failure, true, dragging); f.document.dispatch('visibilitychange');
    assert.deepEqual(f.calls.slice(0, 5), ['pointcloud', 'invalidate', 'disarm:document_hidden', 'recording:visibility_hidden:false', 'deactivate']);
    assert.ok(f.calls.indexOf('camera') < f.calls.indexOf(dragging ? 'suspend' : 'revoke'));
    assert.equal(f.draft.stale, dragging && failure !== 'suspend');
    assert.deepEqual(f.errors, failure ? [failure] : []);
  });
}

test('visible events do not suspend the draft', () => {
  const f = fixture(null, false); f.document.dispatch('visibilitychange');
  assert.deepEqual(f.calls, ['pointcloud', 'camera']);
  assert.equal(f.draft.stale, false);
});
