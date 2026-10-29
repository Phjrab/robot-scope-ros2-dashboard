// Copyright 2026 Robot Scope contributors. SPDX-License-Identifier: Apache-2.0
// Native Shim + TF buffer. No command publishers, actions, sensor input or bridge.
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <set>
#include <vector>
#include "gtest/gtest.h"
#include "rcl/time.h"
#include "nav2_controller/plugins/simple_goal_checker.hpp"
#include "nav2_controller/plugins/simple_progress_checker.hpp"
#include "nav2_controller/plugins/pose_progress_checker.hpp"
#include "nav2_rotation_shim_controller/nav2_rotation_shim_controller.hpp"
#ifdef ROBOT_SCOPE_FIXED
#include "common_time.hpp"
#endif

using Pose = geometry_msgs::msg::PoseStamped;
using Twist = geometry_msgs::msg::Twist;

geometry_msgs::msg::Quaternion quat(double yaw)
{
  tf2::Quaternion value;
  value.setRPY(0, 0, yaw);
  return tf2::toMsg(value);
}

class SpyPrimary : public nav2_core::Controller
{
public:
  int calls = 0;
  void configure(const rclcpp_lifecycle::LifecycleNode::WeakPtr &, std::string,
    std::shared_ptr<tf2_ros::Buffer>, std::shared_ptr<nav2_costmap_2d::Costmap2DROS>) override {}
  void cleanup() override {}
  void activate() override {}
  void deactivate() override {}
  void setPlan(const nav_msgs::msg::Path &) override {}
  void setSpeedLimit(const double &, const bool &) override {}
  geometry_msgs::msg::TwistStamped computeVelocityCommands(
    const Pose & pose, const Twist &, nav2_core::GoalChecker *) override
  {
    ++calls;
    geometry_msgs::msg::TwistStamped cmd;
    cmd.header = pose.header;
    cmd.twist.linear.x = 0.25;
    return cmd;
  }
};

class Shim : public nav2_rotation_shim_controller::RotationShimController
{
public:
  void useSpy(const std::shared_ptr<SpyPrimary> & spy) {primary_controller_ = spy;}
  void skipInitialHeading() {path_updated_ = false;}
};

class Heading : public ::testing::Test
{
public:
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> node;
  std::shared_ptr<tf2_ros::Buffer> tf;
  std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap;
  std::shared_ptr<SpyPrimary> spy;
  Shim shim;
  nav2_controller::SimpleGoalChecker checker;
  Pose pose;
  nav_msgs::msg::Path path;

  void now(double seconds)
  {
    ASSERT_EQ(rcl_set_ros_time_override(node->get_clock()->get_clock_handle(),
      static_cast<int64_t>(seconds * 1e9)), RCL_RET_OK);
  }
  void edge(const std::string & parent, const std::string & child, double stamp,
    double x = 0, double yaw = 0)
  {
    geometry_msgs::msg::TransformStamped value;
    value.header.frame_id = parent;
    value.child_frame_id = child;
    value.header.stamp = rclcpp::Time(static_cast<int64_t>(stamp * 1e9));
    value.transform.translation.x = x;
    value.transform.rotation = quat(yaw);
    ASSERT_TRUE(tf->setTransform(value, "isolated_native_test", false));
  }
  void inputs(double map_stamp, double body_stamp, double x = 0.03, double yaw = 1.2)
  {
    tf->clear();
    edge("map", "odom", 98);
    edge("odom", "base_link", 98);
    edge("map", "odom", map_stamp);
    edge("odom", "base_link", body_stamp);
    pose.header.frame_id = "odom";
    pose.header.stamp = rclcpp::Time(static_cast<int64_t>(body_stamp * 1e9));
    pose.pose.orientation = quat(0);
    path.header.frame_id = "map";
    path.header.stamp = rclcpp::Time(97, 0);
    path.poses.resize(2);
    path.poses[0].pose.orientation = quat(0);
    path.poses[1].pose.position.x = x;
    path.poses[1].pose.orientation = quat(yaw);
    shim.setPlan(path);
    shim.skipInitialHeading();
  }
  auto command() {return shim.computeVelocityCommands(pose, Twist(), &checker);}
  void SetUp() override
  {
    if (const char * expected = std::getenv("ROBOT_SCOPE_EXPECTED_SHIM_LIBRARY")) {
      std::ifstream maps("/proc/self/maps");
      std::set<std::string> loaded;
      std::string line;
      while (std::getline(maps, line)) {
        if (line.find("libnav2_rotation_shim_controller.so") != std::string::npos) {
          loaded.insert(line.substr(line.find('/')));
        }
      }
      ASSERT_EQ(loaded, std::set<std::string>{expected});
      RecordProperty("loaded_shim_library", expected);
    }
    node = std::make_shared<rclcpp_lifecycle::LifecycleNode>("heading_native_test");
    ASSERT_EQ(rcl_enable_ros_time_override(node->get_clock()->get_clock_handle()), RCL_RET_OK);
    now(100);
    // Keep timeout time advancing while the deterministic pose clock is frozen.
    // Otherwise upstream's 0.1s ROS-time wait never expires in this fixture.
    tf = std::make_shared<tf2_ros::Buffer>(std::make_shared<rclcpp::Clock>(RCL_SYSTEM_TIME));
    tf->setUsingDedicatedThread(true);
    costmap = std::make_shared<nav2_costmap_2d::Costmap2DROS>("heading_test_costmap");
    costmap->set_parameter(rclcpp::Parameter("plugins", std::vector<std::string>{}));
    costmap->on_configure(rclcpp_lifecycle::State());
    costmap->getCostmap()->resizeMap(200, 200, 0.05, -5, -5);
    costmap->getCostmap()->resetMap(0, 0, 200, 200);
    node->declare_parameter("controller_frequency", 10.0);
    node->declare_parameter("FollowPath.primary_controller",
      "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController");
    node->declare_parameter("FollowPath.rotate_to_goal_heading", true);
    node->declare_parameter("FollowPath.rotate_to_heading_angular_vel", 0.5);
    node->declare_parameter("FollowPath.max_angular_accel", 1.2);
    node->declare_parameter("FollowPath.closed_loop", false);
    node->declare_parameter("checker.xy_goal_tolerance", 0.10);
    node->declare_parameter("checker.yaw_goal_tolerance", 0.10);
    checker.initialize(node, "checker", costmap);
    shim.configure(node, "FollowPath", tf, costmap);
    shim.activate();
    spy = std::make_shared<SpyPrimary>();
    shim.useSpy(spy);
    inputs(100, 100);
  }
  void TearDown() override
  {
    shim.deactivate();
    shim.cleanup();
    costmap->on_cleanup(rclcpp_lifecycle::State());
  }
};

