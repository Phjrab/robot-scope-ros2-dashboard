import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COCKPIT_WINDOW_MODE,
  COCKPIT_WINDOW_NAME,
  cockpitWindowFeatures,
  cockpitWindowUrl,
  dashboardWindowUrl,
  initializeCockpitWindowMode,
  openCockpitWorkspaceWindow,
  toggleDocumentFullscreen,
  workspaceWindowMode,
} from '../robot_dashboard/static/features/cockpit/window_mode.js';

test('Cockpit full-window mode is strictly allowlisted', () => {
  assert.equal(workspaceWindowMode('https://dashboard.test/?workspace=cockpit#overview'), COCKPIT_WINDOW_MODE);
  for (const href of [
    'https://dashboard.test/#cockpit',
    'https://dashboard.test/?workspace=controls#cockpit',
    'https://dashboard.test/?workspace=Cockpit#cockpit',
    'https://dashboard.test/?workspace=%20cockpit#cockpit',
    'https://dashboard.test/?workspace=cockpit&workspace=cockpit#cockpit',
  ]) {
    assert.equal(workspaceWindowMode(href), null, href);
  }
});

test('Cockpit full-window and dashboard URLs stay same-origin and canonical', () => {
  const source = 'https://dashboard.test/ui/?unsafe=discarded&workspace=controls#navigation';
  assert.equal(cockpitWindowUrl(source), 'https://dashboard.test/ui/?workspace=cockpit#cockpit');
  assert.equal(dashboardWindowUrl(source), 'https://dashboard.test/ui/#overview');
});

test('Cockpit popup geometry is numeric, bounded, and multi-monitor aware', () => {
  assert.equal(
    cockpitWindowFeatures(
      { availWidth: 1920.9, availHeight: 1080.4, availLeft: -1920, availTop: 0 },
      { outerWidth: 800, outerHeight: 600 },
    ),
    'popup=yes,resizable=yes,scrollbars=no,width=1920,height=1080,left=-1920,top=0',
  );
  assert.equal(
    cockpitWindowFeatures(
      { availWidth: Number.NaN, availHeight: 0, availLeft: Number.NaN, availTop: Number.POSITIVE_INFINITY },
      { outerWidth: 1200, outerHeight: 700 },
    ),
    'popup=yes,resizable=yes,scrollbars=no,width=1200,height=700,left=0,top=0',
  );
});

test('Cockpit launcher reuses one named target, focuses it, and severs opener access', () => {
  const calls = [];
  const popup = {
    opener: {},
    focusCalls: 0,
    focus() { this.focusCalls += 1; },
  };
  const windowValue = {
    location: { href: 'https://dashboard.test/ui/#cockpit' },
    screen: { availWidth: 1600, availHeight: 900, availLeft: 20, availTop: 30 },
    outerWidth: 1000,
    outerHeight: 700,
    open(...args) { calls.push(args); return popup; },
  };

  const first = openCockpitWorkspaceWindow(windowValue);
  const second = openCockpitWorkspaceWindow(windowValue);
  assert.equal(first.opened, true);
  assert.equal(second.opened, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0][0], 'https://dashboard.test/ui/?workspace=cockpit#cockpit');
  assert.equal(calls[0][1], COCKPIT_WINDOW_NAME);
  assert.equal(calls[1][1], COCKPIT_WINDOW_NAME);
  assert.match(calls[0][2], /popup=yes/);
  assert.equal(popup.focusCalls, 2);
  assert.equal(popup.opener, null);
});

test('Cockpit launcher reports popup blocking without a fallback mutation', () => {
  const result = openCockpitWorkspaceWindow({
    location: { href: 'https://dashboard.test/#cockpit' },
    screen: {},
    open() { return null; },
  });
  assert.equal(result.opened, false);
  assert.equal(result.reason, 'blocked');
  assert.equal(result.popup, null);
});

test('Cockpit native fullscreen is entered and exited only by an explicit toggle', async () => {
  let requests = 0;
  let exits = 0;
  const root = { async requestFullscreen() { requests += 1; } };
  const documentValue = {
    documentElement: root,
    fullscreenElement: null,
    async exitFullscreen() { exits += 1; },
  };

  assert.deepEqual({ requests, exits }, { requests: 0, exits: 0 });
  assert.equal(await toggleDocumentFullscreen(documentValue), true);
  assert.deepEqual({ requests, exits }, { requests: 1, exits: 0 });
  documentValue.fullscreenElement = root;
  assert.equal(await toggleDocumentFullscreen(documentValue), false);
  assert.deepEqual({ requests, exits }, { requests: 1, exits: 1 });
  await assert.rejects(() => toggleDocumentFullscreen({ documentElement: {} }), /Fullscreen is unavailable/);
});

test('Cockpit full-window controller owns DOM bindings and strict route projection', () => {
  class FakeElement extends EventTarget {
    constructor() { super(); this.hidden = true; this.attributes = new Map(); this.textContent = ''; }
    setAttribute(name, value) { this.attributes.set(name, value); }
  }
  const elements = new Map([
    ['#cockpitOpenWindowButton', new FakeElement()],
    ['#cockpitWindowBar', new FakeElement()],
    ['#cockpitFullscreenButton', new FakeElement()],
    ['#cockpitCloseWindowButton', new FakeElement()],
  ]);
  const documentValue = new EventTarget();
  documentValue.documentElement = { dataset: {} };
  documentValue.querySelector = (selector) => elements.get(selector) || null;
  documentValue.fullscreenElement = null;
  documentValue.title = '';
  const popup = { opener: {}, focus() {} };
  let opened = 0;
  const windowValue = {
    location: { href: 'https://dashboard.test/?workspace=cockpit#controls', hash: '#controls' },
    screen: {},
    open() { return popup; },
    setTimeout() {},
  };

  const controller = initializeCockpitWindowMode({ windowValue, documentValue, onOpened: () => { opened += 1; } });
  assert.equal(controller.mode, COCKPIT_WINDOW_MODE);
  assert.equal(controller.pageFromHash({ overview: true, cockpit: true, controls: true }), 'cockpit');
  assert.equal(controller.resolvePage('controls'), 'cockpit');
  assert.equal(controller.shouldReplaceHash(false), true);
  assert.equal(documentValue.documentElement.dataset.workspaceWindow, 'cockpit');
  assert.equal(documentValue.title, 'Robot Cockpit · Robot Scope');
  assert.equal(elements.get('#cockpitWindowBar').hidden, false);
  assert.equal(windowValue.RobotScopeCockpitWindow, controller);

  elements.get('#cockpitOpenWindowButton').dispatchEvent(new Event('click'));
  assert.equal(opened, 1);
  assert.equal(popup.opener, null);
  controller.destroy();
  elements.get('#cockpitOpenWindowButton').dispatchEvent(new Event('click'));
  assert.equal(opened, 1, 'destroy removes the launcher binding');
});
