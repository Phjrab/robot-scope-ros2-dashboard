import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { COCKPIT_LAYOUT_MODES, createLayoutModeController, reduceLayoutMode } from '../robot_dashboard/static/features/cockpit/layout_mode.js';
import { projectSafetyHud } from '../robot_dashboard/static/features/cockpit/safety_hud.js';

const NOW = 10_000;

function liveInput() {
  return {
    stateUpdatedAt: 9_000,
    controlUpdatedAt: 9_000,
    state: {
      health: { agent_ready: true, robot_target_connected: true, robot_online: true },
      sensors: [
        { category: 'robot_state', topic: '/lowstate', state: 'ok', age_s: 0.04, values: {} },
        { category: 'battery', state: 'ok', age_s: 0.1, values: { battery_soc: 83 } },
      ],
    },
    control: {
      lease: { active: true, source: 'keyboard' }, estop_latched: false,
      command: { deadman: true, linear_x: 0.2, linear_y: -0.1, angular_z: 0.3, speed_scale: 0.4 },
    },
    navigationAvailable: true,
    navigation: { pipeline: { state: 'idle' }, goal: { state: 'idle' } },
  };
}

test('Safety HUD projects every fixed field from fresh bounded state', () => {
  const projected = projectSafetyHud(liveInput(), NOW);
  assert.deepEqual({
    source: projected['control-source'], armed: projected.armed, deadman: projected.deadman,
    stop: projected['software-stop'], lease: projected.lease, link: projected['go2-link'],
    lowstate: projected.lowstate, battery: projected.battery, vx: projected.vx,
    vy: projected.vy, wz: projected.wz, scale: projected['speed-scale'], tone: projected.tone,
  }, {
    source: 'MANUAL', armed: 'ARMED', deadman: 'HELD', stop: 'CLEAR', lease: 'ACTIVE', link: 'LIVE',
    lowstate: '40 ms', battery: '83%', vx: '+0.200', vy: '-0.100', wz: '+0.300', scale: '40%', tone: 'normal',
  });
});

test('Safety HUD fails closed instead of retaining cached control and telemetry values', () => {
  const stale = projectSafetyHud(liveInput(), NOW + 3_000);
  assert.equal(stale['control-source'], 'NONE');
  assert.equal(stale.armed, 'UNKNOWN · LOCKED');
  assert.equal(stale.deadman, 'UNKNOWN');
  assert.equal(stale['software-stop'], 'UNKNOWN');
  assert.equal(stale.lease, 'UNKNOWN · LOCKED');
  assert.equal(stale['go2-link'], 'STALE');
  assert.equal(stale.lowstate, 'WAITING');
  assert.equal(stale.battery, 'WAITING');
  assert.equal(stale.vx, 'UNKNOWN');
  assert.equal(stale['speed-scale'], 'UNKNOWN');
  assert.equal(stale.layoutArmed, true, 'a stale previously active lease keeps layout fail-closed');
  assert.equal(stale.tone, 'danger');
});

test('Navigation ownership is displayed without weakening the manual conflict warning', () => {
  const input = liveInput();
  input.control.lease.active = false;
  input.control.command.deadman = false;
  input.navigation.pipeline.state = 'running';
  const projected = projectSafetyHud(input, NOW);
  assert.equal(projected['control-source'], 'NAVIGATION');
  assert.equal(projected.armed, 'DISARMED');
});

test('layout mode is explicit, ARM auto-locks, and stale generations cannot unlock it', () => {
  const initial = reduceLayoutMode(undefined, {});
  assert.equal(initial.mode, COCKPIT_LAYOUT_MODES.OPERATE);
  const changes = [];
  const controller = createLayoutModeController({ onChange: (state) => changes.push(state) });
  assert.equal(controller.requestEdit().mode, COCKPIT_LAYOUT_MODES.EDIT);
  assert.equal(controller.updateControl({ armed: true, generation: 4 }).mode, COCKPIT_LAYOUT_MODES.OPERATE);
  assert.equal(controller.requestEdit().mode, COCKPIT_LAYOUT_MODES.OPERATE);
  assert.equal(controller.updateControl({ armed: false, generation: 3 }).armed, true);
  assert.equal(controller.updateControl({ armed: false, generation: 5 }).armed, false);
  assert.equal(controller.snapshot().mode, COCKPIT_LAYOUT_MODES.OPERATE);
  assert.equal(controller.requestEdit().mode, COCKPIT_LAYOUT_MODES.EDIT);
  assert.equal(controller.apply().mode, COCKPIT_LAYOUT_MODES.OPERATE);
  assert.ok(changes.length >= 5);
});

test('Cockpit reuses existing control endpoints and polling generation fences', () => {
  const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
  assert.match(app, /\['controls', 'navigation', 'cockpit'\]\.includes\(activePage\)/);
  assert.match(app, /const armGenerationAtRequest = controlArmGeneration/);
  assert.match(app, /armGenerationAtRequest !== controlArmGeneration/);
  assert.match(app, /onSoftwareStop: \(\) => triggerEmergencyStop\('cockpit_hud'\)/);
  assert.doesNotMatch(app, /cockpit[\s\S]{0,160}\/api\/v1\/control\/(?:arm|disarm)/i);
});
