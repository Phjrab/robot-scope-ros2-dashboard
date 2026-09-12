import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const load = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const html = load('../robot_dashboard/static/index.html');
const css = load('../robot_dashboard/static/dashboard-polish.css');
const rules = css.replace(/\/\*[\s\S]*?\*\//g, '');

test('presentation refinements load once after the existing dashboard styles', () => {
  const links = [...html.matchAll(/<link\s+rel="stylesheet"\s+href="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(links.filter((href) => href === '/static/dashboard-polish.css').length, 1);
  assert.ok(links.indexOf('/static/dashboard-polish.css') > links.indexOf('/static/features/cockpit/cockpit.css'));
  assert.doesNotMatch(rules, /@import|url\s*\(/i, 'polish adds no external resources');
});

test('common typography uses scalable readable tiers', () => {
  for (const [name, value] of [['micro', '.75rem'], ['control', '.875rem'], ['secondary', '.875rem'], ['body', '1rem'], ['section', '1.125rem']]) {
    assert.ok(rules.includes(`--type-${name}: ${value};`));
  }
  assert.match(rules, /:focus-visible\s*\{[^}]*outline:\s*3px/);
});

test('UI polish does not override canvas hit routing or operational safety overlays', () => {
  assert.doesNotMatch(rules, /pointer-events\s*:|touch-action\s*:|z-index\s*:|!important/);
  assert.doesNotMatch(rules, /\bcanvas\b|\.cockpit-safety[-\w]*|\.cockpit-fixed-stop|\.software-estop|\.control-arm-button/);
  assert.doesNotMatch(rules, /\[hidden\]|\[data-layout-mode|\[data-state|\[aria-pressed/);
  assert.match(rules, /\.page-view:not\(\.cockpit-page\)/, 'form sizing excludes cockpit overlays');
});

test('narrow layouts retain status labels and table filters', () => {
  assert.match(rules, /@media\s*\(max-width: 800px\)/);
  assert.match(rules, /\.table-actions\s*\{[^}]*display:\s*flex/);
  assert.match(rules, /\.connection-chip #connectionLabel,[\s\S]*?\.connection-chip #controlConnectionLabel\s*\{\s*display:\s*inline/);
  assert.match(rules, /\.sidebar \.read-only-note\s*\{\s*display:\s*flex/);
});

test('long telemetry metadata stays inside its KPI card without shrinking the icon', () => {
  assert.match(rules, /\.kpi-card\s*\{[^}]*min-width:\s*0/);
  assert.match(rules, /\.kpi-card > div:not\(\.kpi-icon\)\s*\{[^}]*min-width:\s*0;[^}]*flex:\s*1/);
});

test('map editor action groups wrap instead of clipping undo and reset controls', () => {
  assert.match(rules, /\.map-editor-toolbar\s*\{[^}]*display:\s*flex;[^}]*flex-wrap:\s*wrap/);
  assert.match(rules, /\.map-editor-brush-size\s*\{[^}]*flex:\s*1 1 140px;[^}]*min-width:\s*0/);
});
