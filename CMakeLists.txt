cmake_minimum_required(VERSION 3.25)

# The compile flags are Soong's, assembled by tools/bp2cmake.py into one
# response file per module and language. Keep CMake from adding its own.
set(CMAKE_C_FLAGS_INIT "")
set(CMAKE_CXX_FLAGS_INIT "")
set(CMAKE_ASM_FLAGS_INIT "")
if(NOT CMAKE_C_COMPILER)
  set(CMAKE_C_COMPILER clang)
endif()
if(NOT CMAKE_CXX_COMPILER)
  set(CMAKE_CXX_COMPILER clang++)
endif()
if(NOT CMAKE_ASM_COMPILER)
  set(CMAKE_ASM_COMPILER clang)
endif()
set(CMAKE_BUILD_TYPE "" CACHE STRING "Unused: flags come from Soong" FORCE)

# Target architecture: arm64 (default) or x86_64. x86_64 on an arm64 build
# machine is a cross build and needs RA64_USE_SYSROOT=ON and
# RA64_HOST_TOOLS_DIR (docs/NOTES.md, "Architectures").
set(RA64_ARCH "arm64" CACHE STRING "Target architecture: arm64 or x86_64")
set_property(CACHE RA64_ARCH PROPERTY STRINGS arm64 x86_64)

# Portable build against the glibc 2.31 sysroot (docs/NOTES.md, "Toolchain"). Same
# as passing -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-sysroot.cmake.
option(RA64_USE_SYSROOT "Build with cmake/toolchain-sysroot.cmake" OFF)
if(RA64_USE_SYSROOT AND NOT CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "${CMAKE_CURRENT_SOURCE_DIR}/cmake/toolchain-sysroot.cmake")
endif()

project(robolectric_arm64 LANGUAGES C CXX ASM)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(NOT RA64_TOOLCHAIN AND NOT RA64_ARCH STREQUAL "arm64")
  message(FATAL_ERROR "RA64_ARCH=${RA64_ARCH} needs -DRA64_USE_SYSROOT=ON")
endif()
# The code generators (aidl, aidl-cpp, aprotoc, sysprop_cpp) run on the
# build machine. A cross build takes them from a native build of the same
# tree (its bin/ directory) instead of building them for the target.
set(RA64_HOST_TOOLS_DIR "" CACHE PATH "Native host tools for a cross build (bin/ of a native build)")
set(_bp2cmake_extra --arch ${RA64_ARCH})
if(RA64_HOST_TOOLS_DIR)
  list(APPEND _bp2cmake_extra --host-tools-dir "${RA64_HOST_TOOLS_DIR}")
elseif(CMAKE_CROSSCOMPILING)
  message(FATAL_ERROR "cross build (RA64_ARCH=${RA64_ARCH}): set RA64_HOST_TOOLS_DIR to the bin/ directory of a native build")
endif()

set(AOSP_SRC "${CMAKE_SOURCE_DIR}/src")
set(AOSP_GEN_CMAKE "${CMAKE_BINARY_DIR}/cmake-gen")

# Generate the module and generator CMake from Android.bp at configure time.
execute_process(
  COMMAND ${Python3_EXECUTABLE} -I "${CMAKE_SOURCE_DIR}/tools/bp2cmake.py"
          --out "${AOSP_GEN_CMAKE}" --binary-dir "${CMAKE_BINARY_DIR}"
          --cmake-command "${CMAKE_COMMAND}" ${_bp2cmake_extra}
  RESULT_VARIABLE _bp2cmake_rc)
if(NOT _bp2cmake_rc EQUAL 0)
  message(FATAL_ERROR "tools/bp2cmake.py failed")
endif()
file(GLOB _tool_sources "${CMAKE_SOURCE_DIR}/tools/*.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_SOURCE_DIR}/config/aosp.toml"
  "${CMAKE_SOURCE_DIR}/config/sources.lock.json"
  "${CMAKE_SOURCE_DIR}/overrides/overrides.toml"
  ${_tool_sources})

include(cmake/host_tools.cmake)
include(cmake/link_runtime.cmake)
# Rust staticlib (target `rustlibs`): built by rust/rustlibs.cmake (the rust
# track) when present, or imported from a prebuilt archive for testing
# (RA64_RUSTLIBS_ARCHIVE). Its C++ halves (libcxxbridge05,
# libminikin_from_rust_to_cpp with the generated minikin bridge code, i.e.
# RUSTLIBS_CC_DEPS and RUSTLIBS_GEN_SOURCES) are built by the generated
# CMake from Android.bp, so they are not added again here.
set(RA64_RUSTLIBS_ARCHIVE "" CACHE FILEPATH "Prebuilt librustlibs.a to link instead of building it (testing)")
if(RA64_RUSTLIBS_ARCHIVE)
  add_library(rustlibs STATIC IMPORTED GLOBAL)
  set_target_properties(rustlibs PROPERTIES IMPORTED_LOCATION "${RA64_RUSTLIBS_ARCHIVE}")
elseif(EXISTS "${CMAKE_SOURCE_DIR}/rust/rustlibs.cmake")
  set(RUSTLIBS_CXXBRIDGE "${CMAKE_BINARY_DIR}/rust/target/release/cxxbridge")
  set(RUSTLIBS_CXXBRIDGE_TARGET cxxbridge_tool)
  include(rust/rustlibs.cmake)
endif()
include("${AOSP_GEN_CMAKE}/generators.cmake")
include("${AOSP_GEN_CMAKE}/modules.cmake")
