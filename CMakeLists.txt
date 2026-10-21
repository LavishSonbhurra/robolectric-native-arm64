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

# Which library to build (tools/target.py): sdk36 (libandroid_runtime.so for
# SDK 36, the default) or compat (librobolectric-nativeruntime.so for
# SDK <= 34, from android12-hostruntime-dev, inputs under config/compat/).
set(RA64_TARGET "sdk36" CACHE STRING "Library to build: sdk36 or compat")
set_property(CACHE RA64_TARGET PROPERTY STRINGS sdk36 compat)
set(ENV{RA64_TARGET} "${RA64_TARGET}")
if(RA64_TARGET STREQUAL "sdk36")
  set(_ra64_config "${CMAKE_SOURCE_DIR}/config")
  set(_ra64_overrides "${CMAKE_SOURCE_DIR}/overrides/overrides.toml")
  set(AOSP_SRC "${CMAKE_SOURCE_DIR}/src")
elseif(RA64_TARGET STREQUAL "compat")
  # C++ library from the tree (config/compat/overrides.toml [toolchain]
  # stl_module), not the toolchain's libc++ 21 (cmake/ra64_link_policy.cmake).
  set(RA64_CXX_RUNTIME "closure")
  set(_ra64_config "${CMAKE_SOURCE_DIR}/config/compat")
  set(_ra64_overrides "${_ra64_config}/overrides.toml")
  set(AOSP_SRC "${CMAKE_SOURCE_DIR}/src-compat")
else()
  message(FATAL_ERROR "RA64_TARGET must be sdk36 or compat, not ${RA64_TARGET}")
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(NOT RA64_TOOLCHAIN AND NOT RA64_ARCH STREQUAL "arm64")
  message(FATAL_ERROR "RA64_ARCH=${RA64_ARCH} needs -DRA64_USE_SYSROOT=ON")
endif()
# The code generators (aidl, aidl-cpp, aprotoc, sysprop_cpp) run on the
# build machine. A cross build takes them from a native build of the same
# tree (its bin/ directory) instead of building them for the target.
set(RA64_HOST_TOOLS_DIR "" CACHE PATH "Native host tools for a cross build (bin/ of a native build)")
set(_bp2cmake_extra --arch ${RA64_ARCH})
# Pixel mode (compat target; config/compat/overrides.toml [pixels.<mode>]):
# native (default) builds Skia's own code paths for the target CPU.
set(RA64_PIXELS "native" CACHE STRING "Pixel mode: native, or a [pixels.<mode>] of the overrides file")
if(NOT RA64_PIXELS STREQUAL "native")
  list(APPEND _bp2cmake_extra --pixels ${RA64_PIXELS})
endif()
if(RA64_HOST_TOOLS_DIR)
  list(APPEND _bp2cmake_extra --host-tools-dir "${RA64_HOST_TOOLS_DIR}")
elseif(CMAKE_CROSSCOMPILING)
  message(FATAL_ERROR "cross build (RA64_ARCH=${RA64_ARCH}): set RA64_HOST_TOOLS_DIR to the bin/ directory of a native build")
endif()

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
  "${_ra64_config}/aosp.toml"
  "${_ra64_config}/sources.lock.json"
  "${_ra64_overrides}"
  ${_tool_sources})

# The compat closure has no Rust and no aconfig: no cargo host tools.
if(RA64_TARGET STREQUAL "sdk36")
  include(cmake/host_tools.cmake)
endif()
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
elseif(RA64_TARGET STREQUAL "sdk36" AND EXISTS "${CMAKE_SOURCE_DIR}/rust/rustlibs.cmake")
  set(RUSTLIBS_CXXBRIDGE "${CMAKE_BINARY_DIR}/rust/target/release/cxxbridge")
  set(RUSTLIBS_CXXBRIDGE_TARGET cxxbridge_tool)
  include(rust/rustlibs.cmake)
endif()
include("${AOSP_GEN_CMAKE}/generators.cmake")
include("${AOSP_GEN_CMAKE}/modules.cmake")
