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

  return Object.freeze({
    CELL_UNKNOWN,
    CELL_FREE,
    CELL_OBSTACLE,
    CELL_VALUES,
    normalizeCell,
    decodeGrid,
    paintCircle,
    interpolateCells,
    diffRuns,
    applyRuns,
  });
}));
