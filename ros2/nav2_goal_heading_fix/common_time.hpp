// Copyright 2026 Robot Scope contributors. SPDX-License-Identifier: Apache-2.0
#pragma once

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>
#include "nav2_core/exceptions.hpp"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"
#include "tf2_ros/buffer.h"

namespace robot_scope_heading
{
using Pose = geometry_msgs::msg::PoseStamped;

// Fixed goal geometry may be queried at a different time. TF samples and the
// controller's input pose are never restamped, mutated, or cached here.
inline std::pair<Pose, Pose> commonTimePoses(
  tf2_ros::Buffer & tf, const Pose & controller, const Pose & goal,
  const std::string & base_frame, const rclcpp::Time & now, double max_age)
{
  auto valid = [&](const rclcpp::Time & stamp) {
      const double age = (now - stamp).seconds();
      return stamp.nanoseconds() > 0 && age >= 0.0 && age <= max_age;
    };
  if (!std::isfinite(max_age) || max_age <= 0 ||
    controller.header.frame_id.empty() || goal.header.frame_id.empty() || base_frame.empty())
  {
    throw nav2_core::PlannerException("GOAL_TF_INVALID_CONTEXT");
  }
  const auto input_time = rclcpp::Time(controller.header.stamp, now.get_clock_type());
  if (!valid(input_time)) {
    throw nav2_core::PlannerException("GOAL_TF_CONTROLLER_POSE_NOT_FRESH");
  }
  auto time = input_time;
  const auto zero_wait = rclcpp::Duration::from_seconds(0.0);
  const auto & frame = controller.header.frame_id;
  auto supported = [&](const rclcpp::Time & stamp) {
      return tf.canTransform(frame, goal.header.frame_id, stamp, zero_wait) &&
             tf.canTransform(frame, base_frame, stamp, zero_wait);
    };
  bool use_input_pose = supported(time);
  try {
    if (!use_input_pose) {
      // Only discover the common chain time with TimePointZero. Both actual
      // transformations below use one explicit, bounded, nonzero query time.
      const auto common = tf.lookupTransform(goal.header.frame_id, base_frame, tf2::TimePointZero);
      time = rclcpp::Time(common.header.stamp, now.get_clock_type());
      if (time > input_time) {
        time = input_time;
      }
      if (!valid(time) || !supported(time)) {
        throw nav2_core::PlannerException("GOAL_TF_NO_FRESH_COMMON_TIME");
      }
    }
    Pose robot = controller;
    if (!use_input_pose) {
      Pose origin;
      origin.header.frame_id = base_frame;
      origin.header.stamp = time;
      origin.pose.orientation.w = 1.0;
      tf2::doTransform(origin, robot, tf.lookupTransform(frame, base_frame, time, zero_wait));
    }
    Pose queried_goal = goal;
    queried_goal.header.stamp = time;
    Pose transformed_goal;
    tf2::doTransform(queried_goal, transformed_goal,
      tf.lookupTransform(frame, goal.header.frame_id, time, zero_wait));
    robot.header.stamp = time;
    transformed_goal.header.stamp = time;
    return {robot, transformed_goal};
  } catch (const tf2::TransformException &) {
    throw nav2_core::PlannerException("GOAL_TF_NO_COMMON_TRANSFORM");
  }
}
}  // namespace robot_scope_heading