TEST_F(Heading, ExactTimeFinalHeading)
{
  auto cmd = command();
  EXPECT_EQ(spy->calls, 0);
  EXPECT_DOUBLE_EQ(cmd.twist.linear.x, 0);
  EXPECT_NEAR(cmd.twist.angular.z, 0.12, 1e-9);
}

TEST_F(Heading, DelayedEdges10_40_60ms)
{
  for (double delay : {0.01, 0.04, 0.06}) {
    inputs(100 - delay, 100 - delay);
    const auto before = spy->calls;
    auto start = std::chrono::steady_clock::now();
    const auto cmd = command();
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    RecordProperty("delay_ms_" + std::to_string(static_cast<int>(delay * 1000)), std::to_string(elapsed));
#ifdef ROBOT_SCOPE_FIXED
    EXPECT_EQ(spy->calls, before);
    EXPECT_DOUBLE_EQ(cmd.twist.linear.x, 0);
    EXPECT_GT(cmd.twist.angular.z, 0);
    EXPECT_EQ(cmd.header.stamp, pose.header.stamp);
    EXPECT_LT(elapsed, 0.05);
#else
    EXPECT_EQ(spy->calls, before + 1);
    EXPECT_DOUBLE_EQ(cmd.twist.linear.x, 0.25);
    EXPECT_DOUBLE_EQ(cmd.twist.angular.z, 0);
#endif
  }
}

TEST_F(Heading, UnequalEdgeTimes)
{
  inputs(99.94, 99.99);
  const auto cmd = command();
#ifdef ROBOT_SCOPE_FIXED
  EXPECT_EQ(spy->calls, 0);
  EXPECT_EQ(rclcpp::Time(cmd.header.stamp).nanoseconds(), 99940000000LL);
  EXPECT_GT(cmd.twist.angular.z, 0);
#else
  EXPECT_EQ(spy->calls, 1);
#endif
}

TEST_F(Heading, ApproachStillUsesPrimary)
{
  inputs(100, 100, 1.0);
  const auto cmd = command();
  EXPECT_EQ(spy->calls, 1);
  EXPECT_DOUBLE_EQ(cmd.twist.linear.x, 0.25);
}

TEST_F(Heading, NewPathReplacesFinalYaw)
{
  auto first = command();
  inputs(100, 100, 0.03, -1.2);
  auto second = command();
  auto third = command();
  EXPECT_GT(first.twist.angular.z, 0);
  EXPECT_LE(second.twist.angular.z, first.twist.angular.z);
  EXPECT_LT(third.twist.angular.z, 0);
  EXPECT_EQ(spy->calls, 0);
}

