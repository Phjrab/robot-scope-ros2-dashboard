// Read-only D435i SDK diagnosis. No option setters, firmware writes or robot commands.
#include <librealsense2/rs.hpp>
#include <chrono>
#include <cmath>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>

int main(int argc, char** argv) {
  if (argc < 2 || argc > 3 || std::string(argv[1]) != "242322077753" ||
      (argc == 3 && std::string(argv[2]) != "--options-only")) return 2;
  std::mutex mutex;
  int gyro = 0, accel = 0;
  double first_g = 0, last_g = 0, first_a = 0, last_a = 0;
  try {
    rs2::context context;
    rs2::device camera;
    for (auto device : context.query_devices())
      if (device.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) == std::string(argv[1])) camera = device;
    if (!camera) throw std::runtime_error("Observed serial not connected");
    std::cout << "SDK=" << RS2_API_VERSION_STR << " firmware="
              << camera.get_info(RS2_CAMERA_INFO_FIRMWARE_VERSION) << "\n";
    auto depth = camera.first<rs2::depth_sensor>();
    std::cout << "emitter_before=" << depth.get_option(RS2_OPTION_EMITTER_ENABLED) << "\n";
    if (argc == 3) return 0;  // Final readback without opening or changing any stream.
    rs2::sensor motion;
    std::vector<rs2::stream_profile> profiles;
    for (auto sensor : camera.query_sensors()) {
      std::vector<rs2::stream_profile> candidates;
      for (auto profile : sensor.get_stream_profiles()) {
        if ((profile.stream_type() == RS2_STREAM_GYRO && profile.fps() == 200) ||
            (profile.stream_type() == RS2_STREAM_ACCEL && profile.fps() == 100)) {
          candidates.push_back(profile);
        }
      }
      if (candidates.size() == 2) { motion = sensor; profiles = candidates; break; }
    }
    if (!motion) throw std::runtime_error("Expected observed gyro200/accel100 profiles unavailable");
    for (auto profile : profiles) {
      try {
      auto intrinsic = profile.as<rs2::motion_stream_profile>().get_motion_intrinsics();
      std::cout << "intrinsic stream=" << profile.stream_name() << " noise=";
      for (auto value : intrinsic.noise_variances) std::cout << value << ",";
      std::cout << " bias=";
      for (auto value : intrinsic.bias_variances) std::cout << value << ",";
      std::cout << "\n";
      } catch (const rs2::error& e) { std::cerr << "INTRINSIC_ERROR " << e.what() << "\n"; }
    }
    motion.open(profiles);
    motion.start([&](rs2::frame frame) {
      auto sample = frame.as<rs2::motion_frame>();
      if (!sample) return;
      auto value = sample.get_motion_data();
      std::lock_guard<std::mutex> guard(mutex);
      bool is_gyro = sample.get_profile().stream_type() == RS2_STREAM_GYRO;
      auto& count = is_gyro ? gyro : accel;
      auto& first = is_gyro ? first_g : first_a;
      auto& last = is_gyro ? last_g : last_a;
      if (!count) {
        first = frame.get_timestamp();
        std::cout << "first_sample stream=" << sample.get_profile().stream_name()
                  << " timestamp_domain=" << frame.get_frame_timestamp_domain()
                  << " xyz=" << value.x << "," << value.y << "," << value.z << "\n";
      }
      last = frame.get_timestamp(); ++count;
    });
    std::this_thread::sleep_for(std::chrono::seconds(10));
    motion.stop(); motion.close();
    std::cout << "RESULT gyro_count=" << gyro << " accel_count=" << accel
              << " gyro_hz=" << (last_g > first_g ? 1000 * (gyro-1)/(last_g-first_g) : 0)
              << " accel_hz=" << (last_a > first_a ? 1000 * (accel-1)/(last_a-first_a) : 0)
              << " emitter_after=" << depth.get_option(RS2_OPTION_EMITTER_ENABLED) << "\n";
    return gyro && accel ? 0 : 3;
  } catch (const rs2::error& e) {
    std::cerr << "SDK_ERROR " << e.get_failed_function() << ": " << e.what() << "\n";
  } catch (const std::exception& e) { std::cerr << "ERROR " << e.what() << "\n"; }
  return 1;
}
