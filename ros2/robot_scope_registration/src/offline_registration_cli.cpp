#include "robot_scope_registration/registration_core.hpp"

#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

namespace rsr = robot_scope_registration;

namespace {

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
    const auto reference = rsr::load_binary_xyz_pcd(argv[1], max_reference);
    const auto query = rsr::load_binary_xyz_pcd(argv[2], max_query);
    const rsr::Pose3DoF seed{number(argv[3]), number(argv[4]), number(argv[5])};
    const auto result = rsr::register_clouds(
        reference, query, seed, number(argv[6]), number(argv[7]), options);
    std::cout << std::setprecision(12)
              << "{\"schema\":\"robot-scope.relocalization-result.v1\","
              << "\"backend\":\"bounded-se2-icp\",\"results\":[";
    for (std::size_t index = 0; index < result.candidates.size(); ++index) {
      if (index) std::cout << ',';
      const auto& candidate = result.candidates[index];
      double margin = 1.0;
      if (index == 0 && result.candidates.size() > 1) {
        const double next = result.candidates[1].fitness;
        margin = std::isfinite(next) && next > 1e-12
                     ? std::max(0.0, (next - candidate.fitness) / next)
                     : 0.0;
      } else if (index > 0) {
        margin = 0.0;
      }
      std::cout << "{\"converged\":" << (candidate.converged ? "true" : "false")
                << ",\"pose\":{\"x\":" << candidate.pose.x
                << ",\"y\":" << candidate.pose.y
                << ",\"yaw\":" << candidate.pose.yaw << "},"
                << "\"metrics\":{\"fitness\":" << candidate.fitness
                << ",\"overlap_ratio\":" << candidate.overlap_ratio
                << ",\"inlier_ratio\":" << candidate.inlier_ratio
                << ",\"query_points\":" << candidate.query_points
                << ",\"reference_points\":" << candidate.reference_points
                << ",\"runtime_ms\":"
                << (result.preprocess_us + result.coarse_us + result.refine_us) / 1000.0
                << "},\"confidence\":\"" << confidence(candidate, margin)
                << "\",\"rank\":" << (index + 1)
                << ",\"ambiguity_margin\":" << margin << '}';
    }
    std::cout << "],\"timing\":{\"preprocess_ms\":" << result.preprocess_us / 1000.0
              << ",\"coarse_ms\":" << result.coarse_us / 1000.0
              << ",\"refine_ms\":" << result.refine_us / 1000.0 << "}}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
