// Observe the unchanged shared backend across actual Playwright context closure.
// All WebSockets are intercepted in-memory; no server or device is contacted.
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

const repo = resolve(process.argv[2] || '.');
const require = createRequire(resolve(repo, 'package.json'));
const { chromium } = require('playwright');
const { installDashboardBackend } = await import(pathToFileURL(resolve(repo, 'tests/e2e/dashboard_backend.mjs')));
const originalSet = globalThis.setInterval;
const originalClear = globalThis.clearInterval;
const timers = new Map();
globalThis.setInterval = (fn, ms, ...args) => {
  const owned = new Error().stack.includes('tests/e2e/dashboard_backend.mjs');
  if (!owned) return originalSet(fn, ms, ...args);
  const row = { ms, calls: 0, cleared: false };
  const timer = originalSet(() => { row.calls++; fn(...args); }, ms);
  timers.set(timer, row);
  return timer;
};
globalThis.clearInterval = timer => {
  if (timers.has(timer)) timers.get(timer).cleared = true;
  return originalClear(timer);
};
let browser;
const rounds = [];
try {
  browser = await chromium.launch({ headless: true });
  for (let i = 0; i < 3; i++) {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const backend = await installDashboardBackend(page);
      // Navigate after route registration so the WebSocket interceptor is
      // installed in a same-origin document. The document itself is fulfilled
      // in-memory; no listener exists or is needed on this port.
      await page.route('http://127.0.0.1:4173/', route => route.fulfill({
        contentType: 'text/html', body: '<!doctype html><title>Synthetic socket lifetime probe</title>',
      }));
      await page.goto('http://127.0.0.1:4173/');
      await page.evaluate(() => new Promise((resolve, reject) => {
        const socket = new WebSocket('ws://127.0.0.1:4173/api/v1/ws/camera?source_id=realsense_color');
        socket.onmessage = () => resolve(); socket.onerror = reject;
      }));
      assert.equal(backend.state.wsConnections.camera, 1);
      await context.close();
      const callsBefore = [...timers.values()].reduce((n, row) => n + row.calls, 0);
      await delay(300);
      rounds.push({ round: i + 1, contextClosed: true, socketCloseCallbacks: backend.state.wsCloses.camera,
        unclearedIntervals: [...timers.values()].filter(row => !row.cleared).length,
        callbacksAfterContextClose: [...timers.values()].reduce((n, row) => n + row.calls, 0) - callsBefore });
    } finally { await context.close(); }
  }
  console.log(JSON.stringify({
    result: rounds.some(row => row.unclearedIntervals) ? 'REPRODUCED_SHARED_FIXTURE_TIMER_LEAK' : 'NO_LEAK_OBSERVED',
    sha: execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    playwright: require('playwright/package.json').version, browser: browser.version(), rounds,
    cleanup: 'All intervals captured by this probe are cleared in finally.',
  }, null, 2));
} finally {
  for (const timer of timers.keys()) originalClear(timer);
  globalThis.setInterval = originalSet;
  globalThis.clearInterval = originalClear;
  await browser?.close();
}
