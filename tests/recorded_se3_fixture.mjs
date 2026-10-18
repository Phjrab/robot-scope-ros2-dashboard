// Synthetic browser/unit fixture only. No private sensor data.
export function recordedFixture() {
  const identity = [[1, 0, 0, .4], [0, 1, 0, .2], [0, 0, 1, .1], [0, 0, 0, 1]];
  const points = Array.from({ length: 120 }, (_, i) => [Math.floor(i / 12) * .2, i % 12 * .2, (i % 3) * .2]);
  const metric = { reference_points: 120, query_points: 120, correspondence_gate_m: .75,
    overlap_ratio: 1, rmse_m: .086, direction: 'query_to_reference' };
  return {
    schema: 'robot-scope.recorded-se3-view.v1', data_kind: 'SYNTHETIC_FIXTURE', diagnostic_only: true,
    operational_application: 'NOT_RUN', live_verification: 'NOT_RUN', absolute_accuracy_m: null, qualification: 'BLOCKED',
    generated_at: new Date().toISOString(), captured_at: new Date().toISOString(), source_commit: 'a'.repeat(40),
    target: { frame_id: 'camera_init', session_id: 'map-session', sha256: 'b'.repeat(64), original_count: 120, points },
    source: { frame_id: 'camera_init', session_id: 'query-session', sha256: 'c'.repeat(64), original_count: 120,
      points: points.map(([x, y, z]) => [x - .4, y - .2, z - .1]), stamp_ns: '1792309179130175352', clock_domain: 'ROS_SYSTEM_TIME_UNVERIFIED', point_semantics: 'REGISTERED_QUERY' },
    result: { status: 'REJECTED', reason: 'HIGH_RESIDUAL', converged: true, iterations: 23,
      T_target_source: identity, geometry_min_max_eigen_ratio: .03,
      solver_metrics: metric, full_reference_metrics: { ...metric, rmse_m: .03 } },
    body_relation: null,
    trajectory: { frame_id: 'camera_init', session_id: 'query-session', estimand: 'synthetic sensor odometry', points: [[0, 0, 0], [.01, 0, 0]] },
  };
}
