(function mapEditorModule(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RobotMapEditor = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function buildMapEditor() {
  'use strict';

  const CELL_UNKNOWN = -1;
  const CELL_FREE = 0;
  const CELL_OBSTACLE = 100;
  const CELL_VALUES = Object.freeze([CELL_UNKNOWN, CELL_FREE, CELL_OBSTACLE]);

  function positiveInteger(value, name) {
    const number = Number(value);
    if (!Number.isInteger(number) || number <= 0) throw new TypeError(`${name} must be a positive integer`);
    return number;
  }

  function normalizeCell(value) {
    const number = Number(value);
    if (number < 0) return CELL_UNKNOWN;
    if (number >= 65) return CELL_OBSTACLE;
    return CELL_FREE;
  }

  function normalizeRotationDegrees(value) {
    const degrees = Number(value);
    if (!Number.isFinite(degrees) || degrees < -180 || degrees > 180) {
      throw new RangeError('rotationDegrees must be between -180 and 180');
    }
    return Object.is(degrees, -0) ? 0 : degrees;
  }

  function rotatedDimensions(width, height, rotationDegrees = 0) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    const radians = normalizeRotationDegrees(rotationDegrees) * Math.PI / 180;
    const cosine = Math.abs(Math.cos(radians));
    const sine = Math.abs(Math.sin(radians));
    return Object.freeze({
      width: Math.max(1, Math.ceil(columns * cosine + rows * sine - 1e-10)),
      height: Math.max(1, Math.ceil(columns * sine + rows * cosine - 1e-10)),
    });
  }

  function sourceCellFromRotatedCell(width, height, rotationDegrees, rotatedX, rotatedY) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    const degrees = normalizeRotationDegrees(rotationDegrees);
    const output = rotatedDimensions(columns, rows, degrees);
    const x = Math.floor(Number(rotatedX));
    const y = Math.floor(Number(rotatedY));
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x >= output.width || y >= output.height) return null;
    const radians = degrees * Math.PI / 180;
    const dx = x - (output.width - 1) / 2;
    const dy = y - (output.height - 1) / 2;
    const rawSourceX = Math.round(Math.cos(radians) * dx - Math.sin(radians) * dy + (columns - 1) / 2);
    const rawSourceY = Math.round(Math.sin(radians) * dx + Math.cos(radians) * dy + (rows - 1) / 2);
    const sourceX = rawSourceX === 0 ? 0 : rawSourceX;
    const sourceY = rawSourceY === 0 ? 0 : rawSourceY;
    if (sourceX < 0 || sourceY < 0 || sourceX >= columns || sourceY >= rows) return null;
    return Object.freeze({ x: sourceX, y: sourceY });
  }

  function cellColor(value) {
    if (normalizeCell(value) === CELL_OBSTACLE) return [7, 10, 9];
    if (normalizeCell(value) === CELL_FREE) return [242, 246, 244];
    return [126, 137, 133];
  }

  function createSourceCanvas(documentValue, cells, width, height) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    if (!(cells instanceof Int8Array) || cells.length !== columns * rows) throw new TypeError('cells must match width and height');
    const canvas = documentValue.createElement('canvas');
    canvas.width = columns;
    canvas.height = rows;
    const context = canvas.getContext('2d');
    const image = context.createImageData(columns, rows);
    for (let index = 0; index < cells.length; index += 1) {
      const x = index % columns;
      const y = Math.floor(index / columns);
      const output = ((rows - 1 - y) * columns + x) * 4;
      const color = cellColor(cells[index]);
      image.data.set([...color, 255], output);
    }
    context.putImageData(image, 0, 0);
    return Object.freeze({ canvas, context });
  }

  function updateSourceCanvas(context, cells, width, height, changes) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    if (!(cells instanceof Int8Array) || cells.length !== columns * rows || !context) return;
    for (const change of changes || []) {
      const x = change.index % columns;
      const y = Math.floor(change.index / columns);
      context.fillStyle = `rgb(${cellColor(cells[change.index]).join(',')})`;
      context.fillRect(x, rows - 1 - y, 1, 1);
    }
  }

  function drawRotatedSource(context, sourceCanvas, viewportWidth, viewportHeight, rotationDegrees, pixelRatio = 1) {
    const output = rotatedDimensions(sourceCanvas.width, sourceCanvas.height, rotationDegrees);
    const scale = Math.min(viewportWidth / output.width, viewportHeight / output.height) * 0.94;
    const drawWidth = output.width * scale;
    const drawHeight = output.height * scale;
    const left = (viewportWidth - drawWidth) / 2;
    const top = (viewportHeight - drawHeight) / 2;
    context.imageSmoothingEnabled = false;
    context.save();
    context.translate(left + drawWidth / 2, top + drawHeight / 2);
    context.rotate(normalizeRotationDegrees(rotationDegrees) * Math.PI / 180);
    context.drawImage(sourceCanvas, -sourceCanvas.width * scale / 2, -sourceCanvas.height * scale / 2, sourceCanvas.width * scale, sourceCanvas.height * scale);
    context.restore();
    context.strokeStyle = 'rgba(93,222,216,.48)';
    context.lineWidth = Math.max(1, Math.min(Number(pixelRatio) || 1, 2));
    context.strokeRect(left, top, drawWidth, drawHeight);
    return Object.freeze({ left, top, drawWidth, drawHeight, scale, outputWidth: output.width, outputHeight: output.height, rotationDegrees: normalizeRotationDegrees(rotationDegrees), canvasWidth: viewportWidth, canvasHeight: viewportHeight });
  }

  function decodeGrid(dataB64, width, height) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    const encoded = String(dataB64 || '');
    let bytes;
    if (typeof atob === 'function') {
      const binary = atob(encoded);
      bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    } else if (typeof Buffer !== 'undefined') {
      bytes = Uint8Array.from(Buffer.from(encoded, 'base64'));
    } else {
      throw new Error('base64 decoder is unavailable');
    }
    if (bytes.length !== columns * rows) throw new RangeError('occupancy grid cell count does not match its dimensions');
    return Int8Array.from(bytes, (byte) => normalizeCell(byte > 127 ? byte - 256 : byte));
  }

  function paintCircle(grid, width, height, centerX, centerY, brushSize, valueOrResolver) {
    const columns = positiveInteger(width, 'width');
    const rows = positiveInteger(height, 'height');
    if (!(grid instanceof Int8Array) || grid.length !== columns * rows) throw new TypeError('grid must match width and height');
    const x0 = Math.round(Number(centerX));
    const y0 = Math.round(Number(centerY));
    const diameter = Math.max(1, Math.min(128, Math.round(Number(brushSize) || 1)));
    const radius = (diameter - 1) / 2;
    const reach = Math.ceil(radius);
    const radiusSquared = Math.pow(radius + 0.35, 2);
    const resolve = typeof valueOrResolver === 'function'
      ? valueOrResolver
      : () => normalizeCell(valueOrResolver);
    const changes = [];
    for (let y = y0 - reach; y <= y0 + reach; y += 1) {
      if (y < 0 || y >= rows) continue;
      for (let x = x0 - reach; x <= x0 + reach; x += 1) {
        if (x < 0 || x >= columns) continue;
        if ((x - x0) ** 2 + (y - y0) ** 2 > radiusSquared) continue;
        const index = y * columns + x;
        const before = normalizeCell(grid[index]);
        const after = normalizeCell(resolve(index, before));
        if (before === after) continue;
        grid[index] = after;
        changes.push({ index, before, after });
      }
    }
    return changes;
  }

  function interpolateCells(from, to, spacing = 1) {
    const start = { x: Math.round(Number(from?.x)), y: Math.round(Number(from?.y)) };
    const end = { x: Math.round(Number(to?.x)), y: Math.round(Number(to?.y)) };
    if (![start.x, start.y, end.x, end.y].every(Number.isFinite)) return [];
    const distance = Math.max(Math.abs(end.x - start.x), Math.abs(end.y - start.y));
    const steps = Math.max(1, Math.ceil(distance / Math.max(1, Number(spacing) || 1)));
    const points = [];
    for (let step = 1; step <= steps; step += 1) {
      points.push({
        x: Math.round(start.x + ((end.x - start.x) * step) / steps),
        y: Math.round(start.y + ((end.y - start.y) * step) / steps),
      });
    }
    return points;
  }

  function diffRuns(original, edited) {
    if (!(original instanceof Int8Array) || !(edited instanceof Int8Array) || original.length !== edited.length) {
      throw new TypeError('original and edited grids must be equal-length Int8Array values');
    }
    const runs = [];
    let current = null;
    for (let index = 0; index < edited.length; index += 1) {
      const before = normalizeCell(original[index]);
      const value = normalizeCell(edited[index]);
      if (before === value) {
        current = null;
        continue;
      }
      if (current && current.start + current.length === index && current.value === value) {
        current.length += 1;
      } else {
        current = { start: index, length: 1, value };
        runs.push(current);
      }
    }
    return runs;
  }

  function applyRuns(original, runs) {
    if (!(original instanceof Int8Array)) throw new TypeError('original must be an Int8Array');
    const result = original.slice();
    let previousEnd = 0;
    for (const run of runs || []) {
      const start = Number(run?.start);
      const length = Number(run?.length);
      const value = Number(run?.value);
      if (!Number.isInteger(start) || !Number.isInteger(length) || start < previousEnd || length <= 0 || start + length > result.length) {
        throw new RangeError('edit runs must be ordered, non-overlapping and in bounds');
      }
      if (!CELL_VALUES.includes(value)) throw new RangeError('edit run value must be -1, 0 or 100');
      result.fill(value, start, start + length);
      previousEnd = start + length;
    }
    return result;
  }

  function replaceCellValue(grid, fromValue, toValue) {
    if (!(grid instanceof Int8Array)) throw new TypeError('grid must be an Int8Array');
    const beforeValue = normalizeCell(fromValue);
    const afterValue = normalizeCell(toValue);
    if (beforeValue === afterValue) return [];
    const changes = [];
    for (let index = 0; index < grid.length; index += 1) {
      const before = normalizeCell(grid[index]);
      if (before !== beforeValue) continue;
      grid[index] = afterValue;
      changes.push({ index, before, after: afterValue });
    }
    return changes;
  }

  function replaceUnknownWithConfirmation(grid, confirmAction) {
    if (!(grid instanceof Int8Array)) throw new TypeError('grid must be an Int8Array');
    if (typeof confirmAction !== 'function') throw new TypeError('confirmAction must be a function');
    let count = 0;
    for (const value of grid) count += normalizeCell(value) === CELL_UNKNOWN ? 1 : 0;
    if (!count) return [];
    const message = `미확인 셀 ${count.toLocaleString()}개를 모두 빈 공간으로 바꿀까요?\n\n`
      + '미관측 장애물이 주행 가능 영역으로 해석될 수 있습니다. 실제 지도를 확인하고 필요한 영역을 다시 그린 뒤 별도 복사본으로 저장하세요. 원본 지도는 변경되지 않습니다.';
    return confirmAction(message) ? replaceCellValue(grid, CELL_UNKNOWN, CELL_FREE) : [];
  }

  return Object.freeze({
    CELL_UNKNOWN,
    CELL_FREE,
    CELL_OBSTACLE,
    CELL_VALUES,
    normalizeCell,
    normalizeRotationDegrees,
    rotatedDimensions,
    sourceCellFromRotatedCell,
    createSourceCanvas,
    updateSourceCanvas,
    drawRotatedSource,
    decodeGrid,
    paintCircle,
    interpolateCells,
    diffRuns,
    applyRuns,
    replaceCellValue,
    replaceUnknownWithConfirmation,
  });
}));
