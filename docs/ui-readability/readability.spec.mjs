import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { installMissionFixture } from '../../tests/e2e/ui_redesign_fixture.mjs';
const phase = process.env.UI_READABILITY_PHASE || 'after';
const root = 'docs/ui-readability';
const matrix = [
  ['cockpit', 'normal', 'dark', 1440, 900], ['cockpit', 'normal', 'light', 1440, 900],
  ['cockpit', 'stale', 'dark', 1280, 800], ['cockpit', 'disconnected', 'light', 1024, 768],
  ['cockpit', 'no-data', 'dark', 1024, 768], ['cockpit', 'normal', 'light', 768, 1024],
  ['cockpit', 'normal', 'dark', 720, 450],
  ['mapping', 'normal', 'dark', 1440, 900], ['maps', 'normal', 'light', 1440, 900],
  ['navigation', 'long-error', 'dark', 1280, 800], ['sensors', 'normal', 'light', 1024, 768],
  ['settings', 'normal', 'dark', 1280, 800],
];
async function platformFonts(page, selector) {
  const session = await page.context().newCDPSession(page);
  await session.send('DOM.enable'); await session.send('CSS.enable');
  const { root } = await session.send('DOM.getDocument');
  const { nodeId } = await session.send('DOM.querySelector', { nodeId: root.nodeId, selector });
  const result = nodeId ? await session.send('CSS.getPlatformFontsForNode', { nodeId }) : { fonts: [] };
  await session.detach(); return result.fonts;
}
test('representative before and after matrix records rendering, safety accessibility and isolated requests', async ({ browser }) => {
  await mkdir(`${root}/captures/${phase}`, { recursive: true }); await mkdir(`${root}/evidence`, { recursive: true });
  const report = [];
  for (const [route, state, theme, width, height] of matrix) {
    const context = await browser.newContext({ viewport: { width, height }, baseURL: `http://127.0.0.1:${process.env.UI_READABILITY_PORT || 4198}` });
    const page = await context.newPage();
    const fixture = await installMissionFixture(page, { online: state !== 'disconnected' });
    const { backend } = fixture;
    if (state === 'no-data') { backend.state.uiCloudStreaming = false; backend.state.cameraStreaming.go2_front = false; }
    if (state === 'long-error') {
      backend.state.navigation.pipeline.error = '로봇 상태 정보가 오래되어 현재 작업을 시작할 수 없습니다. 연결 상태와 마지막 상태 수신 시각을 확인한 뒤 다시 시도하세요. 원본 장치에서 제공한 진단 정보가 길어도 화면 안에서 모두 읽을 수 있어야 합니다.';
      backend.state.navigation.pipeline.state = 'error';
      backend.state.navigation.safety.blockers = ['lowstate_stale'];
    }
    await page.goto(`/?readability=${phase}-${state}#${route}`);
    await expect(page.locator('#pageTitle')).not.toHaveText('');
    if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#themeToggle').click();
    if (route === 'maps') await page.locator('.saved-map-item').first().click();
    if (state === 'long-error') await expect(page.locator('#navigationPipelineNote')).toHaveText(backend.state.navigation.pipeline.error);
    if (state === 'stale') {
      await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBeGreaterThan(0);
      await page.waitForTimeout(600); backend.state.uiCloudStreaming = false; backend.state.cameraStreaming.go2_front = false;
      await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'stale', { timeout: 8000 });
    }
    await page.evaluate(async () => { await document.fonts.ready; await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); });
    await page.waitForTimeout(400);
    // At the 200% reflow equivalent, normal page scrolling may move navigation
    // above the viewport. Verify that the observation workspace remains usable.
    if (width === 720) await page.locator('#cockpitWorkspace').scrollIntoViewIfNeeded();
    let stopTrial = null;
    try { await page.locator('[data-cockpit-software-stop]').click({ trial: true, timeout: 1500 }); } catch (error) { stopTrial = error.message; }
    const geometry = await page.evaluate(() => {
      const selectors = ['#connectionLabel', '#controlConnectionLabel', '#pageTitle', '.cockpit-safety-summary', '.cockpit-fixed-stop strong', '.cockpit-fixed-stop small', '#navigationSafetyMessage', '#navigationPipelineNote', '#missionInspector', '.cockpit-scene-controls', '.cockpit-layout-library', '.cockpit-sensor-launcher', '#cockpitWorkspace', '#cockpitSceneCanvas', '[data-cockpit-software-stop]'];
      const elements = selectors.map((selector) => {
        const node = document.querySelector(selector); if (!node) return { selector, absent: true };
        const box = node.getBoundingClientRect(); const style = getComputedStyle(node);
        return { selector, text: node.textContent.slice(0, 400), box: box.toJSON(), visible: !!(box.width && box.height), clipped: node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1, font: { family: style.fontFamily, size: style.fontSize, weight: style.fontWeight, lineHeight: style.lineHeight }, color: style.color, background: style.backgroundColor };
      });
      const luminance = (hex) => hex.match(/[a-f\d]{2}/gi).map(v => parseInt(v, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      const style = getComputedStyle(document.documentElement); const token = name => style.getPropertyValue(name).trim();
      const contrast = (a, b) => { const pair = [luminance(a), luminance(b)].sort((a,b) => b-a); return (pair[0] + .05) / (pair[1] + .05); };
      const contrasts = Object.fromEntries(['--text','--muted','--cyan'].map(name => [name, contrast(token(name), token('--panel'))]));
      const canvas = document.querySelector('#cockpitSceneCanvas');
      const canvasBox = canvas.getBoundingClientRect(); const hud = document.querySelector('#cockpitSafetyHud').getBoundingClientRect();
      const unobstructedSceneHeight = Math.max(0, Math.min(canvasBox.bottom, innerHeight, hud.top) - Math.max(0, canvasBox.top));
      const cameraMetrics = [...document.querySelectorAll('.cockpit-camera-metrics > div > strong')].flatMap(node => {
        const box = node.getBoundingClientRect(); if (!box.width || !box.height) return [];
        const content = node.closest('.cockpit-panel-content').getBoundingClientRect();
        return [{ text: node.textContent, box: box.toJSON(), content: content.toJSON(), insidePanel: box.top >= content.top - 1 && box.bottom <= content.bottom + 1 }];
      });
      return { overflow: document.documentElement.scrollWidth > innerWidth, elements, contrasts, unobstructedSceneHeight, cameraMetrics, canvas: { cssWidth: canvas.clientWidth, cssHeight: canvas.clientHeight, width: canvas.width, height: canvas.height, dpr: devicePixelRatio } };
    });
    const fonts = route === 'cockpit' && width === 1440 ? await platformFonts(page, '#pageTitle') : undefined;
    const file = `${phase}/${route}-${state}-${theme}-${width}x${height}.png`;
    await page.screenshot({ path: `${root}/captures/${file}`, animations: 'disabled' });
    report.push({ file, route, state, theme, viewport: { width, height }, zoomEquivalent: width === 720 ? '200% reflow equivalent of 1440x900 with workspace scrolled into view; not actual browser or OS zoom' : undefined, stopTrial, geometry, fonts, requests: backend.state.requests, pageErrors: fixture.pageErrors, consoleErrors: fixture.consoleErrors, httpErrors: fixture.httpErrors, unexpected: fixture.unexpected });
    await writeFile(`${root}/evidence/${phase}-browser.json`, JSON.stringify(report, null, 2) + '\n');
    await context.close();
  }
  for (const row of report) {
    expect(row.unexpected, row.file).toEqual([]); expect(row.pageErrors, row.file).toEqual([]);
    const expectedFixtureErrors = row.httpErrors.filter(({ url, status }) => (url === '/static/data/go2_saved_map.json' && status === 404) || (row.state === 'disconnected' && url === '/api/v1/state' && status === 503));
    expect(row.httpErrors, row.file).toEqual(expectedFixtureErrors);
    expect(row.consoleErrors.filter(message => !/^Failed to load resource: the server responded with a status of (404|503) /.test(message)), row.file).toEqual([]);
    expect(row.requests.filter(({ path }) => /control\/(arm|acquire|command|stop)|navigation\/(start|goal)|mapping\/(start|save)/.test(path)), row.file).toEqual([]);
    if (phase === 'after') {
      expect(row.stopTrial, row.file).toBeNull(); expect(row.geometry.overflow, row.file).toBe(false);
      const stop = row.geometry.elements.find(e => e.selector === '[data-cockpit-software-stop]');
      expect(stop.box.y, row.file).toBeGreaterThanOrEqual(0); expect(stop.box.bottom, row.file).toBeLessThanOrEqual(row.viewport.height + 1);
      expect(stop.box.height, row.file).toBeGreaterThanOrEqual(44);
      for (const element of row.geometry.elements.filter(e => e.visible && ['#connectionLabel', '#controlConnectionLabel', '.cockpit-safety-summary', '.cockpit-fixed-stop strong', '.cockpit-fixed-stop small', '#navigationSafetyMessage', '#navigationPipelineNote'].includes(e.selector))) expect(element.clipped, `${row.file}: ${element.selector}`).toBe(false);
      for (const contrast of Object.values(row.geometry.contrasts)) expect(contrast, row.file).toBeGreaterThanOrEqual(4.5);
      if (row.route === 'cockpit' && row.viewport.width === 720) expect(row.geometry.unobstructedSceneHeight, `${row.file}: scene above fixed safety HUD`).toBeGreaterThanOrEqual(80);
      for (const metric of row.geometry.cameraMetrics) expect(metric.insidePanel, `${row.file}: primary camera metric ${metric.text}`).toBe(true);
    }
  }
});

