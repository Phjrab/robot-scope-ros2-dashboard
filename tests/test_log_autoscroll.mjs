import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const navigationLogSource = readFileSync(new URL('../robot_dashboard/static/features/navigation/log_controller.js', import.meta.url), 'utf8');
const scrollSource = readFileSync(new URL('../robot_dashboard/static/core/log_scroll.js', import.meta.url), 'utf8');
const helperStart = scrollSource.indexOf('export const LOG_SCROLL_BOTTOM_TOLERANCE_PX');
const helperEnd = scrollSource.length;
assert.ok(helperStart >= 0 && helperEnd > helperStart, 'sticky log scroll helpers must be extractable');
const helperSource = scrollSource.slice(helperStart, helperEnd).replaceAll('export ', '');

function createHarness() {
  const frames = [];
  const context = {
    requestAnimationFrame(callback) {
      frames.push(callback);
      return frames.length;
    },
  };
  vm.runInNewContext(`
    ${helperSource}
    this.capture = captureStickyLogScroll;
    this.schedule = scheduleStickyLogScroll;
  `, context);
  return {
    capture: context.capture,
    schedule: context.schedule,
    flush() {
      const pending = frames.splice(0);
      pending.forEach((callback) => callback());
    },
  };
}

function terminal({ scrollTop, scrollHeight = 1000, clientHeight = 200 }) {
  return { scrollTop, scrollHeight, clientHeight };
}

test('sticky logs follow only while within the 16px bottom tolerance', () => {
  const { capture } = createHarness();
  assert.equal(capture(terminal({ scrollTop: 784 })).follow, true);
  assert.equal(capture(terminal({ scrollTop: 783 })).follow, false);
  assert.equal(capture(terminal({ scrollTop: 800 }), false).follow, false);
  assert.equal(capture(terminal({ scrollTop: 0, scrollHeight: 100, clientHeight: 200 })).follow, true);
});

test('mapping-style proximity preserves a scrolled-up view and resumes at the bottom', () => {
  const harness = createHarness();
  const output = terminal({ scrollTop: 240 });
  const paused = harness.capture(output);
  output.scrollHeight = 1100;
  harness.schedule(output, paused);
  harness.flush();
  assert.equal(output.scrollTop, 240, 'an append must not pull a scrolled-up mapping log down');

  output.scrollTop = 884;
  const resumed = harness.capture(output);
  assert.equal(resumed.follow, true, 'manually returning within 16px resumes follow mode');
  output.scrollHeight = 1200;
  harness.schedule(output, resumed);
  harness.flush();
  assert.equal(output.scrollTop, 1000);
});

test('navigation auto-scroll respects manual pause and explicit re-enable', () => {
  const harness = createHarness();
  const output = terminal({ scrollTop: 300 });
  const manuallyPaused = harness.capture(output, true);
  output.scrollHeight = 1100;
  harness.schedule(output, manuallyPaused);
  harness.flush();
  assert.equal(output.scrollTop, 300, 'checked auto-scroll still pauses after a manual scroll up');

  output.scrollTop = 900;
  const disabled = harness.capture(output, false);
  output.scrollHeight = 1200;
  harness.schedule(output, disabled);
  harness.flush();
  assert.equal(output.scrollTop, 900, 'an unchecked auto-scroll never follows new output');

  harness.schedule(output, harness.capture(output, false), { forceBottom: true });
  harness.flush();
  assert.equal(output.scrollTop, 1000, 'explicitly re-enabling auto-scroll follows the latest line');
});

test('an intervening user scroll wins the render-to-animation-frame race', () => {
  const harness = createHarness();
  const output = terminal({ scrollTop: 800 });
  const following = harness.capture(output, true);
  output.scrollHeight = 1100;
  harness.schedule(output, following);
  output.scrollTop = 420;
  harness.flush();
  assert.equal(output.scrollTop, 420);
});

test('both terminal panels use the shared sticky contract without unconditional bottom writes', () => {
  const mappingStart = appSource.indexOf('function scheduleMappingLogScroll(');
  const mappingEnd = appSource.indexOf('\nasync function refreshMappingControl(', mappingStart);
  const mappingSource = appSource.slice(mappingStart, mappingEnd);
  assert.match(mappingSource, /captureStickyLogScroll\(ui\.mappingLog\)/);
  assert.match(mappingSource, /scheduleMappingLogScroll\(logScrollSnapshot\)/);
  assert.doesNotMatch(mappingSource, /mappingLog\.scrollTop\s*=\s*ui\.mappingLog\.scrollHeight/);

  const navigationStart = navigationLogSource.indexOf('function scheduleNavigationLogScroll(');
  const navigationEnd = navigationLogSource.indexOf('\nfunction resetNavigationLogView(', navigationStart);
  const navigationSource = navigationLogSource.slice(navigationStart, navigationEnd);
  assert.match(navigationSource, /captureStickyLogScroll\([\s\S]*?navigationLogAutoScroll\.checked/);
  assert.match(navigationSource, /scheduleNavigationLogScroll\(logScrollSnapshot\)/);
  assert.doesNotMatch(navigationSource, /navigationLogOutput\.scrollTop\s*=\s*ui\.navigationLogOutput\.scrollHeight/);

  assert.match(navigationLogSource, /navigationLogAutoScroll\?\.addEventListener\('change',[\s\S]*?forceBottom: true/);
});
