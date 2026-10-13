import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const styles = readFileSync(new URL('../robot_dashboard/static/styles.css', import.meta.url), 'utf8');

test('dashboard uses the readable Mission Control typography scale', () => {
  for (const token of [
    '--type-micro: .75rem',
    '--type-control: .875rem',
    '--type-secondary: .875rem',
    '--type-body: .9375rem',
    '--type-section: 1.125rem',
  ]) {
    assert.match(styles, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }

  assert.match(styles, /\.control-action-card > span \{ font-size:var\(--type-micro\); \}/);
  assert.match(styles, /\.control-action-card > strong \{ font-size:var\(--type-body\); \}/);
  assert.match(styles, /\.control-action-card > small \{ font-size:var\(--type-secondary\); \}/);
  assert.match(styles, /\.control-action-card button,[\s\S]*?font-size:var\(--type-control\);/);
  assert.match(styles, /\.panel-header h2 \{ font-size:var\(--type-section\); \}/);
  assert.match(styles, /body,\s*input,\s*select \{ font-size:var\(--type-secondary\); \}/);
});

test('all workspaces share the scale while canvas HUD remains compact', () => {
  for (const selector of [
    '.mapping-safety-note',
    '.saved-map-item small',
    '.sensor-value',
    'td',
    '.robot-type-note',
    '.navigation-parameter-field small',
  ]) {
    assert.ok(styles.includes(selector), `${selector} is part of the unified scale`);
  }

  assert.match(styles, /\.stream-overlay, \.map-meta \{[^}]*font-size: 12px/);
  assert.match(styles, /\.scene-controls button \{[^}]*font: 600 12px/);
});
