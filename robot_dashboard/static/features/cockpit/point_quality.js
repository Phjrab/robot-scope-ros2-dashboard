export const COCKPIT_POINT_BUDGETS = Object.freeze({ low: 10_000, medium: 30_000, high: 60_000 });
export const COCKPIT_MAX_POINTS = COCKPIT_POINT_BUDGETS.high;

const LEVELS = Object.freeze(Object.keys(COCKPIT_POINT_BUDGETS));
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const normalizedLevel = (value, fallback = 'low') => LEVELS.includes(value) ? value : fallback;

function allocateBandQuotas(counts, budget) {
  const weights = [1, 0.45, 0.15];
  const quotas = [0, 0, 0];
  const scores = counts.map((count, index) => count * weights[index]);
  const scoreTotal = scores.reduce((sum, value) => sum + value, 0);
  if (!scoreTotal || !budget) return quotas;
  for (let band = 0; band < 3; band += 1) {
    quotas[band] = Math.min(counts[band], Math.floor(budget * scores[band] / scoreTotal));
  }
  let remaining = budget - quotas.reduce((sum, value) => sum + value, 0);
  while (remaining > 0) {
    let changed = false;
    for (let band = 0; band < 3 && remaining > 0; band += 1) {
      if (quotas[band] >= counts[band]) continue;
      quotas[band] += 1;
      remaining -= 1;
      changed = true;
    }
    if (!changed) break;
  }
  return quotas;
}

function cloudPointCount(cloud) {
  return Math.floor(Number(cloud?.points?.length) / 3) || 0;
}

export function createSpatialPointLod(options = {}) {
  const capacity = clamp(Math.floor(Number(options.maxPoints) || COCKPIT_MAX_POINTS), 1_000, COCKPIT_MAX_POINTS);
  const buffers = [new Float32Array(capacity * 3), new Float32Array(capacity * 3)];
  let bufferIndex = 0;
  let projections = 0;

  function project(cloud, requestedBudget, nearField = true) {
    const input = cloud?.points;
    const available = cloudPointCount(cloud);
    const budget = clamp(Math.floor(Number(requestedBudget) || COCKPIT_POINT_BUDGETS.low), 1_000, capacity);
    if (!input || !available || available <= budget) return cloud;

    bufferIndex = 1 - bufferIndex;
    const output = buffers[bufferIndex];
    let written = 0;
    if (!nearField) {
      const stride = available / budget;
      for (let index = 0; index < budget; index += 1) {
        const source = Math.min(available - 1, Math.floor(index * stride)) * 3;
        const target = written * 3;
        const x = Number(input[source]); const y = Number(input[source + 1]); const z = Number(input[source + 2]);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
        output[target] = x; output[target + 1] = y; output[target + 2] = z;
        written += 1;
      }
    } else {
      const counts = [0, 0, 0];
      for (let source = 0; source < available * 3; source += 3) {
        const x = Number(input[source]); const y = Number(input[source + 1]); const z = Number(input[source + 2]);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
        const radius = Math.hypot(x, y);
        counts[radius < 5 ? 0 : radius < 15 ? 1 : 2] += 1;
      }
      const quotas = allocateBandQuotas(counts, budget);
      const seen = [0, 0, 0];
      const selected = [0, 0, 0];
      for (let band = 0; band < 3; band += 1) {
        if (!quotas[band]) continue;
        const stride = counts[band] / quotas[band];
        for (let source = 0; source < available * 3 && selected[band] < quotas[band]; source += 3) {
          const x = Number(input[source]); const y = Number(input[source + 1]); const z = Number(input[source + 2]);
          if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
          const radius = Math.hypot(x, y);
          const sourceBand = radius < 5 ? 0 : radius < 15 ? 1 : 2;
          if (sourceBand !== band) continue;
          const targetOrdinal = Math.floor(selected[band] * stride);
          if (seen[band]++ < targetOrdinal) continue;
          const target = written * 3;
          output[target] = x; output[target + 1] = y; output[target + 2] = z;
          selected[band] += 1; written += 1;
        }
      }
    }
    projections += 1;
    return {
      ...cloud,
      points: output.subarray(0, written * 3),
      sent_points: written,
      display_points: written,
      prevalidated: true,
      cockpit_lod: Object.freeze({ budget, near_field: Boolean(nearField) }),
    };
  }

  return Object.freeze({
    project,
    diagnostics: () => Object.freeze({ capacity, buffers: buffers.length, allocations: buffers.length, projections }),
  });
}

export function createAdaptivePointBudgetController(options = {}) {
  const minimumDwellMs = Math.max(0, Number(options.minimumDwellMs ?? 3_000));
  const recoveryDwellMs = Math.max(minimumDwellMs, Number(options.recoveryDwellMs ?? 8_000));
  const badSamplesRequired = Math.max(1, Math.floor(Number(options.badSamplesRequired ?? 2)));
  const goodSamplesRequired = Math.max(1, Math.floor(Number(options.goodSamplesRequired ?? 5)));
  let ceiling = normalizedLevel(options.ceiling, 'high');
  let level = normalizedLevel(options.initialLevel, 'low');
  if (LEVELS.indexOf(level) > LEVELS.indexOf(ceiling)) level = ceiling;
  let lastChangeAt = Number(options.now) || 0;
  let badSamples = 0;
  let goodSamples = 0;

  function snapshot() {
    return Object.freeze({ level, ceiling, budget: COCKPIT_POINT_BUDGETS[level], badSamples, goodSamples, lastChangeAt });
  }

  function setCeiling(next, now = 0, adopt = false) {
    ceiling = normalizedLevel(next, ceiling);
    if (adopt) {
      level = ceiling; lastChangeAt = Number(now) || 0;
    } else if (LEVELS.indexOf(level) > LEVELS.indexOf(ceiling)) {
      level = ceiling; lastChangeAt = Number(now) || 0;
    }
    badSamples = 0; goodSamples = 0;
    return snapshot();
  }

  function sample(metrics = {}, now = 0) {
    const time = Number(now) || 0;
    const bad = metrics.stale === true || Number(metrics.droppedFrames) > 0 ||
      Number(metrics.frameMs) > 28 || (Number(metrics.fps) > 0 && Number(metrics.fps) < 28) ||
      Number(metrics.decodeMs) > 10 || Number(metrics.uploadMs) > 8;
    const good = !bad && Number(metrics.frameMs) > 0 && Number(metrics.frameMs) < 18 &&
      Number(metrics.fps) >= 50 && Number(metrics.decodeMs) < 5 && Number(metrics.uploadMs) < 5;
    badSamples = bad ? badSamples + 1 : 0;
    goodSamples = good ? goodSamples + 1 : 0;
    const index = LEVELS.indexOf(level);
    if (badSamples >= badSamplesRequired && index > 0 && time - lastChangeAt >= minimumDwellMs) {
      level = LEVELS[index - 1]; lastChangeAt = time; badSamples = 0; goodSamples = 0;
    } else if (goodSamples >= goodSamplesRequired && index < LEVELS.indexOf(ceiling) && time - lastChangeAt >= recoveryDwellMs) {
      level = LEVELS[index + 1]; lastChangeAt = time; badSamples = 0; goodSamples = 0;
    }
    return snapshot();
  }

  return Object.freeze({ setCeiling, sample, snapshot });
}
