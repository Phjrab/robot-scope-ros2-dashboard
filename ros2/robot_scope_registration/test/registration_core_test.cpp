#include "robot_scope_registration/registration_core.hpp"

#include <cmath>
#include <iostream>
#include <vector>

namespace rsr = robot_scope_registration;

namespace {

std::vector<rsr::Point3> room() {
  std::vector<rsr::Point3> cloud;
  for (int layer = 0; layer < 5; ++layer) {
    const double z = -0.4 + layer * 0.2;
    for (int step = 0; step <= 120; ++step) {
      const double value = -6.0 + step * 0.1;
      cloud.push_back({value, -4.0, z});
      cloud.push_back({value, 4.0, z});
      cloud.push_back({-6.0, value * 2.0 / 3.0, z});
      if (step < 80) cloud.push_back({6.0, -4.0 + step * 0.1, z});
    }
    for (int step = 0; step < 63; ++step) {
      const double angle = step * 0.1;
      cloud.push_back({2.1 + 0.35 * std::cos(angle), 1.2 + 0.35 * std::sin(angle), z});
    }
  }
  return cloud;
}

std::vector<rsr::Point3> inverse(const std::vector<rsr::Point3>& reference,
                                 const rsr::Pose3DoF& pose) {
  std::vector<rsr::Point3> query;
  query.reserve(reference.size());
  const double c = std::cos(pose.yaw);
  const double s = std::sin(pose.yaw);
  for (const auto& point : reference) {
    const double x = point.x - pose.x;
    const double y = point.y - pose.y;
    query.push_back({c * x + s * y, -s * x + c * y, point.z});
  }
  return query;
}

double yaw_error(double left, double right) {
  return std::abs(std::atan2(std::sin(left - right), std::cos(left - right)));
}

}  // namespace

int main() {
  const rsr::Pose3DoF truth{0.40, -0.30, 0.20};
  rsr::RegistrationOptions options;
  options.reference_voxel_m = 0.12;
  options.query_voxel_m = 0.12;
  options.minimum_query_points = 300;
  options.correspondence_m = 0.65;
  const auto result = rsr::register_clouds(room(), inverse(room(), truth),
                                            {0.0, 0.0, 0.0}, 0.8, 0.5, options);
  if (result.candidates.empty()) {
    std::cerr << "no registration candidate\n";
    return 1;
  }
  const auto& best = result.candidates.front();
  if (!best.converged || std::hypot(best.pose.x - truth.x, best.pose.y - truth.y) > 0.15 ||
      yaw_error(best.pose.yaw, truth.yaw) > 0.08 || best.overlap_ratio < 0.70) {
    std::cerr << "registration error " << best.pose.x << ' ' << best.pose.y << ' '
              << best.pose.yaw << ' ' << best.overlap_ratio << '\n';
    return 1;
  }
  bool rejected = false;
  try {
    auto too_small = room();
    too_small.resize(10);
    static_cast<void>(rsr::register_clouds(room(), too_small, {0.0, 0.0, 0.0},
                                           0.8, 0.5, options));
  } catch (const std::runtime_error&) {
    rejected = true;
  }
  if (!rejected) {
    std::cerr << "small cloud was accepted\n";
    return 1;
  }
  return 0;
}
