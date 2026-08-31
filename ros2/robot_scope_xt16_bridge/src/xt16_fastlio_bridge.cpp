#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <functional>
#include <initializer_list>
#include <limits>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
#include "sensor_msgs/msg/imu.hpp"
#endif
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "sensor_msgs/msg/point_field.hpp"
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
#include "unitree_go/msg/low_state.hpp"
#endif

namespace robot_scope_xt16_bridge
{

using sensor_msgs::msg::PointField;

constexpr char kRawTopic[] = "/lidar_points";
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
constexpr char kLowStateTopic[] = "/lowstate";
#endif
constexpr char kOutputCloudTopic[] = "/velodyne_points";
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
constexpr char kOutputImuTopic[] = "/imu/body";
#endif
constexpr char kLidarFrame[] = "hesai_lidar";
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
constexpr char kImuFrame[] = "body_imu";
#endif
#if defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
constexpr char kLoggerName[] = "robot_scope_xt16_cloud_bridge";
#else
constexpr char kLoggerName[] = "xt16_fastlio_bridge";
#endif

constexpr std::size_t kRawMinPoints = 4'000;
constexpr std::size_t kRawMaxPoints = 100'000;
constexpr std::size_t kOutputMinPoints = 1'000;
constexpr std::size_t kCloudDecimation = 4;
constexpr std::size_t kRawMinPointStep = 26;
constexpr std::size_t kOutputPointStep = 22;
constexpr double kMaxScanDurationS = 0.25;
constexpr double kClockOffsetRisePerScanS = 0.0001;
constexpr double kClockResidualLimitS = 0.25;
constexpr std::size_t kClockRelockRequiredSamples = 3;
constexpr double kClockRelockMaxSpreadS = 0.02;
constexpr double kClockStepMinDivergenceS = 0.10;
constexpr double kConvertedCloudMaxAgeS = 0.50;
constexpr double kConvertedCloudMaxFutureS = 0.05;
constexpr double kRawHeaderScanStartToleranceS = 0.01;

class ContractError : public std::runtime_error
{
public:
  using std::runtime_error::runtime_error;
};

struct Observation
{
  double instantaneous;
  double scan_end;
  double received;
  double monotonic;
};

class ClockOffsetTracker
{
public:
  builtin_interfaces::msg::Time stamp(
    double scan_start, double scan_end, double received, double monotonic)
  {
    if (!finite({scan_start, scan_end, received, monotonic})) {
      throw ContractError("cloud clocks must be finite");
    }
    if (scan_start <= 0.0 || scan_end < scan_start || received <= 0.0 || monotonic <= 0.0) {
      throw ContractError("cloud clocks are outside the supported range");
    }

    const double instantaneous = received - scan_end;
    if (!has_offset_) {
      calibrate_initial({instantaneous, scan_end, received, monotonic});
      throw ContractError("unreachable initial clock calibration state");
    }

    const double residual = instantaneous - offset_;
    const bool raw_not_progressing = has_last_observation_ && scan_end <= last_scan_end_;
    if (raw_not_progressing) {
      if (std::abs(residual) > kClockResidualLimitS) {
        reject_discontinuity(
          {instantaneous, scan_end, received, monotonic}, residual, true);
      }
      throw ContractError("raw cloud device timestamp did not increase; stale sample rejected");
    }
    if (std::abs(residual) > kClockResidualLimitS) {
      bool wall_step = false;
      if (has_last_observation_) {
        wall_step = std::abs(
          (received - last_received_) - (monotonic - last_monotonic_)) >=
          kClockStepMinDivergenceS;
      }
      reject_discontinuity(
        {instantaneous, scan_end, received, monotonic}, residual, wall_step);
    }
    relock_samples_.clear();

    const double candidate_offset = std::min(
      instantaneous, offset_ + kClockOffsetRisePerScanS);
    const double host_stamp = scan_start + candidate_offset;
    if (!std::isfinite(host_stamp) || host_stamp < 0.0) {
      throw ContractError("converted cloud stamp is outside the supported range");
    }
    const double host_age = received - host_stamp;
    if (host_age > kConvertedCloudMaxAgeS) {
      throw ContractError(
              "converted cloud age " + decimal(host_age) + "s exceeds " +
              decimal(kConvertedCloudMaxAgeS) + "s");
    }
    if (host_age < -kConvertedCloudMaxFutureS) {
      throw ContractError(
              "converted cloud future skew " + decimal(-host_age) + "s exceeds " +
              decimal(kConvertedCloudMaxFutureS) + "s");
    }
    if (has_last_published_stamp_ && host_stamp <= last_published_stamp_) {
      throw ContractError("converted cloud timestamp did not increase; stale sample rejected");
    }
    if (host_stamp > static_cast<double>(std::numeric_limits<std::int32_t>::max())) {
      throw ContractError("converted cloud stamp exceeds the ROS 2 time range");
    }

    offset_ = candidate_offset;
    last_published_stamp_ = host_stamp;
    has_last_published_stamp_ = true;
    remember({instantaneous, scan_end, received, monotonic});

    const double seconds_floor = std::floor(host_stamp);
    std::int64_t seconds = static_cast<std::int64_t>(seconds_floor);
    std::int64_t nanoseconds = static_cast<std::int64_t>(
      std::llround((host_stamp - seconds_floor) * 1'000'000'000.0));
    if (nanoseconds >= 1'000'000'000) {
      ++seconds;
      nanoseconds -= 1'000'000'000;
    }
    builtin_interfaces::msg::Time result;
    result.sec = static_cast<std::int32_t>(seconds);
    result.nanosec = static_cast<std::uint32_t>(nanoseconds);
    return result;
  }

private:
  static bool finite(std::initializer_list<double> values)
  {
    return std::all_of(values.begin(), values.end(), [](double value) {
      return std::isfinite(value);
    });
  }

  static std::string decimal(double value)
  {
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%.3f", value);
    return buffer;
  }

  static bool stable_window(
    const std::vector<Observation> & current, const Observation & candidate)
  {
    if (current.empty()) {
      return true;
    }
    const auto & previous = current.back();
    const double wall_delta = candidate.received - previous.received;
    const double monotonic_delta = candidate.monotonic - previous.monotonic;
    double minimum = candidate.instantaneous;
    double maximum = candidate.instantaneous;
    for (const auto & item : current) {
      minimum = std::min(minimum, item.instantaneous);
      maximum = std::max(maximum, item.instantaneous);
    }
    return candidate.scan_end > previous.scan_end && wall_delta > 0.0 &&
           monotonic_delta > 0.0 &&
           std::abs(wall_delta - monotonic_delta) < kClockStepMinDivergenceS &&
           maximum - minimum <= kClockRelockMaxSpreadS;
  }

  void remember(const Observation & observation)
  {
    last_scan_end_ = observation.scan_end;
    last_received_ = observation.received;
    last_monotonic_ = observation.monotonic;
    has_last_observation_ = true;
  }

  void calibrate_initial(const Observation & candidate)
  {
    if (!initial_samples_.empty() && stable_window(initial_samples_, candidate)) {
      initial_samples_.push_back(candidate);
    } else {
      initial_samples_.assign(1, candidate);
    }
    remember(candidate);
    const auto count = initial_samples_.size();
    if (count >= kClockRelockRequiredSamples) {
      offset_ = std::min_element(
        initial_samples_.begin(), initial_samples_.end(),
        [](const Observation & left, const Observation & right) {
          return left.instantaneous < right.instantaneous;
        })->instantaneous;
      has_offset_ = true;
      initial_samples_.clear();
      throw ContractError(
              "cloud clock initial calibration completed; calibration cloud rejected");
    }
    throw ContractError(
            "cloud clock initial calibration sample " + std::to_string(count) + "/" +
            std::to_string(kClockRelockRequiredSamples) + " rejected");
  }

  void reject_discontinuity(
    const Observation & candidate, double residual, bool relock_eligible)
  {
    if (!relock_eligible && relock_samples_.empty()) {
      throw ContractError(
              "cloud callback backlog residual " + decimal(residual) +
              "s exceeded " + decimal(kClockResidualLimitS) +
              "s; sample rejected without clock rebase");
    }

    if (!relock_samples_.empty()) {
      if (stable_window(relock_samples_, candidate)) {
        relock_samples_.push_back(candidate);
      } else if (relock_eligible) {
        relock_samples_.assign(1, candidate);
      } else {
        relock_samples_.clear();
      }
    } else if (relock_eligible) {
      relock_samples_.push_back(candidate);
    }

    const auto count = relock_samples_.size();
    if (count >= kClockRelockRequiredSamples) {
      offset_ = std::min_element(
        relock_samples_.begin(), relock_samples_.end(),
        [](const Observation & left, const Observation & right) {
          return left.instantaneous < right.instantaneous;
        })->instantaneous;
      has_offset_ = true;
      relock_samples_.clear();
      remember(candidate);
      throw ContractError(
              "cloud clock residual discontinuity " + decimal(residual) +
              "s exceeded " + decimal(kClockResidualLimitS) +
              "s; stable offset relocked and calibration cloud rejected");
    }
    throw ContractError(
            "cloud clock residual discontinuity " + decimal(residual) +
            "s exceeded " + decimal(kClockResidualLimitS) + "; relock sample " +
            std::to_string(count) + "/" +
            std::to_string(kClockRelockRequiredSamples) + " rejected");
  }

  bool has_offset_{false};
  double offset_{0.0};
  bool has_last_observation_{false};
  double last_scan_end_{0.0};
  double last_received_{0.0};
  double last_monotonic_{0.0};
  bool has_last_published_stamp_{false};
  double last_published_stamp_{0.0};
  std::vector<Observation> initial_samples_;
  std::vector<Observation> relock_samples_;
};

template<typename T>
T read_value(const std::vector<std::uint8_t> & data, std::size_t offset)
{
  T value{};
  std::memcpy(&value, data.data() + offset, sizeof(T));
  return value;
}

template<typename T>
void write_value(std::vector<std::uint8_t> & data, std::size_t offset, T value)
{
  std::memcpy(data.data() + offset, &value, sizeof(T));
}

void require_field(
  const sensor_msgs::msg::PointCloud2 & message, const char * name,
  std::uint32_t offset, std::uint8_t datatype)
{
  const auto item = std::find_if(
    message.fields.begin(), message.fields.end(),
    [name](const PointField & field) {return field.name == name;});
  if (item == message.fields.end() || item->offset != offset ||
    item->datatype != datatype || item->count != 1)
  {
    throw ContractError(std::string("raw cloud field ") + name + " has an incompatible layout");
  }
  if (std::count_if(
      message.fields.begin(), message.fields.end(),
      [name](const PointField & field) {return field.name == name;}) != 1)
  {
    throw ContractError(std::string("raw cloud field ") + name + " is duplicated");
  }
}

struct SelectedPoint
{
  float x;
  float y;
  float z;
  float intensity;
  std::uint16_t ring;
  double timestamp;
};

class Xt16FastlioBridge : public rclcpp::Node
{
public:
  Xt16FastlioBridge()
#if defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  : Node("robot_scope_xt16_cloud_bridge")
#else
  : Node("xt16_fastlio_bridge")
#endif
  {
    if (!native_little_endian()) {
      throw ContractError("XT16 bridge requires a little-endian host");
    }

    auto output_qos = rclcpp::QoS(rclcpp::KeepLast(5)).reliable().durability_volatile();
    auto raw_qos = rclcpp::QoS(rclcpp::KeepLast(1)).reliable().durability_volatile();
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    auto lowstate_qos = rclcpp::QoS(rclcpp::KeepLast(5)).best_effort().durability_volatile();
#endif

    cloud_publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(
      kOutputCloudTopic, output_qos);
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    imu_publisher_ = create_publisher<sensor_msgs::msg::Imu>(kOutputImuTopic, output_qos);
#endif

    cloud_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    imu_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
#endif
    rclcpp::SubscriptionOptions cloud_options;
    cloud_options.callback_group = cloud_group_;
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    rclcpp::SubscriptionOptions imu_options;
    imu_options.callback_group = imu_group_;
#endif
    cloud_subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      kRawTopic, raw_qos,
      std::bind(&Xt16FastlioBridge::on_cloud, this, std::placeholders::_1), cloud_options);
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    imu_subscription_ = create_subscription<unitree_go::msg::LowState>(
      kLowStateTopic, lowstate_qos,
      std::bind(&Xt16FastlioBridge::on_lowstate, this, std::placeholders::_1), imu_options);
#endif
    report_timer_ = create_wall_timer(
      std::chrono::seconds(5), std::bind(&Xt16FastlioBridge::report, this));
#if defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    RCLCPP_INFO(
      get_logger(),
      "fixed C++ XT16 cloud bridge ready: /lidar_points -> /velodyne_points");
#else
    RCLCPP_INFO(
      get_logger(),
      "fixed C++ XT16 bridge ready: /lidar_points -> /velodyne_points; "
      "/lowstate -> /imu/body");
#endif
  }

private:
  static bool native_little_endian()
  {
    const std::uint16_t value = 1;
    return *reinterpret_cast<const std::uint8_t *>(&value) == 1;
  }