TEST_F(Heading, CollisionDuringFinalRotation)
{
  std::fill(costmap->getCostmap()->getCharMap(),
    costmap->getCostmap()->getCharMap() + 200 * 200, nav2_costmap_2d::LETHAL_OBSTACLE);
  for (double yaw : {1.2, 0.5, -0.5}) {
    inputs(100, 100, 0.03, yaw);
#ifdef ROBOT_SCOPE_COLLISION_FIXED
    EXPECT_THROW(command(), nav2_core::PlannerException) << yaw;
#else
    if (std::abs(yaw) < 0.785) {
      // Original and TF-only variants both skip the short final-yaw sweep.
      EXPECT_NO_THROW(command());
    } else {
#ifdef ROBOT_SCOPE_FIXED
      EXPECT_THROW(command(), nav2_core::PlannerException);
#else
      const auto before = spy->calls;
      EXPECT_NO_THROW(command());
      EXPECT_EQ(spy->calls, before + 1);
#endif
    }
#endif
  }
}

TEST_F(Heading, InstalledProgressCheckerComparison)
{
  node->declare_parameter("simple.required_movement_radius", 0.2);
  node->declare_parameter("simple.movement_time_allowance", 10.0);
  node->declare_parameter("pose.required_movement_radius", 0.2);
  node->declare_parameter("pose.movement_time_allowance", 10.0);
  node->declare_parameter("pose.required_movement_angle", 0.2);
  nav2_controller::SimpleProgressChecker simple;
  nav2_controller::PoseProgressChecker angular;
  simple.initialize(node, "simple");
  angular.initialize(node, "pose");
  for (int scenario = 0; scenario < 5; ++scenario) {
    simple.reset();
    angular.reset();
    bool simple_ok = true;
    bool angular_ok = true;
    for (int tick = 0; tick <= 120; ++tick) {
      now(100 + tick * 0.1);
      double yaw = 0;
      if (scenario == 0) {yaw = tick * 0.005;}  // converging final rotation
      if (scenario == 2) {yaw = 0.04 * std::sin(tick);}  // small noise
      if (scenario == 3) {yaw = (tick / 5) % 2 ? 0.3 : -0.3;}  // oscillation
      if (scenario == 4) {yaw = tick * 0.1;}  // endless rotation
      pose.pose.orientation = quat(yaw);
      simple_ok = simple.check(pose) && simple_ok;
      angular_ok = angular.check(pose) && angular_ok;
    }
    EXPECT_FALSE(simple_ok);
    // PoseProgressChecker cannot reject large oscillation/endless spin itself.
    // Such a candidate still requires a finite trial and convergence evidence.
    EXPECT_EQ(angular_ok, scenario == 0 || scenario == 3 || scenario == 4);
  }
}

#ifdef ROBOT_SCOPE_FIXED
TEST_F(Heading, MissingStaleFutureAndEmptyRejectWithoutFallback)
{
  for (int scenario = 0; scenario < 4; ++scenario) {
    inputs(100, 100);
    if (scenario == 0) {tf->clear();}
    if (scenario == 1) {inputs(99, 99);}
    if (scenario == 2) {pose.header.stamp = rclcpp::Time(101, 0);}
    if (scenario == 3) {path.poses.clear(); shim.setPlan(path);}
    EXPECT_THROW(command(), nav2_core::PlannerException);
    EXPECT_EQ(spy->calls, 0);
  }
}

TEST_F(Heading, ClockRewindAndNewGeneration)
{
  command();
  now(99);
  pose.header.stamp = rclcpp::Time(99, 0);
  EXPECT_THROW(command(), nav2_core::PlannerException);
  tf->clear();
  edge("map", "odom", 99);
  edge("odom", "base_link", 99);
  EXPECT_THROW(command(), nav2_core::PlannerException);
  shim.setPlan(path);
  shim.skipInitialHeading();
  EXPECT_NO_THROW(command());
}

TEST_F(Heading, CommonTimeReconstructsBothPosesAndPreservesInputs)
{
  inputs(99.94, 99.99);
  tf->clear();
  edge("map", "odom", 99.9, 0.1, 0.1);
  edge("map", "odom", 99.94, 0.2, 0.2);
  edge("odom", "base_link", 99.9, 0, 0);
  edge("odom", "base_link", 99.99, 0.9, 0.9);
  pose.pose.position.x = 0.9;
  pose.pose.orientation = quat(0.9);
  auto goal = path.poses.back();
  goal.header = path.header;
  const auto before = pose;
  const auto aligned = robot_scope_heading::commonTimePoses(*tf, pose, goal, "base_link",
    node->now(), costmap->getTransformTolerance());
  EXPECT_EQ(pose, before);
  EXPECT_EQ(aligned.first.header.stamp, aligned.second.header.stamp);
  EXPECT_NEAR(aligned.first.pose.position.x, 0.4, 1e-7);
  EXPECT_NEAR(tf2::getYaw(aligned.first.pose.orientation), 0.4, 1e-7);
  EXPECT_NEAR(tf2::getYaw(aligned.second.pose.orientation), 1.0, 1e-7);
  EXPECT_EQ(goal.header.stamp, path.header.stamp);
}
#endif

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  ::testing::InitGoogleTest(&argc, argv);
  const int result = RUN_ALL_TESTS();
  rclcpp::shutdown();
  return result;
}
