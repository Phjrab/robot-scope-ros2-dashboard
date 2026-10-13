import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { installMissionFixture } from './ui_redesign_fixture.mjs';

const phase = process.env.TYPOGRAPHY_CAPTURE_PHASE || 'after';
const root = process.env.UI_EVIDENCE_ROOT || 'docs/ui-typography';
test.beforeAll(async () => {
  await mkdir(`${root}/captures/${phase}`, { recursive: true });
  await mkdir(`${root}/evidence`, { recursive: true });
});
const samples = [
  ['korean', 'ui', '로봇 연결 상태'], ['english', 'display', 'Map & Localization'],
  ['safety', 'ui', 'STOP · DISARMED'], ['topic', 'mono', '/camera/image_raw'],
  ['coordinate', 'mono', 'x: 1.250 m'], ['fps', 'mono', '15.0 FPS'],
  ['ambiguous', 'mono', '0 O 1 I l'], ['mixed-log', 'mono', '연결 끊김 · 마지막 수신 시각'],
];
async function settle(page) {
  await page.evaluate(async () => { await document.fonts.ready; await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); });
  await page.waitForTimeout(350);
}
async function labelFixture(page) {
  await page.evaluate(() => {
    const banner = document.createElement('div'); banner.id = 'typographyFixtureBanner';
    banner.textContent = 'UI DEMO / SYNTHETIC FIXTURE / 실장비·성능 검증 아님';
    banner.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#11161c;color:white;padding:6px 12px;font:12px var(--font-ui,system-ui);pointer-events:none';
    document.body.append(banner);
  });
}
async function platformFonts(page, selector) {
  const session = await page.context().newCDPSession(page);
  await session.send('DOM.enable'); await session.send('CSS.enable');
  const { root } = await session.send('DOM.getDocument');
  const { nodeId } = await session.send('DOM.querySelector', { nodeId: root.nodeId, selector });
  const result = await session.send('CSS.getPlatformFontsForNode', { nodeId });
  await session.detach(); return result.fonts;
}

test('typography actual before/after capture matrix retains critical safety text', async ({ page }) => {
  const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  const fontResponses = []; page.on('response', (response) => { if (/\.woff2(?:\?|$)/.test(response.url())) fontResponses.push({ path: new URL(response.url()).pathname, status: response.status() }); });
  await mkdir(`${root}/captures/${phase}`, { recursive: true }); await mkdir(`${root}/evidence`, { recursive: true });
  const report = [];
  for (const viewport of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 800 }]) {
    await page.setViewportSize(viewport);
    for (const theme of ['dark', 'light']) {
      await page.goto('/#cockpit');
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#themeToggle').click();
      for (const scenario of ['cockpit', 'maps', 'navigation', 'missions', 'sensors', 'settings', 'disconnected', 'stale']) {
        backend.state.online = scenario !== 'disconnected';
        backend.state.uiCloudStreaming = true;
        backend.state.cameraStreaming.go2_front = true;
        const route = ['disconnected', 'stale'].includes(scenario) ? 'cockpit' : scenario;
        await page.goto(`/?typography=${phase}-${scenario}#${route}`);
        await expect(page.locator('#pageTitle')).not.toHaveText('');
        await expect(page.locator('#connectionLabel')).toContainText(scenario === 'disconnected' ? '연결 끊김' : '준비');
        if (scenario === 'maps') await page.locator('.saved-map-item').first().click();
        if (scenario === 'stale') {
          await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBeGreaterThan(0);
          await page.waitForTimeout(500);
          backend.state.uiCloudStreaming = false; backend.state.cameraStreaming.go2_front = false;
          await expect(page.locator('.cockpit-camera-state').first()).toHaveText(phase === 'before' ? 'STALE' : '오래된 데이터', { timeout: 6000 });
          await expect(page.locator('.cockpit-camera-state').first()).toHaveAttribute('data-state', 'stale');
        }
        await settle(page);
        await page.locator('[data-cockpit-software-stop]').click({ trial: true });
        const geometry = await page.evaluate(() => {
          const selectors = ['#cockpitSafetyHud .cockpit-fixed-stop strong', '#cockpitSafetyHud .cockpit-fixed-stop small', '#cockpitSafetyHud .cockpit-safety-summary', '#connectionLabel'];
          return selectors.map((selector) => {
            const node = document.querySelector(selector); const box = node.getBoundingClientRect(); const range = document.createRange(); range.selectNodeContents(node);
            const text = [...range.getClientRects()].map(({ x, y, width, height }) => ({ x, y, width, height }));
            return { selector, text, box: { x: box.x, y: box.y, width: box.width, height: box.height }, style: { family: getComputedStyle(node).fontFamily, weight: getComputedStyle(node).fontWeight }, clipped: node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1 };
          });
        });
        if (phase === 'after') for (const item of geometry) { expect(item.clipped, `${scenario} ${item.selector}`).toBe(false); expect(item.box.x).toBeGreaterThanOrEqual(0); expect(item.box.x + item.box.width).toBeLessThanOrEqual(viewport.width + 1); }
        await labelFixture(page);
        const file = `${phase}/${theme}-${scenario}-${viewport.width}x${viewport.height}.png`;
        await page.screenshot({ path: `${root}/captures/${file}`, animations: 'disabled' });
        report.push({ file, viewport, scenario, theme, geometry });
      }
    }
  }
  await writeFile(`${root}/evidence/${phase}-captures.json`, JSON.stringify({ report, fontResponses, pageErrors, unexpected, mutations: backend.state.requests }, null, 2) + '\n');
  expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
  expect(backend.state.requests.filter(({ path }) => /control\/(arm|acquire|command)|navigation\/(start|goal)|mapping\/(start|save)/.test(path))).toEqual([]);
  if (phase === 'after') { expect(fontResponses.length).toBeGreaterThan(0); expect(fontResponses.every(({ status }) => status === 200)).toBe(true); }
});

