// Camera preferences only: never a robot pose or navigation command.
export function validCameraState(value) {
  if (!value || !Array.isArray(value.target) || value.target.length !== 3
    || !value.target.every((n) => Number.isFinite(n) && Math.abs(n) <= 1e6)
    || !Number.isFinite(value.distance) || value.distance < 0.05 || value.distance > 2000
    || !Number.isFinite(value.yaw) || Math.abs(value.yaw) > 1e6
    || !Number.isFinite(value.pitch) || value.pitch < -82 * Math.PI / 180 || value.pitch > 88 * Math.PI / 180
    || !['follow', 'world'].includes(value.mode)) return null;
  return { target: value.target.slice(), distance: value.distance, yaw: value.yaw, pitch: value.pitch, mode: value.mode };
}

export function cameraPreferences(storage) {
  const memory = new Map();
  const key = (scope) => `robot-scope.cockpit.camera.v1:${scope}`;
  return {
    load(scope) {
      if (memory.has(scope)) return validCameraState(memory.get(scope));
      try { return validCameraState(JSON.parse(storage?.getItem(key(scope)) || 'null')); } catch { return null; }
    },
    save(scope, value) {
      const valid = validCameraState(value); if (!valid) return;
      memory.set(scope, valid);
      try { storage?.setItem(key(scope), JSON.stringify(valid)); } catch { /* In-memory route restoration still works. */ }
    },
  };
}
