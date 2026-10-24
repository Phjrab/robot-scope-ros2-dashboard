// Display-only lowstate joints. No claim of sensor-clock synchronization or
// a calibrated transform between FAST-LIO's IMU and the URDF base origin.
export const GO2_JOINT_NAMES = ['FR', 'FL', 'RR', 'RL'].flatMap(leg =>
  ['hip', 'thigh', 'calf'].map(joint => `${leg}_${joint}_joint`));

export class ObservedJoints {
  constructor(now = () => performance.now()) { this.now = now; this.input = null; }
  clear() { this.input = null; }
  ingest(value) {
    if (value?.state !== 'ok' || value.topic !== '/lowstate'
        || value.source_order !== 'unitree_lowstate' || !Number.isSafeInteger(value.seq) || value.seq < 0
        || !Number.isFinite(value.age_s) || value.age_s < 0 || value.age_s > 1.2
        || !Array.isArray(value.order) || value.order.length !== 12 || new Set(value.order).size !== 12
        || GO2_JOINT_NAMES.some(name => !value.order.includes(name))
        || !Array.isArray(value.position_rad) || value.position_rad.length !== 12
        || !value.position_rad.every(Number.isFinite)) { this.clear(); return; }
    // Repeated snapshots do not renew freshness. A reconnect may reset seq;
    // use its new receipt as a new display sample, never interpolate epochs.
    if (this.input?.seq === value.seq || this.input && value.seq < this.input.seq && this.snapshot()) return;
    this.input = { seq: value.seq, arrived: this.now(), age_ms: value.age_s * 1000,
      positions: Object.fromEntries(value.order.map((name, i) => [name, value.position_rad[i]])) };
  }
  snapshot() {
    if (!this.input) return null;
    const age = this.input.age_ms + this.now() - this.input.arrived;
    return age >= 0 && age <= 1200 ? { ...this.input, age_ms: age, expires_at: this.now() + 1200 - age } : null;
  }
}
