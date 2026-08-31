cmake_minimum_required(VERSION 3.8)
project(robot_scope_xt16_bridge)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(unitree_go REQUIRED)

add_executable(robot_scope_xt16_bridge_node src/xt16_fastlio_bridge.cpp)
target_compile_options(robot_scope_xt16_bridge_node PRIVATE -Wall -Wextra -Wpedantic)
ament_target_dependencies(
  robot_scope_xt16_bridge_node
  rclcpp
  sensor_msgs
  unitree_go
)

add_executable(robot_scope_xt16_cloud_bridge_node src/xt16_fastlio_bridge.cpp)
target_compile_definitions(
  robot_scope_xt16_cloud_bridge_node
  PRIVATE ROBOT_SCOPE_XT16_CLOUD_ONLY=1
)
target_compile_options(
  robot_scope_xt16_cloud_bridge_node
  PRIVATE -Wall -Wextra -Wpedantic
)
ament_target_dependencies(
  robot_scope_xt16_cloud_bridge_node
  rclcpp
  sensor_msgs
)

install(
  TARGETS
    robot_scope_xt16_bridge_node
    robot_scope_xt16_cloud_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