  static double steady_seconds()
  {
    return std::chrono::duration<double>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }

  static double header_seconds(const builtin_interfaces::msg::Time & stamp)
  {
    if (stamp.sec < 0 || stamp.nanosec >= 1'000'000'000U) {
      throw ContractError("raw cloud header timestamp is outside the supported range");
    }
    const double result = static_cast<double>(stamp.sec) +
      static_cast<double>(stamp.nanosec) * 1e-9;
    if (result <= 0.0) {
      throw ContractError("raw cloud header timestamp must be positive");
    }
    return result;
  }

  void reject(const ContractError & error)
  {
    const auto count = reject_count_.fetch_add(1, std::memory_order_relaxed) + 1;
    if (count == 1 || count % 50 == 0) {
      RCLCPP_ERROR(get_logger(), "bridge rejected input: %s", error.what());
    }
  }

  void validate_cloud(const sensor_msgs::msg::PointCloud2 & message) const
  {
    if (message.header.frame_id != kLidarFrame) {
      throw ContractError("raw cloud frame must be hesai_lidar");
    }
    const std::uint64_t points =
      static_cast<std::uint64_t>(message.width) * static_cast<std::uint64_t>(message.height);
    if (message.height != 1 || points < kRawMinPoints || points > kRawMaxPoints) {
      throw ContractError("raw cloud must contain 4000..100000 points in one row");
    }
    if (message.point_step < kRawMinPointStep || message.is_bigendian) {
      throw ContractError("raw cloud byte layout is unsupported");
    }
    const std::uint64_t expected_row = points * message.point_step;
    if (message.row_step != expected_row || message.data.size() != expected_row) {
      throw ContractError("raw cloud payload length does not match its layout");
    }
    require_field(message, "x", 0, PointField::FLOAT32);
    require_field(message, "y", 4, PointField::FLOAT32);
    require_field(message, "z", 8, PointField::FLOAT32);
    require_field(message, "intensity", 12, PointField::FLOAT32);
    require_field(message, "ring", 16, PointField::UINT16);
    require_field(message, "timestamp", 18, PointField::FLOAT64);
  }