test('CDP confirms Korean English and technical glyph fonts in specimen and the app', async ({ page }) => {
  test.skip(phase === 'before');
  await installMissionFixture(page);
  await page.goto('/#settings'); await settle(page);
  await page.evaluate((samples) => {
    const specimen = document.createElement('section'); specimen.id = 'fontSpecimen';
    specimen.style.cssText = 'position:fixed;inset:80px 120px 240px;overflow:auto;z-index:90;padding:24px;background:var(--panel);color:var(--text);border:1px solid var(--line)';
    const heading = document.createElement('h2'); heading.textContent = 'FONT SPECIMEN · 서체 확인용 예시 / 실측값 아님'; specimen.append(heading);
    for (const [id, role, value] of samples) {
      const row = document.createElement('p'); const span = document.createElement('span'); span.id = `specimen-${id}`; span.textContent = value;
      span.style.cssText = `font-family:var(--font-${role},system-ui);font-size:${role === 'display' ? 26 : 14}px;font-weight:${role === 'display' ? 600 : 400};line-height:1.6;letter-spacing:0`; row.append(span); specimen.append(row);
    }
    document.body.append(specimen);
  }, samples);
  await settle(page); await labelFixture(page);
  const results = [];
  for (const [id] of samples) results.push({ id, fonts: await platformFonts(page, `#specimen-${id}`) });
  await writeFile(`${root}/evidence/rendered-fonts.json`, JSON.stringify({ results }, null, 2) + '\n');
  for (const [id, expected] of [['korean','IBM Plex Sans KR'], ['english','IBM Plex Sans'], ['topic','IBM Plex Mono'], ['coordinate','IBM Plex Mono'], ['ambiguous','IBM Plex Mono'], ['mixed-log','IBM Plex Sans KR']]) {
    const fonts = results.find((entry) => entry.id === id).fonts;
    const prefix = { 'IBM Plex Sans KR': 'IBMPlexSansKR', 'IBM Plex Sans': 'IBMPlexSans', 'IBM Plex Mono': 'IBMPlexMono' }[expected];
    expect(fonts.some((font) => new RegExp(`^${prefix}(?:-|$)`).test(font.postScriptName) && font.isCustomFont && font.glyphCount > 0), JSON.stringify({ id, fonts })).toBe(true);
  }
  const app = [];
  for (const selector of ['#pageTitle', '.page-heading p', '#robotType', '#robotIp', '#cockpitSafetyHud .cockpit-fixed-stop strong']) app.push({ selector, fonts: await platformFonts(page, selector) });
  const measurements = await page.evaluate(() => {
    const span = document.createElement('span'); span.style.cssText = 'position:absolute;white-space:nowrap;font:400 14px var(--font-mono);font-variant-numeric:tabular-nums'; document.body.append(span);
    const digits = [...'0123456789'].map((digit) => { span.textContent = digit; return { digit, width: span.getBoundingClientRect().width }; }); span.remove();
    const controls = ['#robotType', '#robotIp'].map((selector) => { const node = document.querySelector(selector); return { selector, height: node.getBoundingClientRect().height }; });
    return { digits, controls };
  });
  expect(Math.max(...measurements.digits.map(({ width }) => width)) - Math.min(...measurements.digits.map(({ width }) => width))).toBeLessThan(.05);
  expect(measurements.controls[0].height).toBe(measurements.controls[1].height);
  expect(measurements.controls[0].height).toBeGreaterThanOrEqual(44);
  const faces = await page.evaluate(() => [...document.fonts].filter((face) => face.status === 'loaded').map(({ family, weight, status }) => ({ family, weight, status })));
  await writeFile(`${root}/evidence/rendered-fonts.json`, JSON.stringify({ results, app, faces, measurements }, null, 2) + '\n');
  await page.screenshot({ path: `${root}/captures/after/specimen-1440x900.png`, animations: 'disabled' });
});

