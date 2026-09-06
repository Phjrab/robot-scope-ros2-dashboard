#include "robot_scope_registration/registration_core.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <unordered_map>

namespace robot_scope_registration {
namespace {

constexpr double kPi = 3.14159265358979323846;

double normalize_yaw(double value) {
  while (value > kPi) value -= 2.0 * kPi;
  while (value < -kPi) value += 2.0 * kPi;
  return value;
}

bool finite(const Point3& point) {
  return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z);
}

struct Cell {
  long long x;
  long long y;
  long long z;
  bool operator==(const Cell& other) const {
    return x == other.x && y == other.y && z == other.z;
  }
};

struct CellHash {
  std::size_t operator()(const Cell& cell) const {
    std::size_t value = std::hash<long long>{}(cell.x);
    value ^= std::hash<long long>{}(cell.y) + 0x9e3779b9U + (value << 6U) + (value >> 2U);
    value ^= std::hash<long long>{}(cell.z) + 0x9e3779b9U + (value << 6U) + (value >> 2U);
    return value;
  }
};

Cell cell_for(const Point3& point, double size) {
  return {static_cast<long long>(std::floor(point.x / size)),
          static_cast<long long>(std::floor(point.y / size)),
          static_cast<long long>(std::floor(point.z / size))};
}

Point3 transform(const Point3& point, const Pose3DoF& pose) {
  const double c = std::cos(pose.yaw);
  const double s = std::sin(pose.yaw);
  return {c * point.x - s * point.y + pose.x,
          s * point.x + c * point.y + pose.y,
          point.z};
}

Pose3DoF compose(const Pose3DoF& delta, const Pose3DoF& current) {
  const double c = std::cos(delta.yaw);
  const double s = std::sin(delta.yaw);
  return {c * current.x - s * current.y + delta.x,
          s * current.x + c * current.y + delta.y,
          normalize_yaw(delta.yaw + current.yaw)};
}

class SpatialIndex {
 public:
  explicit SpatialIndex(const std::vector<Point3>& points, double cell_size)
      : points_(points), cell_size_(cell_size) {
    for (std::size_t index = 0; index < points_.size(); ++index) {
      cells_[cell_for(points_[index], cell_size_)].push_back(index);
    }
  }

  bool nearest(const Point3& query, double maximum_distance, Point3* match,
               double* squared_distance) const {
    const Cell center = cell_for(query, cell_size_);
    const int reach = static_cast<int>(std::ceil(maximum_distance / cell_size_));
    double best = maximum_distance * maximum_distance;
    bool found = false;
    for (int dx = -reach; dx <= reach; ++dx) {
      for (int dy = -reach; dy <= reach; ++dy) {
        for (int dz = -1; dz <= 1; ++dz) {
          const auto found_cell = cells_.find({center.x + dx, center.y + dy, center.z + dz});
          if (found_cell == cells_.end()) continue;
          for (const std::size_t index : found_cell->second) {
            const Point3& candidate = points_[index];
            const double x = candidate.x - query.x;
            const double y = candidate.y - query.y;
            const double z = candidate.z - query.z;
            const double distance = x * x + y * y + z * z;
            if (distance <= best) {
              best = distance;
              *match = candidate;
              found = true;
            }
          }
        }
      }
    }
    if (found) *squared_distance = best;
    return found;
  }

