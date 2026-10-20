# Toolchain file: system clang and lld, compiling and linking against a
# Debian 11 sysroot (glibc 2.31) from toolchain/make-sysroot.py and the
# static libc++/libc++abi/libunwind from toolchain/build-runtimes.sh.
#
#   cmake -S . -B build/out -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-sysroot.cmake [-DRA64_ARCH=x86_64]
#
# RA64_ARCH (cache or environment variable): arm64 (default) or x86_64.
# x86_64 on an arm64 machine is a cross build (CMAKE_CROSSCOMPILING); its
# host tools come from a native build (RA64_HOST_TOOLS_DIR, see
# CMakeLists.txt).
#
# Optional overrides (cache variables or environment variables of the same
# name): RA64_SYSROOT, RA64_RUNTIMES.
#
# What it sets:
#   compile: --target=<triple> --sysroot=<sysroot>
#            --gcc-install-dir=<sysroot>/usr/lib/gcc/<triple>/10
#            C++ also: -stdlib++-isystem <runtimes>/include/c++/v1
#   link:    -fuse-ld=lld, the same sysroot and GCC dir, -L<runtimes>/lib,
#            -stdlib=libc++ (libc++.a only exists statically, and contains
#            libc++abi and libunwind)
#
# -stdlib++-isystem replaces clang's default C++ library include directory
# in place, so the search order is the same as with the system libc++, and
# -nostdinc++ (Soong's stl: "none") still removes it.
#
# For the final shared library, use ra64_apply_shared_link_policy() from
# cmake/ra64_link_policy.cmake, which is included automatically below.
#
# Variables for other build steps (Rust build scripts, custom commands):
#   RA64_TOOLCHAIN (TRUE), RA64_TRIPLE, RA64_SYSROOT, RA64_RUNTIMES,
#   RA64_GCC_INSTALL_DIR, RA64_GLIBC_FLOOR, RA64_C_FLAGS, RA64_CXX_FLAGS,
#   RA64_LINK_FLAGS (space separated strings).

set(RA64_TOOLCHAIN TRUE)
set(RA64_GLIBC_FLOOR 2.31)
get_filename_component(_ra64_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

foreach(_v RA64_ARCH RA64_SYSROOT RA64_RUNTIMES)
  if(NOT ${_v} AND DEFINED ENV{${_v}})
    set(${_v} "$ENV{${_v}}")
  endif()
endforeach()
if(NOT RA64_ARCH)
  set(RA64_ARCH arm64)
endif()
if(RA64_ARCH STREQUAL "arm64")
  set(RA64_TRIPLE aarch64-linux-gnu)
  set(_ra64_cpu aarch64)
  set(_ra64_deb arm64)
  set(_ra64_rt_suffix "")
elseif(RA64_ARCH STREQUAL "x86_64")
  set(RA64_TRIPLE x86_64-linux-gnu)
  set(_ra64_cpu x86_64)
  set(_ra64_deb amd64)
  set(_ra64_rt_suffix "-x86_64")
else()
  message(FATAL_ERROR "RA64_ARCH must be arm64 or x86_64, not ${RA64_ARCH}")
endif()
if(NOT RA64_SYSROOT)
  set(RA64_SYSROOT "${_ra64_root}/toolchain/out/sysroot-bullseye-${_ra64_deb}")
endif()
if(NOT RA64_RUNTIMES)
  set(RA64_RUNTIMES "${_ra64_root}/toolchain/out/runtimes${_ra64_rt_suffix}")
endif()
set(RA64_ARCH "${RA64_ARCH}" CACHE STRING "Target architecture: arm64 or x86_64")
set(RA64_SYSROOT "${RA64_SYSROOT}" CACHE PATH "Debian 11 sysroot (toolchain/make-sysroot.py)")
set(RA64_RUNTIMES "${RA64_RUNTIMES}" CACHE PATH "libc++ install prefix (toolchain/build-runtimes.sh)")
# try_compile projects re-read this file; hand the settings down.
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES RA64_ARCH RA64_SYSROOT RA64_RUNTIMES)

