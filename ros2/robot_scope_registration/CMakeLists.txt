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

option(ROBOT_SCOPE_BUILD_PCL_BACKENDS "Build fixed PCL registration backends" OFF)
if(ROBOT_SCOPE_BUILD_PCL_BACKENDS)
  find_package(PCL 1.12 REQUIRED COMPONENTS common filters kdtree registration search)

  foreach(backend IN ITEMS ndt2d gicp)
    string(TOUPPER "${backend}" backend_upper)
    add_executable(robot_scope_offline_registration_pcl_${backend}
                   src/pcl_registration_cli.cpp)
    target_include_directories(robot_scope_offline_registration_pcl_${backend}
                               SYSTEM PRIVATE ${PCL_INCLUDE_DIRS})
    target_compile_definitions(robot_scope_offline_registration_pcl_${backend}
                               PRIVATE ROBOT_SCOPE_PCL_BACKEND_${backend_upper}=1)
    target_link_libraries(robot_scope_offline_registration_pcl_${backend}
                          PRIVATE robot_scope_registration_core ${PCL_LIBRARIES})
    target_compile_options(robot_scope_offline_registration_pcl_${backend}
                           PRIVATE -Wall -Wextra -Wpedantic)
  endforeach()
endif()

include(CTest)
if(BUILD_TESTING)
  add_executable(robot_scope_registration_core_test test/registration_core_test.cpp)
  target_link_libraries(robot_scope_registration_core_test PRIVATE robot_scope_registration_core)
  target_compile_options(robot_scope_registration_core_test PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME robot_scope_registration_core COMMAND robot_scope_registration_core_test)
endif()

if(ROBOT_SCOPE_BUILD_PCL_BACKENDS)
  install(TARGETS robot_scope_offline_registration_pcl_ndt2d
                  robot_scope_offline_registration_pcl_gicp
          RUNTIME DESTINATION lib/${PROJECT_NAME})
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
