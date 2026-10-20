# librustlibs.a: the Rust part of libandroid_runtime, as one staticlib (Rust
# std plus every live crate), built with rustc 1.83.0 from the Android.bp
# files by tools/bp2rust.py. See docs/NOTES.md, "Rust".
#
# Use from the top-level CMakeLists.txt, after AOSP_SRC is set:
#
#   set(RUSTLIBS_CXXBRIDGE "${CMAKE_BINARY_DIR}/rust/target/release/cxxbridge")
#   set(RUSTLIBS_CXXBRIDGE_TARGET cxxbridge_tool)   # if built by this project
#   include(rust/rustlibs.cmake)
#   target_link_libraries(android_runtime PRIVATE ... rustlibs)
#
# Optional inputs:
#   RUSTLIBS_RUSTC    rustc 1.83.0 (default: rust/toolchain/bin/rustc, from
#                     rust/install-toolchain.sh)
#   RUSTLIBS_HOST_CC  linker driver for host proc macros (default: clang)
#   RUSTLIBS_JOBS     parallel rustc jobs (default: 2)
#   RA64_ARCH         target architecture (arm64 or x86_64; the std for a
#                     non-native target comes from
#                     rust/install-toolchain.sh --target <triple>)
#
# Provides:
#   rustlibs                    IMPORTED STATIC library: librustlibs.a, with
#                               the generated cxx headers (rust/cxx.h,
#                               minikin_cxx_bridge.rs.h) as interface
#                               include dirs.
#   rustlibs_build              the target that builds it (and the headers).
#   RUSTLIBS_GEN_INCLUDE_DIRS   the generated header dirs.
#   RUSTLIBS_GEN_SOURCES        generated C++ bridge code
#                               (minikin_cxx_bridge_generated.cpp); Soong
#                               compiles it into libminikin_from_rust_to_cpp.
#   RUSTLIBS_CC_DEPS            C++ modules the Rust code needs at link time
#                               (whole_static_libs/static_libs of the live
#                               Rust modules): libcxxbridge05 (cxx.cc) and
#                               libminikin_from_rust_to_cpp.
#
# librustlibs.a is not linked with --whole-archive: like Soong, the C++
# objects pull in what they reference.

if(NOT DEFINED AOSP_SRC)
  set(AOSP_SRC "${CMAKE_SOURCE_DIR}/src")
endif()
if(NOT RUSTLIBS_RUSTC)
  set(RUSTLIBS_RUSTC "${CMAKE_CURRENT_LIST_DIR}/toolchain/bin/rustc")
endif()
if(NOT EXISTS "${RUSTLIBS_RUSTC}")
  message(FATAL_ERROR "rustc 1.83.0 not found at ${RUSTLIBS_RUSTC}; run rust/install-toolchain.sh")
endif()
if(NOT RUSTLIBS_CXXBRIDGE)
  message(FATAL_ERROR "set RUSTLIBS_CXXBRIDGE to a cxxbridge 1.0.119 binary before including rustlibs.cmake")
endif()
if(NOT RUSTLIBS_HOST_CC)
  find_program(RUSTLIBS_HOST_CC clang REQUIRED)
endif()
if(NOT RUSTLIBS_JOBS)
  set(RUSTLIBS_JOBS 2)
endif()
if(CMAKE_GENERATOR MATCHES "Ninja")
  set(_rustlibs_ninja "${CMAKE_MAKE_PROGRAM}")
else()
  find_program(_rustlibs_ninja ninja REQUIRED)
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(RUSTLIBS_DIR "${CMAKE_BINARY_DIR}/rustlibs")
# Target architecture (RA64_ARCH); proc macros are always built for the
# build machine.
set(_rustlibs_arch "")
if(RA64_ARCH)
  set(_rustlibs_arch --arch ${RA64_ARCH})
endif()
execute_process(
  COMMAND ${Python3_EXECUTABLE} -I "${CMAKE_CURRENT_LIST_DIR}/../tools/bp2rust.py"
          --out "${RUSTLIBS_DIR}" --rustc "${RUSTLIBS_RUSTC}"
          --cxxbridge "${RUSTLIBS_CXXBRIDGE}" --host-cc "${RUSTLIBS_HOST_CC}"
          ${_rustlibs_arch}
  RESULT_VARIABLE _bp2rust_rc)
if(NOT _bp2rust_rc EQUAL 0)
  message(FATAL_ERROR "tools/bp2rust.py failed")
endif()
include("${RUSTLIBS_DIR}/rustlibs-vars.cmake")
# Normalized paths: the top-level CMakeLists.txt also lists tools/*.py, and
# Ninja rejects the same file spelled twice (rust/../tools/x.py vs tools/x.py).
get_filename_component(_rustlibs_tools "${CMAKE_CURRENT_LIST_DIR}/../tools" ABSOLUTE)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  ${RUSTLIBS_CONFIGURE_DEPENDS}
  "${_rustlibs_tools}/bp2rust.py"
  "${_rustlibs_tools}/bp2cmake.py"
  "${_rustlibs_tools}/blueprint.py")

# The inner Ninja file tracks every .rs input through rustc's dep-info, so
# it runs on every build and is a no-op when nothing changed. It must run
# from the source root (see tools/bp2rust.py).
add_custom_target(rustlibs_build
  COMMAND "${_rustlibs_ninja}" -C "${AOSP_SRC}" -f "${RUSTLIBS_DIR}/build.ninja" -j ${RUSTLIBS_JOBS}
  BYPRODUCTS "${RUSTLIBS_ARCHIVE}" ${RUSTLIBS_GEN_OUTPUTS}
  COMMENT "Rust: librustlibs.a (rustc 1.83.0)"
  USES_TERMINAL VERBATIM)
if(RUSTLIBS_CXXBRIDGE_TARGET)
  add_dependencies(rustlibs_build ${RUSTLIBS_CXXBRIDGE_TARGET})
endif()

add_library(rustlibs STATIC IMPORTED GLOBAL)
# Interface include dirs of an imported target must exist at generate time.
file(MAKE_DIRECTORY ${RUSTLIBS_GEN_INCLUDE_DIRS})
set_target_properties(rustlibs PROPERTIES
  IMPORTED_LOCATION "${RUSTLIBS_ARCHIVE}"
  INTERFACE_INCLUDE_DIRECTORIES "${RUSTLIBS_GEN_INCLUDE_DIRS}")
add_dependencies(rustlibs rustlibs_build)
