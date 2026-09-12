import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const navigation = require('../robot_dashboard/static/navigation.js');
const source = readFileSync(new URL('../robot_dashboard/static/features/navigation/presets.js', import.meta.url), 'utf8');
const { createNavigationPresetCatalog } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const values = () => ({ ...navigation.TUNED_VALUES });
const validate = (draft) => navigation.parameterValues(draft, { requireAll: true });
const entry = (label = '팀 A') => ({ id: `user-${'a'.repeat(32)}`, label, values: values() });

test('save captures draft, uses catalog API only, and does not mutate draft', async () => {
  const calls = [];
  const draft = values();
  const catalog = createNavigationPresetCatalog({ validate, api: async (path, options) => {
    calls.push([path, options]);
    return { preset: entry(), presets: [entry()] };
  } });
  assert.equal(await catalog.save(' 팀 A ', draft), entry().id);
  assert.deepEqual(draft, values());
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/v1/navigation/presets');
  assert.equal(calls[0][1].method, 'POST');
  assert.deepEqual(JSON.parse(calls[0][1].body), { name: '팀 A', values: values() });
  assert.equal(catalog.presets[0].label, '사용자 · 팀 A');
});

test('busy catalog rejects overlapping save and refresh, then releases busy', async () => {
  let resolve;
  let calls = 0;
  const catalog = createNavigationPresetCatalog({ validate, api: () => { calls++; return new Promise((r) => { resolve = r; }); } });
  const draft = values();
  const saving = catalog.save('one', draft);
  draft.desired_linear_vel = 0.7;
  assert.equal(catalog.busy, true);
  assert.equal(await catalog.save('two', values()), null);
  assert.equal(await catalog.refresh(), null);
  resolve({ preset: entry(), presets: [entry()] });
  await saving;
  assert.equal(calls, 1);
  assert.equal(catalog.busy, false);
  assert.equal(draft.desired_linear_vel, 0.7);
});

test('invalid names and values never call API', async () => {
  const catalog = createNavigationPresetCatalog({ validate, api: () => assert.fail('unexpected request') });
  for (const name of ['', ' ', 'a'.repeat(65), 'a\nb']) await assert.rejects(catalog.save(name, values()));
  await assert.rejects(catalog.save('one', { ...values(), desired_linear_vel: 4 }));
  await assert.rejects(catalog.save('one', {}));
  assert.equal(catalog.busy, false);
});

test('failed refresh or save preserves catalog and releases busy', async () => {
  let fail = false;
  const catalog = createNavigationPresetCatalog({ validate, api: async () => {
    if (fail) throw new Error('duplicate or offline');
    return { presets: [entry()] };
  } });
  await catalog.refresh();
  fail = true;
  await assert.rejects(catalog.save('one', values()));
  await assert.rejects(catalog.refresh());
  assert.equal(catalog.presets.length, 1);
  assert.equal(catalog.busy, false);
});

test('invalid server catalog cannot replace last good list', async () => {
  let payload = { presets: [entry()] };
  const catalog = createNavigationPresetCatalog({ validate, api: async () => payload });
  await catalog.refresh();
  for (const presets of [[{ ...entry(), id: '<script>' }], [entry(), entry()], [{ ...entry(), values: {} }]]) {
    payload = { presets };
    await assert.rejects(catalog.refresh());
    assert.equal(catalog.presets.length, 1);
  }
});

test('dashboard wires escaped preset options and separate creation controls', () => {
  const app = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
  const html = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');
  for (const id of ['navigationPresetName', 'navigationPresetSave', 'navigationPresetRefresh', 'navigationPresetMessage']) assert.ok(html.includes(`id="${id}"`));
  assert.ok(app.includes('escapeHtml(preset.label)'));
  assert.ok(source.includes("navigationPresetSave.addEventListener('click', save)"));
  assert.ok(app.includes('navigationParameterBusy || pipelineActive || !dirty'));
});
