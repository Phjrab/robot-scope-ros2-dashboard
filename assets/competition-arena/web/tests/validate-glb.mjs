import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import * as THREE from '../vendor/three/three.module.js';
import { GLTFLoader } from '../vendor/three/addons/loaders/GLTFLoader.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const bytes = await fs.readFile(path.join(root, 'arena.glb'));
const metadata = JSON.parse(await fs.readFile(path.join(root, 'arena.json'), 'utf8'));
assert.equal(bytes.subarray(0, 4).toString(), 'glTF');
assert.equal(bytes.readUInt32LE(4), 2);
assert.equal(bytes.readUInt32LE(8), bytes.length);
const jsonChunkLength = bytes.readUInt32LE(12);
const gltfJSON = JSON.parse(bytes.subarray(20, 20 + jsonChunkLength).toString());
assert.equal(gltfJSON.asset.version, '2.0');
assert(!(gltfJSON.buffers ?? []).some((buffer) => buffer.uri && !buffer.uri.startsWith('data:')), 'All geometry must be embedded');
assert(!(gltfJSON.images ?? []).some((image) => image.uri && !image.uri.startsWith('data:')), 'All textures must be embedded');
const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(arrayBuffer, '', resolve, reject));
gltf.scene.updateMatrixWorld(true);
const meshes = [];
let triangles = 0;
const totalBounds = new THREE.Box3();
const categories = {};
gltf.scene.traverse((object) => {
  if (!object.isMesh) return;
  assert(object.geometry.getAttribute('position'), `${object.name} must contain vertex positions`);
  const box = new THREE.Box3().setFromObject(object);
  for (const value of [...box.min.toArray(), ...box.max.toArray()]) assert(Number.isFinite(value), 'Mesh coordinates must be finite');
  totalBounds.union(box);
  triangles += (object.geometry.index?.count ?? object.geometry.getAttribute('position').count) / 3;
  meshes.push(object.name);
  const prefix = object.name.split('_')[0];
  categories[prefix] = (categories[prefix] ?? 0) + 1;
});
assert(meshes.length > 0);
for (const prefix of ['floor', 'wall', 'ramp', 'stair', 'label']) assert(categories[prefix] > 0, `${prefix} meshes must exist`);
assert(Array.isArray(metadata.dimensions) && metadata.dimensions.length > 0);
assert(Array.isArray(metadata.assumptions) && metadata.assumptions.length > 0);
assert(Array.isArray(metadata.objects) && metadata.objects.length > 0);
assert(['metre', 'meter', 'meters', 'metres', 'm'].includes(metadata.coordinate_system.unit));
for (const object of metadata.objects) {
  assert(object.status && object.source && object.uncertainty, `${object.name} must document evidence and uncertainty`);
  assert(meshes.includes(object.name), `Metadata object ${object.name} must exist in GLB`);
}
// A source (x,y,z) maps to glTF (x,z,-y); inspect model-space bounds against metadata.
const byName = new Map(); gltf.scene.traverse((object) => { if (object.isMesh) byName.set(object.name, object); });
let coordinateChecks = 0;
for (const object of metadata.objects) {
  if (!object.bbox_m?.min || !object.bbox_m?.max) continue;
  const sourceMin = object.bbox_m.min;
  const sourceMax = object.bbox_m.max;
  const expectedMin = [sourceMin[0], sourceMin[2], -sourceMax[1]];
  const expectedMax = [sourceMax[0], sourceMax[2], -sourceMin[1]];
  const box = new THREE.Box3().setFromObject(byName.get(object.name));
  const actual = [...box.min.toArray(), ...box.max.toArray()];
  const expected = [...expectedMin, ...expectedMax];
  for (let index = 0; index < 6; index++) assert(Math.abs(actual[index] - expected[index]) < 0.002, `${object.name} axis/bbox mismatch at ${index}: ${actual[index]} vs ${expected[index]}`);
  coordinateChecks++;
}
assert(coordinateChecks > 0, 'At least one metadata bbox must verify the axis convention');
const requiredPaths = ['web/vendor/three/three.module.js', 'web/vendor/three/three.core.js', 'web/vendor/three/addons/loaders/GLTFLoader.js', 'web/vendor/three/addons/controls/OrbitControls.js', 'web/vendor/three/addons/utils/BufferGeometryUtils.js', 'web/vendor/three/LICENSE'];
for (const dependency of requiredPaths) assert((await fs.stat(path.join(root, dependency))).size > 0);
const index = await fs.readFile(path.join(root, 'web/index.html'), 'utf8');
const app = await fs.readFile(path.join(root, 'web/app.js'), 'utf8');
assert(!/https?:\/\//.test(index), 'HTML must use local assets only');
assert(!/https?:\/\//.test(app), 'Application must not use external endpoints');
const report = {
  passed: true,
  validationKind: 'Actual GLTFLoader parsing and static integration; no browser runtime or GPU rendering claim',
  glbBytes: bytes.length,
  gltfVersion: gltfJSON.asset.version,
  threeRevision: THREE.REVISION,
  meshCount: meshes.length,
  triangles,
  categories,
  worldBoundsYUp: { min: totalBounds.min.toArray(), max: totalBounds.max.toArray() },
  metadataDimensions: metadata.dimensions.length,
  metadataAssumptions: metadata.assumptions.length,
  metadataObjects: metadata.objects.length,
  coordinateChecks,
  browserRuntime: 'NOT VERIFIED: sandbox Chromium socket permission error; approved execution retry failed due to sandbox setup read-only path error. No browser screenshot was produced.',
  checks: ['GLB header, version, and declared byte length', 'Embedded resources only', 'Actual vendored GLTFLoader parses every mesh', 'Finite vertex bounds and nonzero triangles', 'Expected named geometry classes', 'Every metadata object resolves to a GLB mesh', 'Per-object Z-up to Y-up bounding-box coordinate conversion', 'All dependencies locally present', 'No external asset URLs in application'],
};
await fs.mkdir(path.join(root, 'web-tests'), { recursive: true });
await fs.writeFile(path.join(root, 'web-tests/structural-validation.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