test('late font paint preserves camera subscriptions layout keyboard routing and canvas ownership', async ({ page }) => {
  test.skip(phase === 'before');
  let releaseFonts; const gate = new Promise((resolve) => { releaseFonts = resolve; });
  await page.route('**/*.woff2', async (route) => { await gate; await route.continue(); });
  const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  await page.goto('/#cockpit', { waitUntil: 'domcontentloaded' });
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);
  const connections = structuredClone(backend.state.cameraConnectionsBySource);
  const closes = structuredClone(backend.state.cameraClosesBySource);
  const before = await page.evaluate(() => ({ snapshot: window.RobotScopeCockpit.snapshot(), storage: { ...localStorage } }));
  releaseFonts(); await settle(page);
  await page.evaluate(() => { for (let i = 0; i < 20; i++) document.fonts.dispatchEvent(new Event('loadingdone')); });
  await settle(page);
  const after = await page.evaluate(() => ({ snapshot: window.RobotScopeCockpit.snapshot(), storage: { ...localStorage } }));
  expect(after.snapshot.workspace.scene.rendererCount).toBe(1);
  expect(after.snapshot.pointcloud.activeConsumers).toEqual(['cockpit']);
  expect(after.snapshot.workspace.panels.panels).toEqual(before.snapshot.workspace.panels.panels);
  expect(after.storage).toEqual(before.storage);
  expect(backend.state.cameraConnectionsBySource).toEqual(connections); expect(backend.state.cameraClosesBySource).toEqual(closes);
  // Open editing after the font/storage invariants above; this is a separate UI action.
  await page.locator('[data-cockpit-layout-action="edit"]').click();
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'layout-edit');
  await page.locator('.cockpit-layout-library-toggle').click();
  await expect(page.locator('.cockpit-layout-library-body')).toBeVisible();
  const library = await page.locator('.cockpit-layout-library-body').boundingBox();
  expect(library.x).toBeGreaterThanOrEqual(0); expect(library.x + library.width).toBeLessThanOrEqual(1440);
  await page.locator('.cockpit-layout-library-toggle').focus(); await page.keyboard.press('Space');
  await expect(page.locator('.cockpit-layout-library-body')).toBeHidden();
  await page.locator('[data-cockpit-software-stop]').click({ trial: true });
  expect(backend.state.requests.filter(({ path }) => /control\/(arm|acquire|command)|navigation\/(start|goal)|mapping\/(start|save)/.test(path))).toEqual([]);
  expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
  await writeFile(`${root}/evidence/font-lifecycle.json`, JSON.stringify({ connections, closes, rendererCount: after.snapshot.workspace.scene.rendererCount, storagePreserved: true, panelStatePreserved: true, pageErrors, unexpected }, null, 2) + '\n');
});
