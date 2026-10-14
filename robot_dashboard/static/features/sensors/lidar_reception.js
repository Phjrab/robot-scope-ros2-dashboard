export function overviewLidarReception(state, topics = []) {
  const selected = state.sources?.pointcloud;
  if (!selected) return { live: false };
  // mapping.cloud meters the selected ROS subscription even when no browser
  // requests binary render frames. An old canvas or cached Hz is not liveness.
  const cloud = state.cloud || {};
  const metric = (!cloud.topic || cloud.topic === selected) ? state.mapping?.cloud : null;
  const topic = topics.find((entry) => entry.name === selected);
  const observation = metric?.state ? metric : topic;
  const age = Number(observation?.age_s);
  const live = observation?.state === 'ok' && observation?.age_s != null
    && Number.isFinite(age) && age >= 0 && age <= 5;
  return { live, hz: live ? observation.hz : null };
}

