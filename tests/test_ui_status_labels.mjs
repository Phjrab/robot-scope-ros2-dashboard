import assert from 'node:assert/strict';
import test from 'node:test';
import { statusLabel, navigationBlockerLabel } from '../robot_dashboard/static/features/cockpit/status_labels.js';

test('waiting, disconnected, stale and unknown remain distinct in Korean', () => {
  const labels = ['WAITING', 'OFFLINE', 'STALE', 'UNKNOWN'].map(statusLabel);
  assert.equal(new Set(labels).size, 4);
  assert.equal(statusLabel('WAITING'), '데이터 대기');
  assert.equal(statusLabel('STALE'), '오래된 데이터');
  assert.equal(statusLabel('UNKNOWN'), '확인 안 됨');
  assert.notEqual(statusLabel('UNKNOWN'), statusLabel('READY'));
});

test('unknown state and blocker codes stay verbatim instead of acquiring an invented cause', () => {
  const unknown = 'vendor_specific_fault_42';
  assert.equal(statusLabel(unknown), unknown);
  assert.equal(navigationBlockerLabel(unknown), unknown);
  assert.equal(navigationBlockerLabel('<unknown_code>'), '<unknown_code>');
  assert.equal(statusLabel(null), '');
  assert.equal(navigationBlockerLabel(null), '');
});

test('synthetic and replay labels never describe live data', () => {
  assert.equal(statusLabel('FIXTURE'), '합성 예시');
  assert.equal(statusLabel('REPLAY'), '기록 재생');
  assert.equal(statusLabel('LIVE'), '실시간 수신');
});

test('navigation blockers identify only their reported condition and a relevant check', () => {
  assert.equal(navigationBlockerLabel('lowstate_stale'), '로봇 상태 정보가 오래되었습니다. LowState 상태 수신을 확인하세요.');
  assert.match(navigationBlockerLabel('bridge_or_lowstate_unavailable'), /제어 연결 또는 로봇 상태 정보/);
  assert.match(navigationBlockerLabel('control_target_mismatch'), /주행 제어 대상이 일치하지 않습니다/);
  assert.match(navigationBlockerLabel('cmd_vel_publisher_count'), /발행자가 하나인지 확인/);
});
