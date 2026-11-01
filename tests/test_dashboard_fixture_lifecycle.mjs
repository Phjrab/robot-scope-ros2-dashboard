import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { installDashboardBackend } from './e2e/dashboard_backend.mjs';
import { onFixtureSocketClose } from './e2e/fixture_socket_lifecycle.mjs';

function fakePage() {
  const page = new EventEmitter();
  page.route = async () => {};
  page.routeWebSocket = async (_, connect) => { page.connect = connect; };
  return page;
}
function fakeSocket(path) {
  return { sends: 0, closes: 0, url: () => `ws://localhost/api/v1/ws/${path}`,
    send() { this.sends++; }, close() { this.closes++; },
    onClose(callback) { this.closed = callback; } };
}
async function withClock(run) {
  const original = Object.fromEntries(['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout'].map(key => [key, globalThis[key]]));
  const timers = new Map(); let nextId = 0;
  globalThis.setInterval = globalThis.setTimeout = callback => { const id = ++nextId; timers.set(id, callback); return id; };
  globalThis.clearInterval = globalThis.clearTimeout = id => timers.delete(id);
  try { await run(timers); } finally { Object.assign(globalThis, original); }
}
for (const path of ['pointcloud', 'camera?source_id=go2_front']) {
  test(`fixture ${path} stops timers when the page closes without socket.onClose`, async () => withClock(async timers => {
    const page = fakePage(), socket = fakeSocket(path);
    await installDashboardBackend(page, { pointcloudFrame: () => Buffer.from('synthetic') });
    await page.connect(socket);
    assert.equal(timers.size, 1);
    for (const tick of timers.values()) tick();
    const sent = socket.sends;
    page.emit('close');
    for (const tick of timers.values()) tick();
    assert.equal(timers.size, 0);
    assert.equal(socket.sends, sent);
    assert.equal(page.listenerCount('close'), 0);
  }));
}
test('normal fixture socket close removes its page listener and is idempotent', async () => withClock(async timers => {
  const page = fakePage(), socket = fakeSocket('pointcloud');
  const backend = await installDashboardBackend(page, { pointcloudFrame: () => Buffer.from('synthetic') });
  await page.connect(socket);
  socket.closed(); socket.closed(); page.emit('close');
  assert.equal(timers.size, 0);
  assert.equal(backend.state.wsCloses.pointcloud, 1);
  assert.equal(page.listenerCount('close'), 0);
}));
test('fixture teardown cancels a pending reconnect callback', async () => withClock(async timers => {
  const page = fakePage(), socket = fakeSocket('pointcloud');
  await installDashboardBackend(page, { closeFirstSocket: 'pointcloud' });
  await page.connect(socket);
  assert.equal(timers.size, 1);
  page.emit('close');
  for (const tick of timers.values()) tick();
  assert.equal(timers.size, 0);
  assert.equal(socket.closes, 0);
}));
test('shared pose and joints cleanup runs once on either lifetime boundary', () => {
  for (const first of ['page', 'socket']) {
    const page = fakePage(), socket = fakeSocket('pose'); let cleanups = 0;
    onFixtureSocketClose(page, socket, () => { cleanups++; });
    if (first === 'page') page.emit('close'); else socket.closed();
    page.emit('close'); socket.closed();
    assert.equal(cleanups, 1);
    assert.equal(page.listenerCount('close'), 0);
  }
});
