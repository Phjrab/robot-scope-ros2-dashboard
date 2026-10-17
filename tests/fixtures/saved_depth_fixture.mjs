import { createHash } from 'node:crypto';
import { deflateSync } from 'node:zlib';

// Entirely synthetic SDK-shaped artifacts for offline tests. `synthetic:false`
// exercises the stored collector's provenance branch; no camera is accessed.
export function savedDepthFixture(id = 'a'.repeat(32), { width = 40, height = 30 } = {}) {
  const intrinsics = { width, height, fx: 36, fy: 36, ppx: width / 2, ppy: height / 2, model: 'distortion.brown_conrady', coeffs: [0, 0, 0, 0, 0] };
  const extrinsics = { rotation: [1, 0, 0, 0, 1, 0, 0, 0, 1], translation: [0, 0, 0] };
  const timestamp = 1792230743487.6013;
  const domain = 'timestamp_domain.global_time';
  const sample = {
    id, width, height, intrinsics: { fx: 36, fy: 36, cx: width / 2, cy: height / 2 },
    depth_m: Array(width * height).fill(2.2), points: [],
    metadata: {
      serial: 'SYNTHETIC_TEST_NO_DEVICE', capture_id: id, frame_id: 'realsense_ir1_optical',
      frame_id_source: 'sdk_logical_optical_not_ros_tf', profile_id: 'f'.repeat(64),
      rectified: true, synthetic: false, depth_semantics: 'optical_z', click_image_file: 'click.png',
      rectification_basis: 'actual_zero_distortion_intrinsics_and_identity_depth_to_ir1_no_resampling',
      source_timestamp: timestamp / 1000, source_timestamp_unit: 'seconds', source_timestamp_stream: 'ir1',
      clock_domain: domain, timestamp_domain: domain,
      source_timestamps_ms: { ir1: timestamp, depth: timestamp }, frame_numbers: { ir1: 55, depth: 56 },
      synchronization: { frameset_verified: true, source_skew_ms: 0, max_source_skew_ms: 1 },
      alignment: { method: 'verified_identity_depth_to_ir1_no_resampling', depth_to_ir1: extrinsics,
        ir1_intrinsics: { ...intrinsics }, depth_intrinsics: { ...intrinsics },
        intrinsics_relative_tolerance: 1e-9, extrinsics_absolute_tolerance: 1e-8 },
    },
  };
  const png = syntheticGrayscalePng(width, height);
  const manifest = {
    schema: 'robot-scope.depth-capture.v1', sample_id: id, session_id: 'c'.repeat(32), generation: 1,
    captured_at_utc: '2026-10-17T09:52:23.508534+00:00', synthetic: false,
    compatibility: { available: true, reason: null }, valid_depth_ratio: 1, actual_source_skew_ms: 0,
    image: { available: true, width, height, frame_id: sample.metadata.frame_id,
      frame_id_source: sample.metadata.frame_id_source, timestamp_ms: timestamp, timestamp_domain: domain, frame_number: 55 },
    files: {}, total_bytes: 0,
  };
  const rebuild = () => {
    const json = Buffer.from(JSON.stringify(sample));
    manifest.files['compatibility.json'] = artifact(json);
    manifest.files['click.png'] = artifact(png);
    manifest.total_bytes = json.length + png.length;
    return { json, png };
  };
  const body = rebuild();
  return { sample, manifest, body, rebuild };
}

export function artifact(body) {
  return { bytes: body.length, sha256: createHash('sha256').update(body).digest('hex') };
}

export function artifactHeaders(file, mime) {
  return { 'Content-Type': mime, 'X-Robot-Scope-Artifact-SHA256': file.sha256,
    'X-Robot-Scope-Artifact-Bytes': String(file.bytes), 'Cache-Control': 'no-store' };
}

function syntheticGrayscalePng(width, height) {
  const crc32 = (data) => {
    let crc = 0xffffffff;
    for (const byte of data) {
      crc ^= byte;
      for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
    return (crc ^ 0xffffffff) >>> 0;
  };
  const chunk = (kind, data) => {
    const head = Buffer.alloc(4); head.writeUInt32BE(data.length);
    const content = Buffer.concat([Buffer.from(kind), data]);
    const checksum = Buffer.alloc(4); checksum.writeUInt32BE(crc32(content));
    return Buffer.concat([head, content, checksum]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8;
  const rows = Buffer.alloc((width + 1) * height);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) rows[y * (width + 1) + x + 1] = 32 + ((x + y) % 160);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', deflateSync(rows)), chunk('IEND', Buffer.alloc(0))]);
}
