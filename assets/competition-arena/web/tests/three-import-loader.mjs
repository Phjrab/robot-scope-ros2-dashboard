// Node-only import map equivalent for validating the same vendored GLTFLoader.
export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'three') return { url: new URL('../vendor/three/three.module.js', import.meta.url).href, shortCircuit: true };
  return nextResolve(specifier, context);
}