  sensor_msgs::msg::PointCloud2 convert_cloud(
    const sensor_msgs::msg::PointCloud2 & message, double received, double monotonic)
  {
    validate_cloud(message);
    const std::size_t points = static_cast<std::size_t>(message.width);
    std::vector<SelectedPoint> selected;
    selected.reserve((points + kCloudDecimation - 1) / kCloudDecimation);
    double scan_start = std::numeric_limits<double>::infinity();
    double scan_end = -std::numeric_limits<double>::infinity();
    for (std::size_t index = 0; index < points; index += kCloudDecimation) {
      const std::size_t base = index * message.point_step;
      SelectedPoint point{
        read_value<float>(message.data, base),
        read_value<float>(message.data, base + 4),
        read_value<float>(message.data, base + 8),
        read_value<float>(message.data, base + 12),
        read_value<std::uint16_t>(message.data, base + 16),
        read_value<double>(message.data, base + 18),
      };
      if (!std::isfinite(point.x) || !std::isfinite(point.y) ||
        !std::isfinite(point.z) || !std::isfinite(point.timestamp) ||
        point.timestamp <= 0.0)
      {
        continue;
      }
      scan_start = std::min(scan_start, point.timestamp);
      scan_end = std::max(scan_end, point.timestamp);
      selected.push_back(point);
    }
    if (selected.size() < kOutputMinPoints) {
      throw ContractError("too few finite decimated XT16 points remain");
    }
    const double duration = scan_end - scan_start;
    if (!std::isfinite(duration) || duration < 0.0 || duration > kMaxScanDurationS) {
      throw ContractError("XT16 scan duration is outside the supported range");
    }
    if (std::abs(header_seconds(message.header.stamp) - scan_start) >
      kRawHeaderScanStartToleranceS)
    {
      throw ContractError("raw cloud header does not match the device scan start");
    }

    sensor_msgs::msg::PointCloud2 output;
    output.header.stamp = clock_offset_.stamp(scan_start, scan_end, received, monotonic);
    output.header.frame_id = kLidarFrame;
    output.height = 1;
    output.width = static_cast<std::uint32_t>(selected.size());
    output.fields = {
      PointField().set__name("x").set__offset(0).set__datatype(PointField::FLOAT32).set__count(1),
      PointField().set__name("y").set__offset(4).set__datatype(PointField::FLOAT32).set__count(1),
      PointField().set__name("z").set__offset(8).set__datatype(PointField::FLOAT32).set__count(1),
      PointField().set__name("intensity").set__offset(12).set__datatype(PointField::FLOAT32).set__count(1),
      PointField().set__name("time").set__offset(16).set__datatype(PointField::FLOAT32).set__count(1),
      PointField().set__name("ring").set__offset(20).set__datatype(PointField::UINT16).set__count(1),
    };
    output.is_bigendian = false;
    output.point_step = kOutputPointStep;
    output.row_step = static_cast<std::uint32_t>(kOutputPointStep * selected.size());
    output.data.assign(output.row_step, 0);
    output.is_dense = true;
    for (std::size_t index = 0; index < selected.size(); ++index) {
      const auto & point = selected[index];
      const std::size_t base = index * kOutputPointStep;
      write_value(output.data, base, point.x);
      write_value(output.data, base + 4, point.y);
      write_value(output.data, base + 8, point.z);
      write_value(output.data, base + 12, std::isfinite(point.intensity) ? point.intensity : 0.0F);
      write_value(output.data, base + 16, static_cast<float>(point.timestamp - scan_start));
      write_value(output.data, base + 20, point.ring);
    }
    return output;
  }

