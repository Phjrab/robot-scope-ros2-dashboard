import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../robot_dashboard/static/', import.meta.url);
const index = readFileSync(new URL('index.html', root), 'utf8');
const app = readFileSync(new URL('app.js', root), 'utf8');
const feature = readFileSync(new URL('features/sensors/realsense_profile.js', root), 'utf8');
const styles = readFileSync(new URL('styles.css', root), 'utf8');

test('Sensors exposes a bounded RealSense resolution selector', () => {
  for (const id of ['realsenseProfileHeading', 'realsenseProfileStatus', 'realsenseProfileSelect', 'realsenseProfileApply']) {
    assert.match(index, new RegExp(`id="${id}"`));
  }
  assert.match(index, /RealSense relay만 잠시 재시작/);
  assert.match(index, /데이터셋 녹화 중에는 변경할 수 없습니다/);
  assert.match(styles, /\.realsense-profile-control \{ display:grid/);
  assert.match(styles, /@media \(max-width: 520px\)[\s\S]*?\.realsense-profile-control \{ grid-template-columns:1fr/);
});

test('profile feature uses only the fixed API and explicit confirmation', () => {
  assert.match(app, /initializeRealSenseProfileFeature/);
  assert.match(feature, /api\('\/api\/v1\/cameras\/realsense\/profile'\)/);
  assert.match(feature, /method: 'POST'/);
  assert.match(feature, /JSON\.stringify\(\{ resolution, confirmed: true \}\)/);
  assert.match(feature, /window\.confirm/);
  for (const forbidden of ['host:', 'port:', 'service_name', 'command:', 'shell:', 'password:']) {
    assert.doesNotMatch(feature, new RegExp(forbidden, 'i'));
  }
});

test('dataset capture and remote status blockers are rendered fail closed', () => {
  assert.match(feature, /dataset_capture_active/);
  assert.match(feature, /remote_status_unavailable/);
  assert.match(feature, /ui\.select\.disabled = busy \|\| !snapshot\?\.can_apply/);
  assert.match(feature, /ui\.apply\.disabled = busy \|\| !snapshot\?\.can_apply \|\| !changed/);
});

test('operator resolution selection survives render and polling until apply succeeds', () => {
  assert.match(feature, /let selectionDirty = false/);
  assert.match(feature, /!selectionDirty \|\| !ids\.includes\(ui\.select\.value\)/);
  assert.match(feature, /selectionDirty = Boolean\([\s\S]*?ui\.select\.value !== snapshot\.selected\.profile/);
  assert.match(feature, /snapshot = await api\([\s\S]*?selectionDirty = false/);
});
