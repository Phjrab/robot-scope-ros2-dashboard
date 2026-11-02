import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const source = readFileSync(new URL('../../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const start = source.indexOf("window.addEventListener('blur',");
const end = source.indexOf("window.addEventListener('pagehide',", start);
if (start < 0 || end <= start) throw new Error('event registrations missing');
const registrations = source.slice(start, end);

for (const failure of ['suspend', 'render']) {
  for (const event of ['blur', 'visibilitychange']) {
    test(`${event} safety completes before draft ${failure} throws`, async ({ page }) => {
      const calls = await page.evaluate(({ registrations, failure, event }) => {
        // Native EventTarget reports listener exceptions without cancelling later listeners.
        window.addEventListener('error', e => e.preventDefault());
        const calls = [], win = new EventTarget(), doc = new EventTarget();
        doc.hidden = true;
        const draft = { preBinding: 'draft', stale: false };
        const mark = name => () => { calls.push(name); if (failure === name) throw new Error(name); };
        const bindings = { window: win, document: doc, navigationPointer: null, navigationStagedPose: draft,
          navigationPreDraftToolBinding: null, preNavigationDraft: { suspend: mark('suspend') },
          renderNavigationPoseSelection: mark('render'), scheduleNavigationMapDraw: mark('draw'),
          controlArmBusy: true, invalidatePendingArm: mark('invalidate'), controlLeaseId: 'lease',
          failSafeDisarm: reason => calls.push(`disarm:${reason}`), syncPointcloudTransport: mark('pointcloud'),
          cameraRecording: {}, cameraRecordingCleanupPolicy: reason => ({ reason, discard: false }),
          stopCameraRecording: policy => calls.push(`recording:${policy.reason}:${policy.discard}`),
          cockpitWorkspace: { deactivate: mark('deactivate') }, activePage: 'navigation', syncCameraTransport: mark('camera') };
        new Function(...Object.keys(bindings), registrations)(...Object.values(bindings));
        (event === 'blur' ? win : doc).dispatchEvent(new Event(event));
        return calls;
      }, { registrations, failure, event });
      if (event === 'blur') expect(calls.slice(0, 2)).toEqual(['invalidate', 'disarm:window_blurred']);
      else expect(calls.slice(0, 6)).toEqual(['pointcloud', 'invalidate', 'disarm:document_hidden', 'recording:visibility_hidden:false', 'deactivate', 'camera']);
      expect(calls).toContain(failure);
    });
  }
}
