#define ROBOT_SCOPE_XT16_CLOUD_ONLY 1
#define ROBOT_SCOPE_XT16_BRIDGE_NO_MAIN 1
#include "../src/xt16_fastlio_bridge.cpp"

#include <cmath>
#include <iostream>
#include <string>

namespace
{

using robot_scope_xt16_bridge::CloudContract;
using robot_scope_xt16_bridge::ContractError;
using sensor_msgs::msg::PointCloud2;
using sensor_msgs::msg::PointField;

int failures = 0;

void check(bool condition, const std::string & message)
{
  if (!condition) {
    ++failures;
    std::cerr << "FAIL: " << message << '\n';
  }
}

template<typename Callable>
void expect_contract_error(Callable && callable, const std::string & expected)
{
  try {
    callable();
    check(false, "expected ContractError containing: " + expected);
  } catch (const ContractError & error) {
    check(
      std::string(error.what()).find(expected) != std::string::npos,
      "unexpected ContractError: " + std::string(error.what()));
  } catch (const std::exception & error) {
    check(false, "unexpected exception type: " + std::string(error.what()));
  }
}

template<typename T>
T value_at(const std::vector<std::uint8_t> & data, std::size_t offset)
{
  return robot_scope_xt16_bridge::read_value<T>(data, offset);
}

builtin_interfaces::msg::Time ros_time(double seconds)
{
  builtin_interfaces::msg::Time stamp;
  const double integral = std::floor(seconds);
  stamp.sec = static_cast<std::int32_t>(integral);
  stamp.nanosec = static_cast<std::uint32_t>(
    std::llround((seconds - integral) * 1'000'000'000.0));
  return stamp;
}

PointCloud2 raw_cloud(double scan_start)
{
  constexpr std::size_t points = 4'000;
  constexpr std::size_t point_step = 26;
  PointCloud2 message;
  message.header.frame_id = "hesai_lidar";
  message.header.stamp = ros_time(scan_start);
  message.height = 1;
  message.width = points;
  message.fields = {
    PointField().set__name("x").set__offset(0).set__datatype(PointField::FLOAT32).set__count(1),
    PointField().set__name("y").set__offset(4).set__datatype(PointField::FLOAT32).set__count(1),
    PointField().set__name("z").set__offset(8).set__datatype(PointField::FLOAT32).set__count(1),
    PointField().set__name("intensity").set__offset(12).set__datatype(PointField::FLOAT32).set__count(1),
    PointField().set__name("ring").set__offset(16).set__datatype(PointField::UINT16).set__count(1),
    PointField().set__name("timestamp").set__offset(18).set__datatype(PointField::FLOAT64).set__count(1),
  };
  message.is_bigendian = false;
  message.point_step = point_step;
  message.row_step = points * point_step;
  message.data.assign(message.row_step, 0);
  message.is_dense = true;
  for (std::size_t index = 0; index < points; ++index) {
    const std::size_t base = index * point_step;
    robot_scope_xt16_bridge::write_value(
      message.data, base, static_cast<float>(index) + 0.25F);
    robot_scope_xt16_bridge::write_value(
      message.data, base + 4, static_cast<float>(index) + 0.5F);
    robot_scope_xt16_bridge::write_value(
      message.data, base + 8, static_cast<float>(index) + 0.75F);
    robot_scope_xt16_bridge::write_value(
      message.data, base + 12, static_cast<float>(index % 255));
    robot_scope_xt16_bridge::write_value(
      message.data, base + 16, static_cast<std::uint16_t>(index % 16));
    robot_scope_xt16_bridge::write_value(
      message.data, base + 18,
      scan_start + 0.1 * static_cast<double>(index) / 3996.0);
  }
  return message;
}

void calibrate(CloudContract & contract)
{
  for (int index = 0; index < 3; ++index) {
    const double start = 100.0 + index;
    auto message = raw_cloud(start);
    expect_contract_error(
      [&]() {contract.convert(message, start + 10.1, 1.0 + index);},
      "calibration");
  }
}

void test_exact_conversion_contract()
{
  check(CloudContract::native_little_endian(), "test host must be little-endian");
  CloudContract contract;
  calibrate(contract);
  auto message = raw_cloud(103.0);
  auto output = contract.convert(message, 113.1, 4.0);

  check(output.header.frame_id == "hesai_lidar", "output frame changed");
  check(output.header.stamp.sec == 113, "output seconds do not preserve calibrated time");
  check(output.header.stamp.nanosec == 0, "output nanoseconds are not exact");
  check(output.height == 1 && output.width == 1'000, "four-to-one decimation changed");
  check(output.point_step == 22 && output.row_step == 22'000, "output stride changed");
  check(output.data.size() == output.row_step, "output payload size changed");
  check(output.is_dense && !output.is_bigendian, "output endian/density contract changed");

  const std::array<std::string, 6> names{"x", "y", "z", "intensity", "time", "ring"};
  const std::array<std::uint32_t, 6> offsets{0, 4, 8, 12, 16, 20};
  check(output.fields.size() == names.size(), "output field count changed");
  for (std::size_t index = 0; index < names.size() && index < output.fields.size(); ++index) {
    check(output.fields[index].name == names[index], "output field name changed");
    check(output.fields[index].offset == offsets[index], "output field offset changed");
    check(output.fields[index].count == 1, "output field count must remain one");
  }
  check(std::abs(value_at<float>(output.data, 0) - 0.25F) < 1e-6F, "x value changed");
  check(std::abs(value_at<float>(output.data, 4) - 0.5F) < 1e-6F, "y value changed");
  check(std::abs(value_at<float>(output.data, 8) - 0.75F) < 1e-6F, "z value changed");
  check(value_at<float>(output.data, 16) == 0.0F, "first relative time must be zero");
  check(value_at<std::uint16_t>(output.data, 20) == 0, "ring value changed");

  auto next = raw_cloud(104.0);
  contract.convert(next, 114.1, 5.0);
  expect_contract_error(
    [&]() {contract.convert(next, 114.2, 5.1);},
    "device timestamp did not increase");

  auto stepped = raw_cloud(105.0);
  expect_contract_error(
    [&]() {contract.convert(stepped, 115.6, 6.0);},
    "residual discontinuity");
}

void test_invalid_inputs_fail_closed()
{
  CloudContract contract;
  auto wrong_frame = raw_cloud(200.0);
  wrong_frame.header.frame_id = "camera_init";
  expect_contract_error(
    [&]() {contract.convert(wrong_frame, 210.1, 1.0);}, "frame must be hesai_lidar");

  auto bad_header = raw_cloud(201.0);
  bad_header.header.stamp = ros_time(201.02);
  expect_contract_error(
    [&]() {contract.convert(bad_header, 211.1, 2.0);},
    "header does not match");

  auto duplicate_field = raw_cloud(202.0);
  duplicate_field.fields.push_back(duplicate_field.fields.front());
  expect_contract_error(
    [&]() {contract.convert(duplicate_field, 212.1, 3.0);}, "field x is duplicated");

  auto short_payload = raw_cloud(203.0);
  short_payload.data.pop_back();
  expect_contract_error(
    [&]() {contract.convert(short_payload, 213.1, 4.0);},
    "payload length does not match");

  auto too_few_finite = raw_cloud(204.0);
  robot_scope_xt16_bridge::write_value(
    too_few_finite.data, 0, std::numeric_limits<float>::quiet_NaN());
  expect_contract_error(
    [&]() {contract.convert(too_few_finite, 214.1, 5.0);},
    "too few finite decimated");
}

}  // namespace

int main()
{
  test_exact_conversion_contract();
  test_invalid_inputs_fail_closed();
  if (failures != 0) {
    std::cerr << failures << " XT16 cloud contract checks failed\n";
    return 1;
  }
  std::cout << "XT16 cloud contract checks passed\n";
  return 0;
}
