#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace robot_scope_registration {

struct Point3 {
  double x;
  double y;
  double z;
};

struct Pose3DoF {
  double x;
  double y;
  double yaw;
};

struct RegistrationOptions {
  double reference_voxel_m{0.20};
  double query_voxel_m{0.15};
  double minimum_range_m{0.50};
  double maximum_range_m{20.0};
  double minimum_z_m{-2.0};
  double maximum_z_m{3.0};
  double self_radius_m{0.35};
  double correspondence_m{0.75};
  std::size_t minimum_query_points{500};
  std::size_t maximum_reference_points{1000000};
  std::size_t maximum_query_points{150000};
  std::size_t maximum_coarse_candidates{128};
  std::size_t maximum_refinements{8};
  std::size_t maximum_results{3};
  std::size_t maximum_iterations{30};
};

struct RegistrationCandidate {
  Pose3DoF pose;
  double fitness;
  double overlap_ratio;
  double inlier_ratio;
  std::size_t query_points;
  std::size_t reference_points;
  bool converged;
};

struct RegistrationResult {
  std::vector<RegistrationCandidate> candidates;
  std::uint64_t preprocess_us{0};
  std::uint64_t coarse_us{0};
  std::uint64_t refine_us{0};
};

std::vector<Point3> preprocess_cloud(
    const std::vector<Point3>& input,
    double voxel_m,
    const RegistrationOptions& options,
    std::size_t maximum_points);

RegistrationResult register_clouds(
    const std::vector<Point3>& reference,
    const std::vector<Point3>& query,
    const Pose3DoF& seed,
    double translation_radius_m,
    double yaw_range_rad,
    const RegistrationOptions& options = RegistrationOptions{});

std::vector<Point3> load_binary_xyz_pcd(
    const std::string& path,
    std::size_t maximum_points);

}  // namespace robot_scope_registration
