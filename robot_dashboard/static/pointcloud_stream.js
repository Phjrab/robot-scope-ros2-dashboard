(function attachPointCloudStream(global) {
  'use strict';

  const MAGIC = [0x52, 0x53, 0x50, 0x43]; // RSPC
  const HEADER_BYTES = 16;
  const MAX_METADATA_BYTES = 16384;
  const MAX_POINT_BYTES = 12000000;
  const textDecoder = typeof TextDecoder === 'function' ? new TextDecoder('utf-8', { fatal: true }) : null;

  function boundedArrayBuffer(input) {
    if (input instanceof ArrayBuffer) return { buffer: input, byteOffset: 0, byteLength: input.byteLength };
    if (ArrayBuffer.isView(input)) return {
      buffer: input.buffer,
      byteOffset: input.byteOffset,
      byteLength: input.byteLength,
    };
    throw new Error('point-cloud frame must be an ArrayBuffer');
  }

  function decodeFrame(input) {
    const source = boundedArrayBuffer(input);
    if (source.byteLength < HEADER_BYTES) throw new Error('point-cloud frame is truncated');
    const view = new DataView(source.buffer, source.byteOffset, source.byteLength);
    if (MAGIC.some((value, index) => view.getUint8(index) !== value)) throw new Error('invalid point-cloud frame magic');
    const version = view.getUint8(4);
    const flags = view.getUint8(5);
    if (version !== 1 || flags !== 0) throw new Error('unsupported point-cloud frame version');
    const metadataBytes = view.getUint16(6, true);
    const pointCount = view.getUint32(8, true);
    const pointBytes = view.getUint32(12, true);
    if (!metadataBytes || metadataBytes > MAX_METADATA_BYTES) throw new Error('invalid point-cloud metadata size');
    if (pointBytes !== pointCount * 12 || pointBytes > MAX_POINT_BYTES) throw new Error('invalid point-cloud payload size');
    const payloadOffset = (HEADER_BYTES + metadataBytes + 3) & ~3;
    if (payloadOffset + pointBytes !== source.byteLength) throw new Error('point-cloud frame length mismatch');
    if (!textDecoder) throw new Error('TextDecoder is unavailable');

    let metadata;
    try {
      const encoded = new Uint8Array(source.buffer, source.byteOffset + HEADER_BYTES, metadataBytes);
      metadata = JSON.parse(textDecoder.decode(encoded));
    } catch (_) {
      throw new Error('invalid point-cloud metadata JSON');
    }
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) throw new Error('invalid point-cloud metadata');
    if (metadata.encoding !== 'float32le' || metadata.point_count !== pointCount) {
      throw new Error('point-cloud metadata does not match its payload');
    }

    const absoluteOffset = source.byteOffset + payloadOffset;
    let points;
    if ((absoluteOffset & 3) === 0) {
      points = new Float32Array(source.buffer, absoluteOffset, pointCount * 3);
    } else {
      const copy = new Uint8Array(pointBytes);
      copy.set(new Uint8Array(source.buffer, absoluteOffset, pointBytes));
      points = new Float32Array(copy.buffer);
    }
    for (let index = 0; index < points.length; index += 1) {
      if (!Number.isFinite(points[index])) throw new Error('point-cloud payload contains non-finite XYZ');
    }
    return {
      ...metadata,
      points,
      sent_points: Number(metadata.sent_points ?? pointCount),
      prevalidated: true,
    };
  }

  function finiteBounds(bounds) {
    if (!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)) return null;
    const min = bounds.min.slice(0, 3).map(Number);
    const max = bounds.max.slice(0, 3).map(Number);
    if (min.length !== 3 || max.length !== 3 || !min.every(Number.isFinite) || !max.every(Number.isFinite)) return null;
    if (min.some((value, index) => value > max[index])) return null;
    return { min, max };
  }

  class RegisteredCloudReservoir {
    constructor(maxAllPoints = 1000000) {
      this.maxAllPoints = Math.max(1000, Math.floor(Number(maxAllPoints) || 1000000));
      this.reset();
    }

    reset() {
      this.key = '';
      this.capacity = 0;
      this.buffer = new Float32Array(0);
      this.size = 0;
      this.seen = 0;
      this.bounds = null;
      this.lastSeq = null;
      this.lastPayload = null;
      this.randomState = 0x9e3779b9;
    }

    _configure(key, requestedLimit) {
      const capacity = requestedLimit == null
        ? this.maxAllPoints
        : Math.max(1000, Math.min(this.maxAllPoints, Math.floor(Number(requestedLimit) || 10000)));
      if (this.key === key && this.capacity === capacity) return;
      this.reset();
      this.key = key;
      this.capacity = capacity;
      this.buffer = new Float32Array(capacity * 3);
    }

    _randomIndex(span) {
      let value = this.randomState >>> 0;
      value ^= value << 13;
      value ^= value >>> 17;
      value ^= value << 5;
      this.randomState = value >>> 0;
      return Math.floor((this.randomState / 0x100000000) * span);
    }

    ingest(cloud, requestedLimit) {
      if (!cloud?.points || typeof cloud.points.length !== 'number') return cloud;
      const key = `${cloud.topic || ''}:${cloud.frame_id || ''}`;
      this._configure(key, requestedLimit);
      if (this.lastSeq === cloud.seq && this.lastPayload) return this.lastPayload;

      const input = cloud.points;
      const available = Math.floor(input.length / 3);
      for (let point = 0; point < available; point += 1) {
        const offset = point * 3;
        const x = Number(input[offset]);
        const y = Number(input[offset + 1]);
        const z = Number(input[offset + 2]);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
        this.seen += 1;
        let target = this.size;
        if (this.size < this.capacity) {
          this.size += 1;
        } else {
          target = this._randomIndex(this.seen);
          if (target >= this.capacity) continue;
        }
        const destination = target * 3;
        this.buffer[destination] = x;
        this.buffer[destination + 1] = y;
        this.buffer[destination + 2] = z;
      }

      const nextBounds = finiteBounds(cloud.bounds);
      if (nextBounds) {
        this.bounds = this.bounds ? {
          min: this.bounds.min.map((value, index) => Math.min(value, nextBounds.min[index])),
          max: this.bounds.max.map((value, index) => Math.max(value, nextBounds.max[index])),
        } : nextBounds;
      }
      const payload = {
        ...cloud,
        points: this.buffer.subarray(0, this.size * 3),
        bounds: this.bounds || nextBounds,
        sent_points: this.size,
        // `source_points` may already describe a cumulative /Laser_map.  Sum
        // neither it nor repeated frames; use the largest defensible count.
        source_points: Math.max(
          this.size,
          this.seen,
          Number(cloud.source_points) || available,
        ),
        frame_source_points: Math.max(available, Number(cloud.source_points) || available),
        accumulated_registered_scans: true,
        prevalidated: cloud.prevalidated === true,
        display_capped: requestedLimit == null && this.size >= this.maxAllPoints,
      };
      this.lastSeq = cloud.seq;
      this.lastPayload = payload;
      return payload;
    }
  }

  global.RobotPointCloudStream = Object.freeze({
    decodeFrame,
    RegisteredCloudReservoir,
    protocol: 'robot-scope-pointcloud-v1',
    maxPointCount: MAX_POINT_BYTES / 12,
  });
})(typeof window !== 'undefined' ? window : globalThis);
