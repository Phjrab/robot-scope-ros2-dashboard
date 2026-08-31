#include <algorithm>
#include <chrono>
#include <cerrno>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "logger.h"
#include "ptc_client.h"

namespace {

constexpr char kSensorIp[] = "192.168.123.20";
constexpr std::uint16_t kPtcPort = 9347;
constexpr std::size_t kMinCorrectionBytes = 64;
constexpr std::size_t kMaxCorrectionBytes = 64 * 1024;
constexpr char kOutputName[] = "xt16-correction.csv";

bool WriteExclusive(int directory_fd, const std::vector<std::uint8_t>& data) {
  const int descriptor = openat(
      directory_fd,
      kOutputName,
      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
      S_IRUSR | S_IWUSR);
  if (descriptor < 0) {
    std::cerr << "refusing to overwrite or follow the correction output\n";
    return false;
  }
  std::size_t offset = 0;
  while (offset < data.size()) {
    const ssize_t written = write(
        descriptor,
        data.data() + offset,
        data.size() - offset);
    if (written < 0 && errno == EINTR) {
      continue;
    }
    if (written <= 0) {
      std::cerr << "failed to write the private correction output\n";
      close(descriptor);
      unlinkat(directory_fd, kOutputName, 0);
      return false;
    }
    offset += static_cast<std::size_t>(written);
  }
  const bool sync_ok = fsync(descriptor) == 0;
  const bool close_ok = close(descriptor) == 0;
  if (!sync_ok || !close_ok) {
    std::cerr << "failed to synchronize the private correction output\n";
    unlinkat(directory_fd, kOutputName, 0);
    return false;
  }
  return true;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3 || std::string(argv[1]) != "--approved-read-only-ptc") {
    std::cerr << "usage: " << argv[0]
              << " --approved-read-only-ptc ABSOLUTE_PRIVATE_DIRECTORY\n";
    return 2;
  }

  const std::filesystem::path output_directory(argv[2]);
  if (!output_directory.is_absolute()) {
    std::cerr << "output directory must be absolute\n";
    return 2;
  }
  const int directory_fd = open(
      output_directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (directory_fd < 0) {
    std::cerr << "private output directory is unavailable\n";
    return 2;
  }
  struct stat directory_stat {};
  if (fstat(directory_fd, &directory_stat) != 0 ||
      !S_ISDIR(directory_stat.st_mode) || directory_stat.st_uid != getuid() ||
      (directory_stat.st_mode & 0777) != 0700) {
    std::cerr << "output directory must be owned by the operator and mode 0700\n";
    close(directory_fd);
    return 2;
  }

  Logger::GetInstance().setLogTargetRule(HESAI_LOG_TARGET_CONSOLE);
  Logger::GetInstance().setLogLevelRule(
      HESAI_LOG_WARNING | HESAI_LOG_ERROR | HESAI_LOG_FATAL);
  hesai::lidar::PtcClient client(
      kSensorIp,
      kPtcPort,
      false,
      hesai::lidar::PtcMode::tcp,
      1,
      "",
      "",
      "",
      500,
      500,
      2.0F,
      0);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!client.IsOpen() && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  if (!client.IsOpen()) {
    std::cerr << "read-only PTC connection did not become ready\n";
    close(directory_fd);
    return 1;
  }

  hesai::lidar::u8Array_t correction;
  if (client.GetCorrectionInfo(correction) != 0 ||
      correction.size() < kMinCorrectionBytes ||
      correction.size() > kMaxCorrectionBytes ||
      std::find(correction.begin(), correction.end(), 0) != correction.end()) {
    std::cerr << "PandarXT correction response failed the bounded CSV contract\n";
    close(directory_fd);
    return 1;
  }
  bool written = WriteExclusive(directory_fd, correction);
  if (written && fsync(directory_fd) != 0) {
    std::cerr << "failed to synchronize the private output directory\n";
    unlinkat(directory_fd, kOutputName, 0);
    written = false;
  }
  close(directory_fd);
  if (!written) {
    return 1;
  }
  std::cout << "private XT16 correction acquired; contents were not printed\n";
  return 0;
}
