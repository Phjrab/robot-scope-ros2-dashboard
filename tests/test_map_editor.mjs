import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const editor = require('../robot_dashboard/static/map_editor.js');
const appSource = readFileSync(new URL('../robot_dashboard/static/app.js', import.meta.url), 'utf8');
const indexSource = readFileSync(new URL('../robot_dashboard/static/index.html', import.meta.url), 'utf8');

test('occupancy base64 decodes to canonical unknown, free and obstacle cells', () => {
  const encoded = Buffer.from([255, 0, 42, 100]).toString('base64');
  assert.deepEqual(Array.from(editor.decodeGrid(encoded, 2, 2)), [-1, 0, 0, 100]);
  assert.throws(() => editor.decodeGrid(encoded, 3, 2), /cell count/);
});

test('brush painting is bounded and eraser resolvers can restore original cells', () => {
  const original = Int8Array.from({ length: 25 }, () => -1);
  const grid = original.slice();
  const painted = editor.paintCircle(grid, 5, 5, 2, 2, 3, 100);
  assert.ok(painted.length > 1);
  assert.ok(painted.every(({ index }) => index >= 0 && index < grid.length));
  assert.equal(grid[12], 100);
  const restored = editor.paintCircle(grid, 5, 5, 2, 2, 3, (index) => original[index]);
  assert.equal(restored.length, painted.length);
  assert.deepEqual(Array.from(grid), Array.from(original));
});

test('interpolated brush points close gaps in fast pointer strokes', () => {
  assert.deepEqual(editor.interpolateCells({ x: 0, y: 0 }, { x: 4, y: 0 }, 1), [
    { x: 1, y: 0 }, { x: 2, y: 0 }, { x: 3, y: 0 }, { x: 4, y: 0 },
  ]);
});

test('edited cells serialize as compact ordered runs and reproduce the grid', () => {
  const original = Int8Array.from([0, 0, 0, -1, -1, 100, 100, 0]);
  const edited = Int8Array.from([0, 100, 100, -1, 0, 0, 100, 0]);
  const runs = editor.diffRuns(original, edited);
  assert.deepEqual(runs, [
    { start: 1, length: 2, value: 100 },
    { start: 4, length: 2, value: 0 },
  ]);
  assert.deepEqual(Array.from(editor.applyRuns(original, runs)), Array.from(edited));
  assert.throws(() => editor.applyRuns(original, [{ start: 0, length: 1, value: 50 }]), /-1, 0 or 100/);
});

test('Saved Maps exposes PDF 09 conversion parameters, progress and safe background choice', () => {
  for (const id of [
    'mapConvertSource', 'mapConvertName', 'mapConvertZMin', 'mapConvertZMax',
    'mapConvertResolution', 'mapConvertRadius', 'mapConvertNeighbors',
    'mapConvertBackground', 'mapConvertStart', 'mapConvertProgress', 'mapConvertMessage',
  ]) assert.match(indexSource, new RegExp(`id="${id}"`));
  assert.match(indexSource, /z=0은 XT16 LiDAR 높이 기준/);
  assert.match(indexSource, /id="mapConvertZMin"[^>]+min="-20"[^>]+max="20"/);
  assert.match(indexSource, /id="mapConvertZMax"[^>]+min="-20"[^>]+max="20"/);
  assert.match(indexSource, /value="unknown" selected/);
  assert.match(indexSource, /value="free">FREE · 경계 전체 자유공간/);
  assert.match(indexSource, /자동 점 노이즈 필터 \(2D 투영\)/);
  assert.match(indexSource, /PCL 3D RadiusOutlierRemoval와 동일한 알고리즘이 아닙니다/);
  assert.match(appSource, /주의: FREE는 PCD 경계 사각형의 미관측 영역까지 자유공간으로 처리합니다/);
});