 private:
  const std::vector<Point3>& points_;
  double cell_size_;
  std::unordered_map<Cell, std::vector<std::size_t>, CellHash> cells_;
};

RegistrationCandidate evaluate(const SpatialIndex& index,
                               const std::vector<Point3>& reference,
                               const std::vector<Point3>& query,
                               const Pose3DoF& pose,
                               double correspondence_m) {
  double error = 0.0;
  std::size_t inliers = 0;
  const std::size_t stride = std::max<std::size_t>(1, query.size() / 4000);
  std::size_t evaluated = 0;
  for (std::size_t offset = 0; offset < query.size(); offset += stride) {
    Point3 match{};
    double squared = 0.0;
    ++evaluated;
    if (index.nearest(transform(query[offset], pose), correspondence_m, &match, &squared)) {
      error += squared;
      ++inliers;
    }
  }
  const double overlap = evaluated == 0 ? 0.0 : static_cast<double>(inliers) / evaluated;
  return {pose,
          inliers == 0 ? std::numeric_limits<double>::infinity() : error / inliers,
          overlap,
          overlap,
          query.size(),
          reference.size(),
          false};
}

RegistrationCandidate refine(const SpatialIndex& index,
                             const std::vector<Point3>& reference,
                             const std::vector<Point3>& query,
                             Pose3DoF pose,
                             const RegistrationOptions& options) {
  bool converged = false;
  for (std::size_t iteration = 0; iteration < options.maximum_iterations; ++iteration) {
    std::vector<std::pair<Point3, Point3>> pairs;
    pairs.reserve(query.size());
    const std::size_t stride = std::max<std::size_t>(1, query.size() / 12000);
    for (std::size_t offset = 0; offset < query.size(); offset += stride) {
      const Point3 moved = transform(query[offset], pose);
      Point3 match{};
      double squared = 0.0;
      if (index.nearest(moved, options.correspondence_m, &match, &squared)) {
        pairs.push_back({moved, match});
      }
    }
    if (pairs.size() < 20) break;
    Point3 from_center{0.0, 0.0, 0.0};
    Point3 to_center{0.0, 0.0, 0.0};
    for (const auto& pair : pairs) {
      from_center.x += pair.first.x;
      from_center.y += pair.first.y;
      to_center.x += pair.second.x;
      to_center.y += pair.second.y;
    }
    const double count = static_cast<double>(pairs.size());
    from_center.x /= count;
    from_center.y /= count;
    to_center.x /= count;
    to_center.y /= count;
    double cross = 0.0;
    double dot = 0.0;
    for (const auto& pair : pairs) {
      const double fx = pair.first.x - from_center.x;
      const double fy = pair.first.y - from_center.y;
      const double tx = pair.second.x - to_center.x;
      const double ty = pair.second.y - to_center.y;
      cross += fx * ty - fy * tx;
      dot += fx * tx + fy * ty;
    }
    const double angle = std::atan2(cross, dot);
    const double c = std::cos(angle);
    const double s = std::sin(angle);
    Pose3DoF delta{to_center.x - (c * from_center.x - s * from_center.y),
                   to_center.y - (s * from_center.x + c * from_center.y), angle};
    pose = compose(delta, pose);
    if (std::hypot(delta.x, delta.y) < 1e-4 && std::abs(delta.yaw) < 1e-4) {
      converged = true;
      break;
    }
  }
  RegistrationCandidate result = evaluate(
      index, reference, query, pose, options.correspondence_m);
  result.converged = converged && result.overlap_ratio >= 0.20 && std::isfinite(result.fitness);
  return result;
}

void require_options(const RegistrationOptions& options, double radius, double yaw_range) {
  if (!std::isfinite(radius) || radius < 0.0 || radius > 10.0 ||
      !std::isfinite(yaw_range) || yaw_range < 0.0 || yaw_range > kPi ||
      options.maximum_coarse_candidates == 0 || options.maximum_coarse_candidates > 128 ||
      options.maximum_refinements == 0 || options.maximum_refinements > 8 ||
      options.maximum_results == 0 || options.maximum_results > 3 ||
      options.maximum_iterations == 0 || options.maximum_iterations > 100 ||
      options.correspondence_m <= 0.0 || options.correspondence_m > 3.0) {
    throw std::invalid_argument("registration options are outside fixed bounds");
  }
}

}  // namespace

std::vector<Point3> preprocess_cloud(const std::vector<Point3>& input,
                                     double voxel_m,
                                     const RegistrationOptions& options,
                                     std::size_t maximum_points) {
  if (!std::isfinite(voxel_m) || voxel_m < 0.05 || voxel_m > 1.0 || maximum_points == 0) {
    throw std::invalid_argument("preprocessing bounds are invalid");
  }
  std::unordered_map<Cell, Point3, CellHash> voxels;
  for (const Point3& point : input) {
    if (!finite(point)) continue;
    const double radius = std::hypot(point.x, point.y);
    if (radius < options.minimum_range_m || radius > options.maximum_range_m ||
        point.z < options.minimum_z_m || point.z > options.maximum_z_m ||
        radius < options.self_radius_m) continue;
    voxels.emplace(cell_for(point, voxel_m), point);
    if (voxels.size() > maximum_points) {
      throw std::runtime_error("point count exceeds preprocessing limit");
    }
  }
  std::vector<Point3> output;
  output.reserve(voxels.size());
  for (const auto& item : voxels) output.push_back(item.second);
  std::sort(output.begin(), output.end(), [](const Point3& left, const Point3& right) {
    return std::tie(left.x, left.y, left.z) < std::tie(right.x, right.y, right.z);
  });
  return output;
}

