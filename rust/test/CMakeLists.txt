# Link test for rust/rustlibs.cmake: builds librustlibs.a through the CMake
# interface, compiles the C++ halves of the live cxx bridges, and links an
# executable and a shared library (-Wl,--no-undefined) against it.
#
#   cmake -S rust/test -B build/rust-test -G Ninja \
#         -DRUSTLIBS_CXXBRIDGE=/path/to/cxxbridge [-DCMAKE_CXX_FLAGS=...]
#   ninja -C build/rust-test && build/rust-test/rustlibs_link_test
cmake_minimum_required(VERSION 3.25)
project(rustlibs_link_test LANGUAGES CXX)

get_filename_component(AOSP_SRC "${CMAKE_CURRENT_LIST_DIR}/../../src" ABSOLUTE)
include("${CMAKE_CURRENT_LIST_DIR}/../rustlibs.cmake")

# libcxxbridge05 (external/rust/cxx/Android.bp) and the generated part of
# libminikin_from_rust_to_cpp. Soong builds both as C++20 with
# -DRUST_CXX_NO_EXCEPTIONS for cxx.cc.
add_library(rust_bridges_cc OBJECT
  "${AOSP_SRC}/external/rust/cxx/src/cxx.cc"
  ${RUSTLIBS_GEN_SOURCES}
  link_test.cpp)
set_source_files_properties("${AOSP_SRC}/external/rust/cxx/src/cxx.cc"
  PROPERTIES COMPILE_DEFINITIONS RUST_CXX_NO_EXCEPTIONS)
target_compile_features(rust_bridges_cc PRIVATE cxx_std_20)
set_target_properties(rust_bridges_cc PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(rust_bridges_cc PRIVATE
  "${AOSP_SRC}/frameworks/minikin/libs/minikin"
  $<TARGET_PROPERTY:rustlibs,INTERFACE_INCLUDE_DIRECTORIES>)
add_dependencies(rust_bridges_cc rustlibs_build)

set(RUSTLIBS_TEST_LIBS "" CACHE STRING "extra link libraries (C++ runtime, unwinder)")

add_executable(rustlibs_link_test $<TARGET_OBJECTS:rust_bridges_cc>)
target_link_libraries(rustlibs_link_test PRIVATE rustlibs ${RUSTLIBS_TEST_LIBS} pthread dl m)

add_library(rustlibs_link_test_shared SHARED $<TARGET_OBJECTS:rust_bridges_cc>)
target_link_libraries(rustlibs_link_test_shared PRIVATE rustlibs ${RUSTLIBS_TEST_LIBS} pthread dl m)
target_link_options(rustlibs_link_test_shared PRIVATE -Wl,--no-undefined)