test('conversion uses only manageable binary PCD and the backend operation contract', () => {
  assert.match(appSource, /entry\.kind === 'pointcloud3d' && entry\.manageable && entry\.format === 'pcd-binary'/);
  assert.match(appSource, /\/api\/v1\/saved-maps\/\$\{encodeURIComponent\(source\.id\)\}\/convert-2d/);
  for (const field of ['z_min', 'z_max', 'resolution', 'noise_radius', 'min_neighbors', 'background']) {
    assert.match(appSource, new RegExp(`${field}[:,]`));
  }
  assert.match(appSource, /renderMapConversionOperation\(operation\)/);
  assert.match(appSource, /conversionNumber\(ui\.mapConvertZMin, 'thre_z_min', -20, 20\)/);
  assert.match(appSource, /conversionNumber\(ui\.mapConvertZMax, 'thre_z_max', -20, 20\)/);
  assert.match(appSource, /operationJobId && responseJobId && operationJobId !== responseJobId/);
  assert.match(appSource, /if \(!\/\^\[0-9a-f\]\{32\}\$\/\.test\(jobId\)\) throw new Error\('서버가 유효한 변환 작업 job_id를 반환하지 않았습니다/);
  assert.match(appSource, /operation\.details\?\.result_map_id \|\| operation\.result_map_id/);
  assert.match(appSource, /savedMapCatalog\.find\(\(entry\) => entry\.id === resultId\)/);
  assert.match(appSource, /await selectSavedMap\(result\.id, false, true\)/);
});

test('conversion status is bound only to the reserved backend job id', () => {
  const start = appSource.indexOf('function mapConversionMatches(operation)');
  const end = appSource.indexOf('\nfunction normalizedOperationProgress(', start);
  assert.ok(start >= 0 && end > start, 'mapConversionMatches must exist');
  const matcher = appSource.slice(start, end);
  assert.match(matcher, /!mapConversionPending\?\.jobId \|\| !operation\?\.job_id/);
  assert.match(matcher, /String\(operation\.job_id\) === mapConversionPending\.jobId/);
  assert.doesNotMatch(matcher, /map_name|operation\.name|pending\.name/);
  assert.match(appSource, /operation\.kind !== 'pcd_to_2d'/);
  assert.match(appSource, /MAP_CONVERSION_TRACKING_TIMEOUT_MS = 15 \* 60 \* 1000/);
  assert.match(appSource, /if \(!mapConversionMatches\(operation\)\) \{[\s\S]{0,180}failMapConversionTracking/);
  assert.match(appSource, /requestGeneration !== mappingControlRequestGeneration/);
  assert.match(appSource, /mappingControlRequestGeneration \+= 1/);
  const matcherBody = matcher.slice(matcher.indexOf('{') + 1, matcher.lastIndexOf('}'));
  const matchesJob = new Function('mapConversionPending', 'operation', matcherBody);
  assert.equal(matchesJob({ jobId: 'a'.repeat(32) }, { job_id: 'a'.repeat(32) }), true);
  assert.equal(matchesJob({ jobId: 'a'.repeat(32) }, { job_id: 'b'.repeat(32) }), false);
  assert.equal(matchesJob({ jobId: 'a'.repeat(32) }, { state: 'idle', job_id: null }), false);
});

test('2D editor exposes brush, eraser, semantic values and non-destructive history', () => {
  for (const value of ['brush', 'eraser']) assert.match(indexSource, new RegExp(`data-map-editor-tool="${value}"`));
  for (const value of ['100', '0', '-1']) assert.match(indexSource, new RegExp(`data-map-editor-value="${value}"`));
  for (const id of ['mapEditorBrushSize', 'mapEditorUndo', 'mapEditorRedo', 'mapEditorReset', 'mapEditorSaveName', 'mapEditorSave']) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(indexSource, /SAVE AS COPY/);
  assert.match(indexSource, /원본 YAML·PGM은 변경하지 않습니다/);
  assert.match(appSource, /if \(meta\?\.manageable !== true\)/);
  assert.match(appSource, /if \(meta\?\.editable !== true\)/);
  assert.match(appSource, /grid && \(!entry\.manageable \|\| entry\.editable !== true\) \? `\$\{fileLabel\} · 편집 불가`/);
  assert.match(appSource, /P5 8-bit trinary YAML·PGM 지도만 안전하게 편집/);
  assert.match(appSource, /안전을 위해 편집을 비활성화했습니다/);
});

test('edited copy sends a strong source revision and compact runs, never a full grid', () => {
  const start = appSource.indexOf('async function saveMapEditorCopy()');
  const end = appSource.indexOf('\nfunction compactValue(', start);
  assert.ok(start >= 0 && end > start, 'saveMapEditorCopy must exist');
  const save = appSource.slice(start, end);
  assert.match(save, /\/api\/v1\/saved-maps\/\$\{encodeURIComponent\(session\.sourceId\)\}\/edited-copy/);
  assert.match(save, /source_revision: session\.revision/);
  assert.match(save, /runs,/);
  assert.doesNotMatch(save, /data_b64|session\.seq|snapshot\.seq/);
  assert.match(appSource, /\^\[0-9a-f\]\{64\}\$\//);
});

test('revision-aware cache and dirty lifecycle prevent silent edit loss', () => {
  assert.match(appSource, /pointBudgetCacheKey\(mapId, limit = savedPointLimit, kind = 'pointcloud3d', revision = ''\)/);
  assert.match(appSource, /pointBudgetCacheKey\(next\.id, savedPointLimit, next\.kind, next\.revision\)/);
  assert.match(appSource, /editorHasUnsavedChanges\(\)[\s\S]{0,220}preserved\.revision !== mapEditorSession\.revision/);
  assert.match(appSource, /mapEditorSession\.sourceStale = true/);
  assert.match(appSource, /mapEditorSave\.disabled = [^;]+session\?\.sourceStale/);
  assert.match(appSource, /confirmDiscardMapEditor\('저장하지 않은 2D 편집을 버리고 다른 지도를 선택할까요\?'/);
  assert.match(appSource, /previousPage === 'maps'[\s\S]{0,220}confirmDiscardMapEditor/);
  assert.match(appSource, /window\.addEventListener\('beforeunload'/);
  assert.match(appSource, /editorHasUnsavedChanges\(\) \|\| mapConversionPending/);
  assert.match(appSource, /const loadGeneration = \+\+savedMapSelectionGeneration/);
  assert.match(appSource, /loadGeneration === savedMapSelectionGeneration/);
  assert.match(appSource, /String\(selectedSavedMapMeta\?\.revision \|\| ''\) === expectedRevision/);
  assert.match(appSource, /String\(payload\?\.revision \|\| ''\) !== expectedRevision/);
  const currentExpression = appSource.match(/const loadIsCurrent = \(\) => \(\n([\s\S]*?)\n  \);/);
  assert.ok(currentExpression, 'selection generation guard must be extractable');
  const isCurrent = new Function(
    'loadGeneration', 'savedMapSelectionGeneration', 'selectedSavedMapId',
    'meta', 'selectedSavedMapMeta', 'expectedRevision',
    `return (${currentExpression[1]});`,
  );
  const meta = { id: 'same-map' };
  assert.equal(isCurrent(2, 2, 'same-map', meta, { revision: 'b' }, 'b'), true);
  assert.equal(isCurrent(1, 2, 'same-map', meta, { revision: 'b' }, 'a'), false);
  assert.equal(isCurrent(2, 2, 'same-map', meta, { revision: 'a' }, 'b'), false);
});

test('edited-copy success explicitly discards the old dirty editor before selecting its result', () => {
  const start = appSource.indexOf('async function saveMapEditorCopy()');
  const end = appSource.indexOf('\nfunction compactValue(', start);
  const save = appSource.slice(start, end);
  const responseAccepted = save.indexOf('createdCopy = result;');
  const detached = save.indexOf('detachMapEditor(', responseAccepted);
  const selected = save.indexOf('await selectSavedMap(result.id', detached);
  assert.ok(responseAccepted >= 0 && detached > responseAccepted && selected > detached);
});
