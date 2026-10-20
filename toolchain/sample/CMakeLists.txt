# Sample for the toolchain: a small C++ shared library linked with the
# final-library link policy, plus a program that loads it.
#   cmake -S toolchain/sample -B toolchain/build/sample -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=$PWD/cmake/toolchain-sysroot.cmake
cmake_minimum_required(VERSION 3.25)
project(ra64_sample LANGUAGES C CXX)
add_library(sample SHARED sample.cpp)
target_compile_options(sample PRIVATE -fPIC -std=gnu++20 -O2 -fvisibility=hidden -ffunction-sections -fdata-sections)
if(RA64_TOOLCHAIN)
  ra64_apply_shared_link_policy(sample VERSION_SCRIPT ${CMAKE_CURRENT_SOURCE_DIR}/sample.map)
else()
  target_link_options(sample PRIVATE -fuse-ld=lld -stdlib=libc++ -static-libstdc++
                      -Wl,--version-script,${CMAKE_CURRENT_SOURCE_DIR}/sample.map)
endif()
add_executable(sample_main main.c)
target_link_libraries(sample_main PRIVATE -ldl)
