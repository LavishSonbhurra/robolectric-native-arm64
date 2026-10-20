// Exercises the parts of the C++ runtime a JNI library uses: exceptions
// (libc++abi + libunwind), iostreams and locale, threads, thread_local
// destructors (__cxa_thread_atexit_impl), filesystem, and a few libc calls.
#include <cstdlib>
#include <cstdio>
#include <filesystem>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
struct Tls {
  std::string s = "tls";
  ~Tls() {}
};
thread_local Tls tls;
std::mutex mu;

int thrower(int x) {
  if (x > 1) throw std::runtime_error("boom " + std::to_string(x));
  return x;
}
}  // namespace

extern "C" __attribute__((visibility("default"))) int sample_run(const char* arg) {
  int total = 0;
  try {
    thrower(std::atoi(arg));
  } catch (const std::exception& e) {
    total += static_cast<int>(std::string(e.what()).size());
  }
  std::vector<std::thread> ts;
  for (int i = 0; i < 3; i++) {
    ts.emplace_back([&total, i] {
      std::lock_guard<std::mutex> l(mu);
      total += i + static_cast<int>(tls.s.size());
    });
  }
  for (auto& t : ts) t.join();
  std::ostringstream os;
  os << 1.5 << " " << std::strtol("42", nullptr, 10);
  total += static_cast<int>(os.str().size());
  total += std::filesystem::exists("/") ? 1 : 0;
  return total;
}