  void on_cloud(const sensor_msgs::msg::PointCloud2::SharedPtr message)
  {
    const double received = now().seconds();
    const double monotonic = steady_seconds();
    try {
      auto output = convert_cloud(*message, received, monotonic);
      cloud_publisher_->publish(std::move(output));
      cloud_count_.fetch_add(1, std::memory_order_relaxed);
    } catch (const ContractError & error) {
      reject(error);
    }
  }

#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  void on_lowstate(const unitree_go::msg::LowState::SharedPtr message)
  {
    const auto & state = message->imu_state;
    const auto all_finite = [](const auto & values) {
        return std::all_of(values.begin(), values.end(), [](float value) {
          return std::isfinite(value);
        });
      };
    if (!all_finite(state.quaternion) || !all_finite(state.gyroscope) ||
      !all_finite(state.accelerometer))
    {
      reject(ContractError("imu vectors must contain finite values"));
      return;
    }
    const double norm = std::sqrt(std::inner_product(
      state.quaternion.begin(), state.quaternion.end(), state.quaternion.begin(), 0.0));
    if (!std::isfinite(norm) || norm < 0.5 || norm > 1.5) {
      reject(ContractError("imu quaternion norm is outside the supported range"));
      return;
    }

    sensor_msgs::msg::Imu output;
    output.header.stamp = now();
    output.header.frame_id = kImuFrame;
    output.orientation.w = state.quaternion[0] / norm;
    output.orientation.x = state.quaternion[1] / norm;
    output.orientation.y = state.quaternion[2] / norm;
    output.orientation.z = state.quaternion[3] / norm;
    output.angular_velocity.x = state.gyroscope[0];
    output.angular_velocity.y = state.gyroscope[1];
    output.angular_velocity.z = state.gyroscope[2];
    output.linear_acceleration.x = state.accelerometer[0];
    output.linear_acceleration.y = state.accelerometer[1];
    output.linear_acceleration.z = state.accelerometer[2];
    imu_publisher_->publish(std::move(output));
    imu_count_.fetch_add(1, std::memory_order_relaxed);
  }
#endif

