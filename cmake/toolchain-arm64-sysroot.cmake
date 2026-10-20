# Kept for existing build directories: the arm64 case of
# cmake/toolchain-sysroot.cmake.
if(NOT RA64_ARCH AND NOT DEFINED ENV{RA64_ARCH})
  set(RA64_ARCH arm64)
endif()
include("${CMAKE_CURRENT_LIST_DIR}/toolchain-sysroot.cmake")