test('actual rendered fonts and effective background contrast for visible critical text', async ({ page }) => {
  test.skip(phase === 'before');
  await installMissionFixture(page); await page.goto('/#cockpit');
  await page.evaluate(async () => { await document.fonts.ready; });
  const report = [];
  for (const theme of ['dark', 'light']) {
    if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#themeToggle').click();
    await page.waitForTimeout(400); // Measure settled theme colors, after existing CSS transitions.
    const text = await page.evaluate(() => {
      const rgba = value => { const a = value.match(/[\d.]+/g)?.map(Number) || [0,0,0,0]; return [...a.slice(0,3), a.length > 3 ? a[3] : 1]; };
      const blend = (fg, bg) => [...fg.slice(0,3).map((c,i) => c*fg[3] + bg[i]*(1-fg[3])), 1];
      const luminance = color => color.slice(0,3).map(c => c/255).map(c => c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4).reduce((sum,c,i) => sum+c*[.2126,.7152,.0722][i],0);
      const selectors = ['#pageTitle','#connectionLabel','#controlConnectionLabel','.nav-item.is-active b','.cockpit-safety-summary','.cockpit-safety-identity strong','.cockpit-fixed-stop strong','.cockpit-fixed-stop small','.cockpit-camera-state','.cockpit-scene-controls button'];
      return selectors.flatMap(selector => [...document.querySelectorAll(selector)].map(node => {
        const box = node.getBoundingClientRect(); if (!box.width || !box.height || node.disabled) return null;
        const chain=[]; for(let parent=node; parent; parent=parent.parentElement) chain.unshift(parent);
        let background=[255,255,255,1]; const gradients=[];
        for(const parent of chain) { const style=getComputedStyle(parent); background=blend(rgba(style.backgroundColor),background); if(style.backgroundImage !== 'none') gradients.push(style.backgroundImage); }
        const style=getComputedStyle(node); const foreground=blend(rgba(style.color),background);
        const l=[luminance(foreground),luminance(background)].sort((a,b)=>b-a);
        return { selector, text:node.textContent.trim(), fontSize:style.fontSize,lineHeight:style.lineHeight, foreground,background,contrast:(l[0]+.05)/(l[1]+.05),gradients,box:box.toJSON() };
      }).filter(Boolean));
    });
    const fonts=[];
    for(const selector of ['#pageTitle','#connectionLabel','.cockpit-fixed-stop strong','.cockpit-camera-state']) fonts.push({selector,fonts:await platformFonts(page,selector)});
    report.push({theme,text,fonts});
  }
  await writeFile(`${root}/evidence/actual-fonts-contrast.json`,JSON.stringify(report,null,2)+'\n');
  for(const row of report) {
    for(const sample of row.text.filter(sample => sample.gradients.length === 0)) expect(sample.contrast, `${row.theme} ${sample.selector} ${sample.text}`).toBeGreaterThanOrEqual(4.5);
    expect(row.fonts.find(sample => sample.selector === '#pageTitle').fonts.some(font => font.isCustomFont && font.glyphCount > 0 && /^IBMPlexSansKR/.test(font.postScriptName))).toBe(true);
  }
});