RegistrationResult register_clouds(const std::vector<Point3>& reference_input,
                                   const std::vector<Point3>& query_input,
                                   const Pose3DoF& seed,
                                   double translation_radius_m,
                                   double yaw_range_rad,
                                   const RegistrationOptions& options) {
  require_options(options, translation_radius_m, yaw_range_rad);
  if (!std::isfinite(seed.x) || !std::isfinite(seed.y) || !std::isfinite(seed.yaw)) {
    throw std::invalid_argument("seed is not finite");
  }
  const auto start = std::chrono::steady_clock::now();
  const auto reference = preprocess_cloud(reference_input, options.reference_voxel_m,
                                           options, options.maximum_reference_points);
  const auto query = preprocess_cloud(query_input, options.query_voxel_m,
                                       options, options.maximum_query_points);
  if (reference.size() < options.minimum_query_points ||
      query.size() < options.minimum_query_points) {
    throw std::runtime_error("too few points remain after preprocessing");
  }
  const auto preprocessed = std::chrono::steady_clock::now();
  const SpatialIndex index(reference, std::max(0.20, options.correspondence_m / 2.0));
  std::vector<RegistrationCandidate> coarse;
  const std::array<double, 5> factors{-1.0, -0.5, 0.0, 0.5, 1.0};
  for (double yaw_factor : factors) {
    for (double x_factor : factors) {
      for (double y_factor : factors) {
        if (coarse.size() >= options.maximum_coarse_candidates) break;
        const Pose3DoF pose{seed.x + x_factor * translation_radius_m,
                           seed.y + y_factor * translation_radius_m,
                           normalize_yaw(seed.yaw + yaw_factor * yaw_range_rad)};
        coarse.push_back(evaluate(index, reference, query, pose,
                                  options.correspondence_m * 1.5));
      }
    }
  }
  std::sort(coarse.begin(), coarse.end(), [](const auto& left, const auto& right) {
    if (left.overlap_ratio != right.overlap_ratio) return left.overlap_ratio > right.overlap_ratio;
    if (left.fitness != right.fitness) return left.fitness < right.fitness;
    return std::tie(left.pose.x, left.pose.y, left.pose.yaw) <
           std::tie(right.pose.x, right.pose.y, right.pose.yaw);
  });
  const auto coarse_done = std::chrono::steady_clock::now();
  std::vector<RegistrationCandidate> refined;
  const std::size_t refinements = std::min(options.maximum_refinements, coarse.size());
  for (std::size_t index_value = 0; index_value < refinements; ++index_value) {
    refined.push_back(refine(index, reference, query, coarse[index_value].pose, options));
  }
  std::sort(refined.begin(), refined.end(), [](const auto& left, const auto& right) {
    if (left.overlap_ratio != right.overlap_ratio) return left.overlap_ratio > right.overlap_ratio;
    if (left.fitness != right.fitness) return left.fitness < right.fitness;
    return std::tie(left.pose.x, left.pose.y, left.pose.yaw) <
           std::tie(right.pose.x, right.pose.y, right.pose.yaw);
  });
  if (refined.size() > options.maximum_results) refined.resize(options.maximum_results);
  const auto refined_done = std::chrono::steady_clock::now();
  return {refined,
          static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(preprocessed - start).count()),
          static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(coarse_done - preprocessed).count()),
          static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(refined_done - coarse_done).count())};
}

std::vector<Point3> load_binary_xyz_pcd(const std::string& path,
                                        std::size_t maximum_points) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open PCD");
  std::string line;
  std::vector<std::string> fields;
  std::vector<int> sizes;
  std::vector<int> counts;
  std::vector<char> types;
  std::size_t points = 0;
  bool binary = false;
  std::size_t header_bytes = 0;
  while (std::getline(stream, line)) {
    header_bytes += line.size() + 1;
    if (header_bytes > 65536) throw std::runtime_error("PCD header is oversized");
    std::istringstream row(line);
    std::string key;
    row >> key;
    if (key == "FIELDS") {
      std::string value;
      while (row >> value) fields.push_back(value);
    } else if (key == "SIZE") {
      int value;
      while (row >> value) sizes.push_back(value);
    } else if (key == "TYPE") {
      char value;
      while (row >> value) types.push_back(value);
    } else if (key == "COUNT") {
      int value;
      while (row >> value) counts.push_back(value);
    } else if (key == "POINTS") {
      row >> points;
    } else if (key == "DATA") {
      std::string kind;
      row >> kind;
      binary = kind == "binary";
      break;
    }
  }
  if (!binary || points == 0 || points > maximum_points || fields.size() != sizes.size() ||
      fields.size() != types.size() || fields.size() != counts.size()) {
    throw std::runtime_error("PCD contract is invalid");
  }
  std::size_t step = 0;
  std::array<std::size_t, 3> offsets{};
  std::array<bool, 3> found{};
  for (std::size_t index = 0; index < fields.size(); ++index) {
    if (sizes[index] <= 0 || sizes[index] > 8 || counts[index] != 1) {
      throw std::runtime_error("PCD field layout is invalid");
    }
    for (std::size_t axis = 0; axis < 3; ++axis) {
      const char* names[] = {"x", "y", "z"};
      if (fields[index] == names[axis]) {
        if (sizes[index] != 4 || types[index] != 'F') throw std::runtime_error("PCD XYZ must be float32");
        offsets[axis] = step;
        found[axis] = true;
      }
    }
    step += static_cast<std::size_t>(sizes[index]);
  }
  if (!found[0] || !found[1] || !found[2] || step == 0 || step > 256) {
    throw std::runtime_error("PCD XYZ fields are missing");
  }
  std::vector<unsigned char> payload(points * step);
  stream.read(reinterpret_cast<char*>(payload.data()), static_cast<std::streamsize>(payload.size()));
  if (stream.gcount() != static_cast<std::streamsize>(payload.size())) {
    throw std::runtime_error("PCD payload is truncated");
  }
  std::vector<Point3> output;
  output.reserve(points);
  for (std::size_t point = 0; point < points; ++point) {
    std::array<float, 3> xyz{};
    for (std::size_t axis = 0; axis < 3; ++axis) {
      std::memcpy(&xyz[axis], payload.data() + point * step + offsets[axis], sizeof(float));
    }
    output.push_back({xyz[0], xyz[1], xyz[2]});
  }
  return output;
}

}  // namespace robot_scope_registration