  void report()
  {
    const auto clouds = cloud_count_.exchange(0, std::memory_order_relaxed);
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    const auto imu = imu_count_.exchange(0, std::memory_order_relaxed);
#endif
    const auto rejected = reject_count_.exchange(0, std::memory_order_relaxed);
#if defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
    RCLCPP_INFO(
      get_logger(), "cloud bridge 5s: clouds=%llu, rejected=%llu",
      static_cast<unsigned long long>(clouds),
      static_cast<unsigned long long>(rejected));
#else
    RCLCPP_INFO(
      get_logger(), "bridge 5s: clouds=%llu, imu=%llu, rejected=%llu",
      static_cast<unsigned long long>(clouds),
      static_cast<unsigned long long>(imu),
      static_cast<unsigned long long>(rejected));
#endif
  }

  ClockOffsetTracker clock_offset_;
  std::atomic<std::uint64_t> cloud_count_{0};
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  std::atomic<std::uint64_t> imu_count_{0};
#endif
  std::atomic<std::uint64_t> reject_count_{0};
  rclcpp::CallbackGroup::SharedPtr cloud_group_;
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  rclcpp::CallbackGroup::SharedPtr imu_group_;
#endif
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr cloud_publisher_;
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_publisher_;
#endif
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr cloud_subscription_;
#if !defined(ROBOT_SCOPE_XT16_CLOUD_ONLY)
  rclcpp::Subscription<unitree_go::msg::LowState>::SharedPtr imu_subscription_;
#endif
  rclcpp::TimerBase::SharedPtr report_timer_;
};

}  // namespace robot_scope_xt16_bridge

int main(int, char **)
{
  int argc = 0;
  char ** argv = nullptr;
  rclcpp::init(argc, argv);
  try {
    auto node = std::make_shared<robot_scope_xt16_bridge::Xt16FastlioBridge>();
    rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 2);
    executor.add_node(node);
    executor.spin();
    executor.remove_node(node);
    rclcpp::shutdown();
    return 0;
  } catch (const std::exception & error) {
    RCLCPP_FATAL(
      rclcpp::get_logger(robot_scope_xt16_bridge::kLoggerName), "%s", error.what());
    rclcpp::shutdown();
    return 2;
  }
}