test('observation disclosure and menu resize preserve renderer, subscriptions and edit tools', async ({ page }) => {
  test.skip(phase === 'before');
  const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  await page.goto('/#cockpit');
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'fixture');
  const baseline = structuredClone({ connections: backend.state.cameraConnectionsBySource, closes: backend.state.cameraClosesBySource, ws: backend.state.wsConnections });
  baseline.layoutStorage = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('robot-scope.cockpit.'))));
  await expect(page.locator('#missionInspector')).toBeHidden();
  await expect(page.locator('#cockpitLayoutLibrary')).toBeHidden();
  await expect(page.locator('#cockpitSensorLauncher')).toBeHidden();
  await page.locator('#cockpitPanelsToggle').click();
  await expect(page.locator('#cockpitPanelsToggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]')).toBeVisible();
  await expect(page.locator('.cockpit-launcher-item[data-panel-type="camera.realsense-color"]')).toBeHidden();
  await expect(page.locator('.cockpit-layout-controls')).toBeHidden();
  await page.locator('.cockpit-launcher-item[data-panel-type="camera.go2-front"]').click();
  await page.locator('#cockpitPanelsToggle').click();
  await expect(page.locator('#cockpitSensorLauncher')).toBeHidden();
  const cameraDetails = page.locator('.cockpit-camera-details').first();
  await cameraDetails.locator('summary').click();
  await expect(cameraDetails).toHaveAttribute('open', '');
  await expect(cameraDetails.locator('.cockpit-camera-extra-metrics')).toBeVisible();
  await cameraDetails.locator('summary').click();
  await expect(cameraDetails).not.toHaveAttribute('open', '');
  await expect(cameraDetails.locator('.cockpit-camera-extra-metrics')).toBeHidden();
  await page.locator('#cockpitInspectorToggle').focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#missionInspector')).toBeVisible();
  await expect(page.locator('#cockpitInspectorToggle')).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Space'); await expect(page.locator('#missionInspector')).toBeHidden();
  await page.locator('#navigationToggle').click();
  await expect(page.locator('#navigationToggle')).toHaveAttribute('aria-expanded', 'false');
  await page.locator('#navigationToggle').click();
  await expect(page.locator('#navigationToggle')).toHaveAttribute('aria-expanded', 'true');
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => ({ snapshot: window.RobotScopeCockpit.snapshot(), layoutStorage: Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('robot-scope.cockpit.'))), canvas: (()=>{ const c=document.querySelector('#cockpitSceneCanvas');return {width:c.width,height:c.height,cssWidth:c.clientWidth,cssHeight:c.clientHeight,dpr:devicePixelRatio}; })() }));
  expect(after.snapshot.workspace.scene.rendererCount).toBe(1);
  expect(after.snapshot.pointcloud.activeConsumers).toEqual(['cockpit']);
  expect(backend.state.cameraConnectionsBySource).toEqual(baseline.connections);
  expect(backend.state.cameraClosesBySource).toEqual(baseline.closes);
  expect(backend.state.wsConnections).toEqual(baseline.ws);
  expect(after.layoutStorage).toEqual(baseline.layoutStorage);
  expect(Math.abs(after.canvas.width - after.canvas.cssWidth * after.canvas.dpr)).toBeLessThanOrEqual(2);
  expect(Math.abs(after.canvas.height - after.canvas.cssHeight * after.canvas.dpr)).toBeLessThanOrEqual(2);
  await page.locator('[data-cockpit-layout-action="edit"]').click();
  await expect(page.locator('#missionPresetSelect')).toBeEnabled();
  await expect(page.locator('#cockpitLayoutLibrary')).toBeVisible();
  await expect(page.locator('#cockpitSensorLauncher')).toBeVisible();
  await page.locator('.cockpit-layout-library-toggle').click();
  await expect(page.locator('.cockpit-layout-library-body')).toBeVisible();
  const libraryBounds = await page.locator('.cockpit-layout-library-body').boundingBox();
  const nameBounds = await page.locator('.cockpit-layout-library input[type="text"]').boundingBox();
  expect(libraryBounds.width).toBeGreaterThanOrEqual(300);
  expect(nameBounds.width).toBeGreaterThanOrEqual(140);
  await page.screenshot({ path: `${root}/captures/after/cockpit-layout-edit-dark-1440x900.png`, animations: 'disabled' });
  await page.locator('[data-layout-library-action="reset"]').click({ trial: true });
  await page.locator('.cockpit-layout-library-toggle').click();
  await page.locator('[data-cockpit-layout-action="apply"]').click();
  await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-layout-mode', 'operate');
  await expect(page.locator('#cockpitLayoutLibrary')).toBeHidden();
  await page.locator('[data-cockpit-software-stop]').click({ trial: true });
  await page.goto('/#overview');
  await expect.poll(() => page.evaluate(() => window.RobotScopeCameraStreams.snapshot().demand.totalConsumers)).toBe(0);
  expect(backend.state.requests.filter(({ path }) => /control\/(arm|acquire|command|stop)|navigation\/(start|goal)|mapping\/(start|save)/.test(path))).toEqual([]);
  expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
  await writeFile(`${root}/evidence/disclosure-lifecycle.json`,JSON.stringify({baseline,after,requests:backend.state.requests,pageErrors,unexpected},null,2)+'\n');
});

