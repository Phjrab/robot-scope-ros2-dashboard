cmake_minimum_required(VERSION 3.16)
project(robot_scope_registration LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(robot_scope_registration_core src/registration_core.cpp)
target_include_directories(robot_scope_registration_core PUBLIC include)
target_compile_options(robot_scope_registration_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(robot_scope_offline_registration src/offline_registration_cli.cpp)
target_link_libraries(robot_scope_offline_registration PRIVATE robot_scope_registration_core)
target_compile_options(robot_scope_offline_registration PRIVATE -Wall -Wextra -Wpedantic)

include(CTest)
if(BUILD_TESTING)
  add_executable(robot_scope_registration_core_test test/registration_core_test.cpp)
  target_link_libraries(robot_scope_registration_core_test PRIVATE robot_scope_registration_core)
  target_compile_options(robot_scope_registration_core_test PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME robot_scope_registration_core COMMAND robot_scope_registration_core_test)
endif()

find_package(ament_cmake QUIET)
if(ament_cmake_FOUND)
  install(TARGETS robot_scope_registration_core robot_scope_offline_registration
          ARCHIVE DESTINATION lib LIBRARY DESTINATION lib
          RUNTIME DESTINATION lib/${PROJECT_NAME})
  install(DIRECTORY include/ DESTINATION include)
  ament_export_include_directories(include)
  ament_export_libraries(robot_scope_registration_core)
  ament_package()
endif()