if(NOT EXISTS "${RA64_SYSROOT}/.ra64-sysroot.json")
  message(FATAL_ERROR "No sysroot at ${RA64_SYSROOT}; run: python3 -I toolchain/make-sysroot.py --arch ${_ra64_deb}")
endif()
if(NOT EXISTS "${RA64_RUNTIMES}/lib/libc++.a")
  message(FATAL_ERROR "No libc++ at ${RA64_RUNTIMES}; run: toolchain/build-runtimes.sh --arch ${RA64_ARCH}")
endif()

# Building for another CPU than the build machine's: tell CMake, so that
# CMAKE_CROSSCOMPILING is set and nothing tries to run target programs.
cmake_host_system_information(RESULT _ra64_host_cpu QUERY OS_PLATFORM)
if(NOT _ra64_host_cpu STREQUAL _ra64_cpu)
  set(CMAKE_SYSTEM_NAME Linux)
  set(CMAKE_SYSTEM_PROCESSOR ${_ra64_cpu})
endif()
# libclang_rt.ubsan_minimal for the target, from build-runtimes.sh. The
# system clang only ships the build machine's; link_runtime.cmake falls back
# to it when this does not exist.
set(RA64_UBSAN_MINIMAL_TOOLCHAIN "${RA64_RUNTIMES}/lib/linux/libclang_rt.ubsan_minimal-${_ra64_cpu}.a")
set(RA64_GCC_INSTALL_DIR "${RA64_SYSROOT}/usr/lib/gcc/${RA64_TRIPLE}/10")

set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_ASM_COMPILER clang)
foreach(_lang C CXX ASM)
  set(CMAKE_${_lang}_COMPILER_TARGET ${RA64_TRIPLE})
endforeach()
set(CMAKE_SYSROOT "${RA64_SYSROOT}")

# CMake adds --target and --sysroot itself (CMAKE_<LANG>_COMPILER_TARGET,
# CMAKE_SYSROOT); the RA64_* strings below are complete, for tools outside
# CMake (cargo build scripts, the cc crate).
set(_ra64_c "--gcc-install-dir=${RA64_GCC_INSTALL_DIR}")
set(_ra64_cxx "${_ra64_c} -stdlib++-isystem ${RA64_RUNTIMES}/include/c++/v1")
set(_ra64_link "-fuse-ld=lld --gcc-install-dir=${RA64_GCC_INSTALL_DIR} -L${RA64_RUNTIMES}/lib -stdlib=libc++")
set(_ra64_common "--target=${RA64_TRIPLE} --sysroot=${RA64_SYSROOT}")
set(RA64_C_FLAGS "${_ra64_common} ${_ra64_c}")
set(RA64_CXX_FLAGS "${_ra64_common} ${_ra64_c} -nostdinc++ -isystem ${RA64_RUNTIMES}/include/c++/v1")
set(RA64_LINK_FLAGS "${_ra64_common} ${_ra64_link}")

# The top-level CMakeLists.txt empties the *_FLAGS_INIT variables before
# project(); this file is read inside project(), so these values win.
# tools/soong_flags.py (run by bp2cmake at configure time) reads this and
# emits Soong's own STL flags, -nostdinc++ -isystem <libc++ headers>, in
# place of -stdlib=libc++. Clang does not claim -stdlib=libc++ when
# -stdlib++-isystem is given, so the plain flag would trip -Werror.
set(ENV{RA64_LIBCXX_INCLUDE} "${RA64_RUNTIMES}/include/c++/v1")
set(CMAKE_C_FLAGS_INIT "${_ra64_c}")
set(CMAKE_CXX_FLAGS_INIT "${_ra64_cxx}")
set(CMAKE_ASM_FLAGS_INIT "${_ra64_c}")
foreach(_kind EXE SHARED MODULE)
  set(CMAKE_${_kind}_LINKER_FLAGS_INIT "${_ra64_link}")
endforeach()

# Build-time programs (python3, bison, ...) come from the host; libraries
# and headers only from the sysroot, so nothing from the host's glibc 2.43
# world can leak into the link.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# Make the link policy available to the project (include() of a module from
# a toolchain file is fine; it only defines functions).
include("${CMAKE_CURRENT_LIST_DIR}/ra64_link_policy.cmake")
