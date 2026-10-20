import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.argv[2] || 'http://127.0.0.1:8000/web/';
const output = path.resolve(process.argv[3] || './web-tests');
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
const externalRequests = [];
const glbResponses = [];
page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', (error) => pageErrors.push(error.message));
page.on('requestfailed', (request) => failedRequests.push({ url: request.url(), error: request.failure() }));
page.on('request', (request) => { if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== new URL(baseURL).origin) externalRequests.push(request.url()); });
page.on('response', (response) => { if (new URL(response.url()).pathname.endsWith('/arena.glb')) glbResponses.push({ url: response.url(), status: response.status() }); });
try {
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__arenaPreview?.loaded && window.__arenaPreview?.metadataLoaded, { timeout: 30000 });
  await page.waitForTimeout(300);
  const diagnostics = await page.evaluate(() => ({ loaded: window.__arenaPreview.loaded, metadataLoaded: window.__arenaPreview.metadataLoaded, meshCount: window.__arenaPreview.meshCount, bounds: window.__arenaPreview.bounds, layers: window.__arenaPreview.layers, renderInfo: window.__arenaPreview.renderInfo }));
  assert(diagnostics.meshCount > 0, 'Actual GLB meshes must load');
  assert(diagnostics.renderInfo.triangles > 0, 'Actual triangles must render');
  assert.equal(glbResponses.length, 1, 'GLB must be requested exactly once');
  assert.equal(glbResponses[0].status, 200, 'GLB response must succeed');
  const bytes = await (await page.request.get(new URL('../arena.glb', baseURL).href)).body();
  assert.equal(bytes.subarray(0, 4).toString('ascii'), 'glTF', 'Model must be a GLB container');
  const json = await (await page.request.get(new URL('../arena.json', baseURL).href)).json();
  assert.deepEqual(JSON.parse(await page.locator('#raw-json').textContent()), json, 'All original metadata must be exposed');
  await page.screenshot({ path: path.join(output, 'web-perspective.png') });
  await page.locator('#top').click();
  assert.equal(await page.evaluate(() => window.__arenaPreview.mode), 'top');
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(output, 'web-top.png') });
  for (const layer of ['walls', 'obstacles', 'labels', 'floor']) {
    assert(diagnostics.layers[layer].meshes > 0, `${layer} must contain actual meshes`);
    await page.locator(`[data-layer="${layer}"]`).uncheck();
    assert.equal(await page.evaluate((key) => window.__arenaPreview.layers[key].visible, layer), 0, `${layer} must hide`);
    await page.locator(`[data-layer="${layer}"]`).check();
    assert.equal(await page.evaluate((key) => window.__arenaPreview.layers[key].visible, layer), diagnostics.layers[layer].meshes, `${layer} must restore`);
  }
  await page.locator('[data-layer="grid"]').uncheck();
  await page.locator('[data-layer="walls"]').uncheck();
  await page.locator('#reset').click();
  assert.equal(await page.evaluate(() => window.__arenaPreview.mode), 'perspective');
  assert(await page.evaluate(() => Object.values(window.__arenaPreview.layers).every((layer) => layer.enabled)), 'Reset must restore layers');
  for (let i = 0; i < 3; i++) {
    await page.locator('#show-details').click();
    assert(await page.locator('#details-dialog').isVisible());
    if (i === 1) await page.keyboard.press('Escape'); else await page.locator('#close-details').click();
    assert(!(await page.locator('#details-dialog').isVisible()));
  }
  await page.locator('#show-details').click();
  await page.screenshot({ path: path.join(output, 'web-dimensions.png') });
  await page.locator('#close-details').click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#reset').click();
  await page.waitForTimeout(200);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile viewport must not overflow horizontally');
  await page.screenshot({ path: path.join(output, 'web-mobile.png'), fullPage: true });
  await page.locator('#top').click();
  assert.equal(await page.evaluate(() => window.__arenaPreview.mode), 'top');
  assert.equal(consoleErrors.length, 0, `Browser console errors: ${consoleErrors.join('; ')}`);
  assert.equal(pageErrors.length, 0, `Page errors: ${pageErrors.join('; ')}`);
  assert.equal(failedRequests.length, 0, `Failed requests: ${JSON.stringify(failedRequests)}`);
  assert.equal(externalRequests.length, 0, 'Preview must not request external assets');
  const report = { passed: true, browser: await browser.version(), testedAt: new Date().toISOString(), baseURL, glbBytes: bytes.length, diagnostics, checks: ['Actual GLB HTTP 200 and glTF header', 'Nonzero rendered triangles', 'Complete source JSON displayed', 'Perspective and orthographic views', 'All model layer toggles', 'Grid and layer reset', 'Repeated detail open/close and Escape', 'Desktop and mobile screenshot', 'Mobile no horizontal overflow', 'Zero console, page, or request errors', 'Zero external network requests'], consoleErrors, pageErrors, failedRequests, externalRequests };
  await fs.writeFile(path.join(output, 'web-test-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  await page.screenshot({ path: path.join(output, 'web-test-failure.png'), fullPage: true }).catch(() => {});
  await fs.writeFile(path.join(output, 'web-test-report.json'), JSON.stringify({ passed: false, error: error.message, consoleErrors, pageErrors, failedRequests, externalRequests }, null, 2));
  throw error;
} finally {
  await browser.close();
}
