import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const start = source.indexOf('async function syncNavigationMapOptions()');
const end = source.indexOf('function resetMapAnnotations(', start);

function fixture() {
  const map = { id: 'map', revision: 'pinned', name: 'map' };
  const state = {
    candidates: [map], navigationSnapshot: { map }, navigationSelectedMapMeta: map,
    navigationMapSnapshot: { revision: 'pinned' }, navigationMapSourceCanvas: {},
    navigationMapError: '', selectedSavedMapMeta: null, selectedSavedMapId: '',
    ui: { navigationMapSelect: { value: 'map', innerHTML: '' } },
    navigationEngine: { pipelineActive: () => true }, escapeHtml: value => value,
    discardNavigationPose() {}, renderNavigationStatus() {}, drawNavigationMap() {},
    loadNavigationMap() { assert.fail('exact cached map must not be reloaded'); },
  };
  state.navigationMapCandidates = () => state.candidates;
  runInNewContext(source.slice(start, end), state);
  return { state, map };
}

test('temporary catalog mismatch recovers with the already decoded exact map', async () => {
  const { state, map } = fixture();
  state.candidates = [];
  assert.equal(await state.syncNavigationMapOptions(), false);
  assert.match(state.navigationMapError, /revision/);
  state.candidates = [map];
  assert.equal(await state.syncNavigationMapOptions(), true);
  assert.equal(state.navigationMapError, '');
});

test('a real active revision mismatch remains blocked', async () => {
  const { state, map } = fixture();
  state.candidates = [{ ...map, revision: 'changed' }];
  assert.equal(await state.syncNavigationMapOptions(), false);
  assert.match(state.navigationMapError, /revision/);
});

test('cached-map recovery preserves a new rendering error', async () => {
  const { state } = fixture();
  state.navigationMapError = 'old catalog mismatch';
  state.drawNavigationMap = () => { state.navigationMapError = 'render failed'; };
  await state.syncNavigationMapOptions();
  assert.equal(state.navigationMapError, 'render failed');
});
