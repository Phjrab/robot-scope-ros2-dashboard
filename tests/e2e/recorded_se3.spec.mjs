import { openExperimentFixture } from './experiment_view_fixture.mjs';
import { expect, test } from '@playwright/test';
import { recordedFixture } from '../recorded_se3_fixture.mjs';
const upload = (page, data) => page.locator('#recordedFile').setInputFiles({ name: 'fixture.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(data)) });
test('recorded overlay shows rejection, six degrees, original timestamps and metric official model without live IO', async ({ page }) => {
  const failures = [], requests = [], sockets = [];
  page.on('pageerror', e => failures.push(e.message));
  page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
  page.on('websocket', ws => sockets.push(ws.url()));
  await openExperimentFixture(page);
  await upload(page, recordedFixture());
  await expect(page.locator('#recordedContent')).toBeVisible();
  await expect(page.locator('#recordedKind')).toContainText('SYNTHETIC_FIXTURE');
  await expect(page.locator('#recordedDecision')).toContainText('REJECTED');
  await expect(page.locator('#recordedTimestamp')).toContainText('1792309179130175352');
  await expect(page.locator('#recordedPose')).toContainText('0.400');
  await expect(page.locator('#recordedPoseCaveat')).toContainText('본체 변환이 없어');
  await expect(page.locator('#recordedModel')).toContainText('공식 URDF 기반');
  await page.locator('#recordedAlignment').selectOption('before');
  await expect(page.locator('#recordedFrames')).toContainText('UNALIGNED_SESSION_COORDINATES');
  await page.locator('#recordedAlignment').selectOption('after');
  await page.locator('#recordedCenter').click();
  await page.locator('#recordedFit').click();
  await page.locator('#recordedRobot').uncheck();
  await page.locator('#clearRecorded').click();
  await expect(page.locator('#recordedContent')).toBeHidden();
  expect(failures).toEqual([]); expect(requests).toEqual([]); expect(sockets).toEqual([]);
});
test('stale capture, absent result and invalid replacement do not display prior result', async ({ page }) => {
  await openExperimentFixture(page);
  const r = recordedFixture(); r.captured_at = '2020-01-01T00:00:00Z';
  await upload(page, r);
  await expect(page.locator('#recordedKind')).toContainText('STALE_RECORDING');
  r.result = null; await upload(page, r);
  await expect(page.locator('#recordedDecision')).toContainText('NO_RESULT');
  await expect(page.locator('#recordedCenter')).toBeDisabled();
  await expect(page.locator('#recordedFrames')).toContainText('UNALIGNED_SESSION_COORDINATES');
  await expect(page.locator('#recordedAlignment')).toBeDisabled();
  r.source.point_semantics = 'RAW_SENSOR'; await upload(page, r);
  await expect(page.locator('#recordedStatus')).toContainText('INVALID');
  await expect(page.locator('#recordedContent')).toBeHidden();
});
test('unverified body transform is diagnostic and asset failure has an explicit fallback', async ({ page }) => {
  let requests = 0;
  await page.route('**/go2-official-lite.json', route => { requests += 1; return route.abort(); });
  await openExperimentFixture(page);
  const r = recordedFixture(); r.body_relation = { verified: false, source_frame: r.source.frame_id,
    source_session: r.source.session_id, body_frame: 'base_link', provenance: 'fixture only',
    T_source_body: [[1, 0, 0, .25], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] };
  await upload(page, r);
  await expect(page.locator('#recordedPoseCaveat')).toContainText('미검증 body 후보');
  await expect(page.locator('#recordedModel')).toContainText('fallback');
  await page.locator('#recordedAlignment').selectOption('before');
  await page.locator('#recordedAlignment').selectOption('after');
  await page.locator('#recordedFit').click();
  expect(requests).toBe(1);
});