test('tablet DPR2 canvas uses CSS pointer coordinates for orbit and zoom', async ({ browser }) => {
  test.skip(phase === 'before');
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 }, deviceScaleFactor: 2, baseURL: `http://127.0.0.1:${process.env.UI_READABILITY_PORT || 4198}` });
  const page = await context.newPage(); const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  await page.goto('/#cockpit'); await expect(page.locator('#cockpitWorkspace')).toHaveAttribute('data-freshness', 'fixture');
  await page.waitForTimeout(300);
  const canvas = await page.locator('#cockpitSceneCanvas').evaluate(node => ({ width: node.width, height: node.height, cssWidth: node.clientWidth, cssHeight: node.clientHeight, dpr: devicePixelRatio, box: node.getBoundingClientRect().toJSON() }));
  expect(canvas.dpr).toBe(2);
  expect(Math.abs(canvas.width - canvas.cssWidth * 2)).toBeLessThanOrEqual(2);
  expect(Math.abs(canvas.height - canvas.cssHeight * 2)).toBeLessThanOrEqual(2);
  const point = { x: canvas.box.x + canvas.box.width * .15, y: canvas.box.y + canvas.box.height * .7 };
  expect(await page.evaluate(({x,y}) => document.elementFromPoint(x,y)?.id,point)).toBe('cockpitSceneCanvas');
  const cameraBefore = await page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera);
  await page.mouse.move(point.x,point.y); await page.mouse.wheel(0,120);
  await expect.poll(() => page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera.distance)).not.toBe(cameraBefore.distance);
  await page.mouse.down(); await page.mouse.move(point.x + 35,point.y - 20,{steps:4}); await page.mouse.up();
  await expect.poll(() => page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera.yaw)).not.toBe(cameraBefore.yaw);
  await page.locator('[data-cockpit-software-stop]').click({trial:true});
  const cameraAfter = await page.evaluate(() => window.RobotScopeCockpit.snapshot().workspace.scene.camera);
  expect(backend.state.requests.filter(({path}) => /control\/(arm|acquire|command|stop)|navigation\/(start|goal)|mapping\/(start|save)/.test(path))).toEqual([]);
  expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
  await writeFile(`${root}/evidence/tablet-dpr-pointer.json`,JSON.stringify({canvas,point,cameraBefore,cameraAfter,requests:backend.state.requests,pageErrors,unexpected},null,2)+'\n');
  await context.close();
});
