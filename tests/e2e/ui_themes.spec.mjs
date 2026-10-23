import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { installMissionFixture } from './ui_redesign_fixture.mjs';
import { recordedFixture } from '../recorded_se3_fixture.mjs';

const root = process.env.UI_EVIDENCE_ROOT || '/private/tmp/robot-scope-ui-themes';
test.beforeAll(async () => mkdir(`${root}/captures`, { recursive: true }));
const key = 'robot-scope.ui.theme.v1';
const forbidden = (backend) => backend.state.requests.filter(({ path }) => /control\/(arm|acquire|command)|navigation\/(start|goal)|mapping\/(start|save)/.test(path));
const addFixtureBanner = (page) => page.evaluate(() => {
  const banner = document.createElement('div'); banner.textContent = 'UI DEMO / SYNTHETIC FIXTURE / 실장비·성능 검증 아님';
  banner.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#11161c;color:white;padding:6px 12px;font:12px system-ui;pointer-events:none';
  document.body.append(banner);
});
async function renderedContrast(page, selectors) {
  return page.evaluate((selectors) => {
    const rgba = (color) => color.match(/[\d.]+/g).map(Number);
    const blend = (front, back) => front.slice(0, 3).map((value, index) => value * (front[3] ?? 1) + back[index] * (1 - (front[3] ?? 1)));
    const luminance = (rgb) => rgb.map((value) => value / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    return selectors.map((selector) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing contrast target: ${selector}`);
      if (!element.checkVisibility()) throw new Error(`Hidden contrast target: ${selector}`);
      const ancestors = []; for (let node = element; node; node = node.parentElement) ancestors.unshift(node);
      let background = [255, 255, 255];
      for (const ancestor of ancestors) background = blend(rgba(getComputedStyle(ancestor).backgroundColor), background);
      const foreground = blend(rgba(getComputedStyle(element).color), background);
      const [high, low] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
      return { selector, foreground, background, ratio: (high + .05) / (low + .05) };
    });
  }, selectors);
}

test('theme switching persists across reload and windows without recreating sensors or controlling the robot', async ({ page, context }) => {
  const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  await page.goto('/#cockpit');
  await expect(page.locator('[data-panel-id="camera-go2-front"]')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect.poll(() => backend.state.cameraConnectionsBySource.go2_front).toBe(1);
  const cameraBefore = structuredClone(backend.state.cameraConnectionsBySource);
  const closesBefore = structuredClone(backend.state.cameraClosesBySource);
  const layoutsBefore = await page.evaluate((key) => Object.fromEntries(Object.entries(localStorage).filter(([name]) => name !== key)), key);
  const before = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  for (let index = 0; index < 20; index += 1) await page.locator('#themeToggle').click();
  const after = await page.evaluate(() => window.RobotScopeCockpit.snapshot());
  expect(after.workspace.panels.panels).toEqual(before.workspace.panels.panels);
  expect(after.workspace.scene.rendererCount).toBe(1);
  expect(after.pointcloud.activeConsumers).toEqual(['cockpit']);
  expect(backend.state.cameraConnectionsBySource).toEqual(cameraBefore);
  expect(backend.state.cameraClosesBySource).toEqual(closesBefore);
  expect(await page.evaluate((key) => Object.fromEntries(Object.entries(localStorage).filter(([name]) => name !== key)), key)).toEqual(layoutsBefore);
  await page.locator('#themeToggle').focus();
  await page.keyboard.press('Space');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBe('light');
  await page.reload();
  await expect(page.locator('#themeToggle')).toHaveAttribute('aria-pressed', 'true');
  const second = await context.newPage();
  await installMissionFixture(second);
  await second.goto('/?workspace=cockpit#cockpit');
  await expect(second.locator('html')).toHaveAttribute('data-theme', 'light');
  // Dedicated windows hide the topbar, but still receive the shared preference.
  await page.locator('#themeToggle').click();
  await expect(second.locator('html')).toHaveAttribute('data-theme', 'dark');
  await second.close();
  expect(forbidden(backend)).toEqual([]);
  expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
});

test('both themes keep readable text and STOP usable across routes and mobile with real fixture captures', async ({ page }) => {
  test.setTimeout(90_000);
  const { backend, pageErrors, unexpected } = await installMissionFixture(page);
  await mkdir(`${root}/captures`, { recursive: true });
  let seq = 0;
  backend.on('/api/v1/system/resources', ({ method, json }) => {
    expect(method).toBe('GET');
    return json({ schema: 'robot-scope.resources.v1', seq: ++seq, timestamp_ms: Date.now(), sample_interval_s: 1,
      host: { model: 'Jetson fixture', hostname: 'fixture' }, cpu: { percent: 25, cores: [] },
      gpu: { percent: 15 }, memory: { percent: 40 }, sensors: {} });
  });
  const measurements = [];
  const failures = [];
  for (const theme of ['dark', 'light']) {
    await page.goto('/#cockpit');
    if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#themeToggle').click();
    const contrast = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      const luminance = (hex) => hex.match(/[a-f\d]{2}/gi).map((value) => parseInt(value, 16) / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
      const ratio = (a, b) => { const values = [luminance(style.getPropertyValue(a)), luminance(style.getPropertyValue(b))].sort((a, b) => b - a); return (values[0] + .05) / (values[1] + .05); };
      return { text: ratio('--text', '--panel'), secondary: ratio('--muted', '--panel'), action: ratio('--cyan', '--panel') };
    });
    for (const ratio of Object.values(contrast)) expect(ratio).toBeGreaterThanOrEqual(4.5);
    const rendered = [];
    measurements.push({ theme, contrast, rendered });
    for (const route of ['cockpit', 'maps', 'navigation', 'sensors', 'settings', 'controls', 'missions', 'route-planner', 'topics', 'mapping', 'resources']) {
      await page.goto(`/?theme-capture=${theme}#${route}`);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      if (route === 'settings') await page.locator('[data-cockpit-software-stop]').click({ trial: true });
      else await expect(page.locator('[data-cockpit-software-stop]')).toBeHidden();
      await expect(page.locator('#connectionLabel')).toContainText('준비');
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(450);
      const targets = ['#pageTitle'];
      if (route === 'settings') targets.push('#cockpitSafetyHud .cockpit-fixed-stop strong', '#cockpitSafetyHud .cockpit-fixed-stop small');
      if (route === 'cockpit') targets.push('.cockpit-camera-statusline > strong', '.cockpit-camera-state');
      if (route === 'sensors') targets.push('.camera-view-toolbar label', '.camera-feed-identity strong', '#cameraPrimaryState', '.dataset-capture-summary span', '.dataset-capture-summary strong', '.dataset-output-path code');
      if (route === 'settings') targets.push('.robot-discovery-empty', '.connection-target-state strong', '#cloudSourceTopicLabel', '.settings-detail strong');
      if (route === 'navigation') targets.push('.navigation-status-card strong', '.navigation-readiness span', '.navigation-readiness strong', '.navigation-primary');
      if (theme === 'light' && route === 'controls') targets.push('#softwareEstopButton strong', '#softwareEstopButton small');
      if (route === 'route-planner') targets.push('.route-planner-header strong', '.route-planner-order h3', '.schematic-controls summary');
      if (route === 'resources') targets.push('#resourceMonitor .intro-copy', '#resourceMonitor .host-box small', '#resourceMonitor .panel-heading h2', '#pauseButton', '#loadNote');
      const colors = await renderedContrast(page, targets);
      for (const color of colors) if (color.ratio < 4.5) failures.push({ theme, route, ...color });
      rendered.push({ route, colors });
      await addFixtureBanner(page);
      await page.screenshot({ path: `${root}/captures/${theme}-${route}-1440x900.png`, animations: 'disabled' });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/#cockpit');
    await page.locator('#themeToggle').click({ trial: true });
    await expect(page.locator('[data-cockpit-software-stop]')).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await addFixtureBanner(page);
    await page.screenshot({ path: `${root}/captures/${theme}-cockpit-390x844.png`, animations: 'disabled' });
    await page.goto('/#settings');
    await page.locator('[data-cockpit-software-stop]').click({ trial: true });
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await writeFile(`${root}/contrast.json`, JSON.stringify(measurements, null, 2) + '\n');
  expect(failures, 'Rendered text contrast must reach 4.5:1').toEqual([]);
  expect(forbidden(backend)).toEqual([]); expect(pageErrors).toEqual([]); expect(unexpected).toEqual([]);
});

test('invalid or unavailable storage falls back safely and offline experiments share the theme', async ({ page }) => {
  await installMissionFixture(page);
  await page.goto('/#cockpit');
  await page.evaluate((key) => localStorage.setItem(key, 'invalid'), key);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('#themeToggle').click();
  await page.goto('/static/experiments.html');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.locator('#recordedFile').setInputFiles({ name: 'synthetic.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(recordedFixture())) });
  await expect(page.locator('#recordedContent')).toBeVisible();
  const colors = await renderedContrast(page, ['.experiment-intro p', '.experiment-source small', '#recordedPoseCaveat']);
  for (const color of colors) expect(color.ratio, color.selector).toBeGreaterThanOrEqual(4.5);
  await addFixtureBanner(page);
  await page.screenshot({ path: `${root}/captures/light-experiments-1440x900.png`, animations: 'disabled' });
  await page.locator('#themeToggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.screenshot({ path: `${root}/captures/dark-experiments-1440x900.png`, animations: 'disabled' });
  await page.goto('/#cockpit');
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error('storage unavailable'); }; });
  await page.locator('#themeToggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('#themeToggle')).toHaveAttribute('title', /이 창에만 적용/);
  await expect(page.locator('[data-cockpit-software-stop]')).toBeHidden();
  await page.goto('/#settings');
  await page.locator('[data-cockpit-software-stop]').click({ trial: true });
});
