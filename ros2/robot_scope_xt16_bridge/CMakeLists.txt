cmake_minimum_required(VERSION 3.8)
project(robot_scope_xt16_bridge)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
include(CTest)

option(
  ROBOT_SCOPE_XT16_BUILD_LEGACY
  "Build the wired legacy bridge that depends on unitree_go"
  ON
)

if(ROBOT_SCOPE_XT16_BUILD_LEGACY)
  find_package(unitree_go REQUIRED)
  add_executable(robot_scope_xt16_bridge_node src/xt16_fastlio_bridge.cpp)
  target_compile_options(robot_scope_xt16_bridge_node PRIVATE -Wall -Wextra -Wpedantic)
  ament_target_dependencies(
    robot_scope_xt16_bridge_node
    rclcpp
    sensor_msgs
    unitree_go
  )
endif()

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

set(ROBOT_SCOPE_XT16_INSTALL_TARGETS robot_scope_xt16_cloud_bridge_node)
if(ROBOT_SCOPE_XT16_BUILD_LEGACY)
  list(APPEND ROBOT_SCOPE_XT16_INSTALL_TARGETS robot_scope_xt16_bridge_node)
endif()
install(TARGETS ${ROBOT_SCOPE_XT16_INSTALL_TARGETS} DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  add_executable(
    robot_scope_xt16_cloud_contract_test
    test/xt16_cloud_contract_test.cpp
  )
  target_compile_options(
    robot_scope_xt16_cloud_contract_test
    PRIVATE -Wall -Wextra -Wpedantic
  )
  ament_target_dependencies(
    robot_scope_xt16_cloud_contract_test
    rclcpp
    sensor_msgs
  )
  add_test(
    NAME robot_scope_xt16_cloud_contract
    COMMAND robot_scope_xt16_cloud_contract_test
  )
endif()

ament_package()
