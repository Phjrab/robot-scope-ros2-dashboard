#include "robot_scope_registration/registration_core.hpp"

#include <pcl/common/transforms.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/registration/gicp.h>
#include <pcl/registration/ndt_2d.h>
#include <pcl/search/kdtree.h>

#include <Eigen/Geometry>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace rsr = robot_scope_registration;
namespace {

#if defined(ROBOT_SCOPE_PCL_BACKEND_NDT2D) == defined(ROBOT_SCOPE_PCL_BACKEND_GICP)
#error "exactly one fixed PCL backend must be selected"
#endif

using Cloud = pcl::PointCloud<pcl::PointXYZ>;
constexpr double kCorrespondenceM = 0.75;
constexpr double kMaximumZCorrectionM = 0.25;
constexpr double kMaximumTiltCorrectionRad = 0.15;
constexpr int kMaximumIterations = 30;

double number(const char* value) {
  std::size_t consumed = 0;
  const double parsed = std::stod(value, &consumed);
  if (consumed != std::string(value).size() || !std::isfinite(parsed)) {
    throw std::invalid_argument("argument is not finite");
  }
  return parsed;
}

std::size_t count(const char* value) {
  std::size_t consumed = 0;
  const unsigned long long parsed = std::stoull(value, &consumed);
  if (consumed != std::string(value).size() || parsed == 0) {
    throw std::invalid_argument("point limit is invalid");
  }
  return static_cast<std::size_t>(parsed);
}

Cloud::Ptr cloud_from(const std::vector<rsr::Point3>& source) {
  Cloud::Ptr cloud(new Cloud);
  cloud->reserve(source.size());
  for (const auto& point : source) {
    cloud->push_back(pcl::PointXYZ(
        static_cast<float>(point.x), static_cast<float>(point.y),
        static_cast<float>(point.z)));
  }
  return cloud;
}

Eigen::Matrix4f initial_transform(const rsr::Pose3DoF& pose) {
  Eigen::Matrix4f transform = Eigen::Matrix4f::Identity();
  transform.block<3, 3>(0, 0) =
      Eigen::AngleAxisf(static_cast<float>(pose.yaw), Eigen::Vector3f::UnitZ())
          .toRotationMatrix();
  transform(0, 3) = static_cast<float>(pose.x);
  transform(1, 3) = static_cast<float>(pose.y);
  return transform;
}

Eigen::Matrix4f planar_transform(const Eigen::Matrix4f& transform) {
  const float yaw = std::atan2(transform(1, 0), transform(0, 0));
  Eigen::Matrix4f planar = Eigen::Matrix4f::Identity();
  planar.block<3, 3>(0, 0) =
      Eigen::AngleAxisf(yaw, Eigen::Vector3f::UnitZ()).toRotationMatrix();
  planar(0, 3) = transform(0, 3);
  planar(1, 3) = transform(1, 3);
  return planar;
}

bool out_of_plane_is_bounded(const Eigen::Matrix4f& transform) {
  if (!transform.allFinite()) return false;
  const Eigen::Vector3f angles = transform.block<3, 3>(0, 0).eulerAngles(0, 1, 2);
  return std::abs(transform(2, 3)) <= kMaximumZCorrectionM &&
         std::abs(angles.x()) <= kMaximumTiltCorrectionRad &&
         std::abs(angles.y()) <= kMaximumTiltCorrectionRad;
}

rsr::RegistrationCandidate evaluate(
    const Cloud::Ptr& reference, const Cloud::Ptr& query,
    const Eigen::Matrix4f& transform, bool converged) {
  Cloud moved;
  pcl::transformPointCloud(*query, moved, transform);
  pcl::search::KdTree<pcl::PointXYZ> tree;
  tree.setInputCloud(reference);
  std::vector<int> indices(1);
  std::vector<float> distances(1);
  std::size_t inliers = 0;
  double squared_error = 0.0;
  for (const auto& point : moved) {
    if (tree.nearestKSearch(point, 1, indices, distances) == 1 &&
        distances[0] <= kCorrespondenceM * kCorrespondenceM) {
      ++inliers;
      squared_error += distances[0];
    }
  }
  const double overlap = moved.empty()
                             ? 0.0
                             : static_cast<double>(inliers) / moved.size();
  const double fitness = inliers == 0
                             ? std::numeric_limits<double>::infinity()
                             : squared_error / inliers;
  const double yaw = std::atan2(transform(1, 0), transform(0, 0));
  return {{transform(0, 3), transform(1, 3), yaw}, fitness, overlap, overlap,
          query->size(), reference->size(),
          converged && overlap >= 0.20 && std::isfinite(fitness)};
}

rsr::RegistrationCandidate refine_candidate(
    const Cloud::Ptr& reference, const Cloud::Ptr& query,
    const rsr::Pose3DoF& initial_pose) {
  Cloud aligned;
  Eigen::Matrix4f final_transform = Eigen::Matrix4f::Identity();
  bool converged = false;
#if defined(ROBOT_SCOPE_PCL_BACKEND_NDT2D)
  pcl::NormalDistributionsTransform2D<pcl::PointXYZ, pcl::PointXYZ> registration;
  registration.setInputSource(query);
  registration.setInputTarget(reference);
  registration.setMaximumIterations(kMaximumIterations);
  registration.setTransformationEpsilon(1e-4);
  registration.setGridCentre(Eigen::Vector2f(0.0F, 0.0F));
  registration.setGridStep(Eigen::Vector2f(0.5F, 0.5F));
  registration.setGridExtent(Eigen::Vector2f(20.0F, 20.0F));
  registration.setOptimizationStepSize(Eigen::Vector3d(1.0, 1.0, 1.0));
  registration.align(aligned, initial_transform(initial_pose));
  final_transform = registration.getFinalTransformation();
  converged = registration.hasConverged();
#else
  pcl::GeneralizedIterativeClosestPoint<pcl::PointXYZ, pcl::PointXYZ> registration;
  registration.setInputSource(query);
  registration.setInputTarget(reference);
  registration.setMaximumIterations(kMaximumIterations);
  registration.setMaxCorrespondenceDistance(kCorrespondenceM);
  registration.setTransformationEpsilon(1e-6);
  registration.setEuclideanFitnessEpsilon(1e-6);
  registration.align(aligned, initial_transform(initial_pose));
  final_transform = registration.getFinalTransformation();
  converged = registration.hasConverged();
#endif
  if (!out_of_plane_is_bounded(final_transform)) {
    return evaluate(reference, query, initial_transform(initial_pose), false);
  }
  return evaluate(reference, query, planar_transform(final_transform), converged);
}

const char* backend() {
#if defined(ROBOT_SCOPE_PCL_BACKEND_NDT2D)
  return "pcl-ndt2d";
#else
  return "pcl-gicp";
#endif
}

const char* confidence(const rsr::RegistrationCandidate& candidate,
                       double ambiguity_margin) {
  if (!candidate.converged || candidate.query_points < 500 ||
      candidate.overlap_ratio < 0.30 || candidate.fitness > 0.16) {
    return "REJECTED";
  }
  if (candidate.overlap_ratio >= 0.70 && candidate.fitness <= 0.04 &&
      ambiguity_margin >= 0.15) {
    return "HIGH";
  }
  if (candidate.overlap_ratio >= 0.50 && candidate.fitness <= 0.09 &&
      ambiguity_margin >= 0.05) {
    return "MEDIUM";
  }
  return "LOW";
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 11) {
    std::cerr << "fixed arguments required\n";
    return 2;
  }
  try {
    const std::size_t max_reference = count(argv[8]);
    const std::size_t max_query = count(argv[9]);
    const std::uint64_t timeout_ms = count(argv[10]);
    if (max_reference > 1000000 || max_query > 150000 || timeout_ms > 15000) {
      throw std::invalid_argument("limits exceed the fixed ceiling");
    }
    rsr::RegistrationOptions options;
    options.maximum_reference_points = max_reference;
    options.maximum_query_points = max_query;
    const auto reference_raw = rsr::load_binary_xyz_pcd(argv[1], max_reference);
    const auto query_raw = rsr::load_binary_xyz_pcd(argv[2], max_query);
    const rsr::Pose3DoF seed{number(argv[3]), number(argv[4]), number(argv[5])};
    const auto seeds = rsr::register_clouds(
        reference_raw, query_raw, seed, number(argv[6]), number(argv[7]), options);
    const auto pcl_preprocess_start = std::chrono::steady_clock::now();
    const auto reference = cloud_from(rsr::preprocess_cloud(
        reference_raw, options.reference_voxel_m, options, max_reference));
    const auto query = cloud_from(rsr::preprocess_cloud(
        query_raw, options.query_voxel_m, options, max_query));
    const auto refine_start = std::chrono::steady_clock::now();
    std::vector<rsr::RegistrationCandidate> candidates;
    candidates.reserve(seeds.candidates.size());
    for (const auto& candidate : seeds.candidates) {
      try {
        candidates.push_back(refine_candidate(reference, query, candidate.pose));
      } catch (const std::exception&) {
        candidates.push_back(evaluate(
            reference, query, initial_transform(candidate.pose), false));
      }
    }
    std::sort(candidates.begin(), candidates.end(), [](const auto& left, const auto& right) {
      if (left.overlap_ratio != right.overlap_ratio) {
        return left.overlap_ratio > right.overlap_ratio;
      }
      if (left.fitness != right.fitness) return left.fitness < right.fitness;
      return std::tie(left.pose.x, left.pose.y, left.pose.yaw) <
             std::tie(right.pose.x, right.pose.y, right.pose.yaw);
    });
    if (candidates.empty()) throw std::runtime_error("no bounded candidate available");
    const auto done = std::chrono::steady_clock::now();
    const double preprocess_ms = seeds.preprocess_us / 1000.0 +
        std::chrono::duration<double, std::milli>(
            refine_start - pcl_preprocess_start).count();
    const double coarse_ms = (seeds.coarse_us + seeds.refine_us) / 1000.0;
    const double refine_ms =
        std::chrono::duration<double, std::milli>(done - refine_start).count();
    const double total_ms = preprocess_ms + coarse_ms + refine_ms;
    std::cout << std::setprecision(12)
              << "{\"schema\":\"robot-scope.relocalization-result.v1\","
              << "\"backend\":\"" << backend() << "\",\"results\":[";
    for (std::size_t index = 0; index < candidates.size(); ++index) {
      if (index) std::cout << ',';
      const auto& candidate = candidates[index];
      double margin = 0.0;
      if (index == 0 && candidates.size() == 1) {
        margin = 1.0;
      } else if (index == 0) {
        const double next = candidates[1].fitness;
        margin = std::isfinite(next) && next > 1e-12
                     ? std::max(0.0, (next - candidate.fitness) / next)
                     : 0.0;
      }
      std::cout << "{\"converged\":"
                << (candidate.converged ? "true" : "false")
                << ",\"pose\":{\"x\":" << candidate.pose.x
                << ",\"y\":" << candidate.pose.y
                << ",\"yaw\":" << candidate.pose.yaw << "},"
                << "\"metrics\":{\"fitness\":" << candidate.fitness
                << ",\"overlap_ratio\":" << candidate.overlap_ratio
                << ",\"inlier_ratio\":" << candidate.inlier_ratio
                << ",\"query_points\":" << candidate.query_points
                << ",\"reference_points\":" << candidate.reference_points
                << ",\"runtime_ms\":" << total_ms << "},"
                << "\"confidence\":\"" << confidence(candidate, margin)
                << "\",\"rank\":" << (index + 1)
                << ",\"ambiguity_margin\":" << margin << '}';
    }
    std::cout << "],\"timing\":{\"preprocess_ms\":" << preprocess_ms
              << ",\"coarse_ms\":" << coarse_ms
              << ",\"refine_ms\":" << refine_ms << "}}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
