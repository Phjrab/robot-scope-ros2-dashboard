cmake_minimum_required(VERSION 3.16)
project(robot_scope_hesai_xt16_calibration LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(HESAI_SDK_ROOT "" CACHE PATH "Pinned HesaiLidar_SDK_2.0 source directory")
if(NOT IS_ABSOLUTE "${HESAI_SDK_ROOT}")
  message(FATAL_ERROR "HESAI_SDK_ROOT must be an absolute path")
endif()
if(NOT EXISTS "${HESAI_SDK_ROOT}/libhesai/PtcClient/include/ptc_client.h")
  message(FATAL_ERROR "HESAI_SDK_ROOT does not contain the pinned PTC client")
endif()

find_package(Git REQUIRED)
execute_process(
  COMMAND "${GIT_EXECUTABLE}" -C "${HESAI_SDK_ROOT}" rev-parse HEAD
  RESULT_VARIABLE HESAI_SDK_REVISION_RESULT
  OUTPUT_VARIABLE HESAI_SDK_REVISION
  OUTPUT_STRIP_TRAILING_WHITESPACE
  ERROR_QUIET
)
if(NOT HESAI_SDK_REVISION_RESULT EQUAL 0 OR
   NOT HESAI_SDK_REVISION STREQUAL "9d5dc4fc4ade5be5f6a6ca00e71dd4050b054168")
  message(FATAL_ERROR "HESAI_SDK_ROOT is not the pinned SDK revision")
endif()
execute_process(
  COMMAND "${GIT_EXECUTABLE}" -C "${HESAI_SDK_ROOT}" status --porcelain
  RESULT_VARIABLE HESAI_SDK_STATUS_RESULT
  OUTPUT_VARIABLE HESAI_SDK_STATUS
  OUTPUT_STRIP_TRAILING_WHITESPACE
  ERROR_QUIET
)
if(NOT HESAI_SDK_STATUS_RESULT EQUAL 0 OR NOT HESAI_SDK_STATUS STREQUAL "")
  message(FATAL_ERROR "HESAI_SDK_ROOT must be a clean pinned checkout")
endif()

find_package(Threads REQUIRED)
set(WITH_PTCS_USE OFF CACHE BOOL "The fixed XT16 endpoint uses plain PTC" FORCE)
add_subdirectory("${HESAI_SDK_ROOT}/libhesai/Logger" "${CMAKE_BINARY_DIR}/Logger")
add_subdirectory("${HESAI_SDK_ROOT}/libhesai/Common" "${CMAKE_BINARY_DIR}/Common")
add_subdirectory("${HESAI_SDK_ROOT}/libhesai/PtcClient" "${CMAKE_BINARY_DIR}/PtcClient")

add_executable(robot_scope_acquire_xt16_correction acquire_xt16_correction.cc)
target_link_libraries(robot_scope_acquire_xt16_correction PRIVATE ptcClient_lib)
target_compile_options(robot_scope_acquire_xt16_correction PRIVATE
  -Wall
  -Wextra
  -Wpedantic
  -Werror
)
