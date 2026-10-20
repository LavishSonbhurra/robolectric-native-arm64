include("${CMAKE_CURRENT_LIST_DIR}/notices.cmake")

# Inputs of the final libandroid_runtime.so link that do not come from
# Android.bp: the static C++ runtime, the UBSan minimal runtime and the Rust
# staticlib. Each is a cache variable or an imported target so that the
# toolchain file (cmake/toolchain-sysroot.cmake) and the Rust build
# (rust/rustlibs.cmake) can provide them. Defaults use the system clang.

# Soong links host shared libraries with stl "libc++_static": -nostdlib++
# plus libc++ and libc++abi as static archives (and LLVM libunwind, which
# the official library contains). The toolchain file should set this to its
# own static libc++.a;libc++abi.a;libunwind.a.
set(RA64_CXX_RUNTIME_LIBS "" CACHE STRING
    "Static C++ runtime archives for the shared library link (empty: system libc++.a, libc++abi.a)")
if(RA64_TOOLCHAIN)
  # cmake/toolchain-sysroot.cmake: ra64_apply_shared_link_policy()
  # links its own libc++.a (with libc++abi and libunwind).
elseif(NOT RA64_CXX_RUNTIME_LIBS)
  set(_libs "")
  foreach(_a libc++.a libc++abi.a)
    execute_process(COMMAND ${CMAKE_CXX_COMPILER} -print-file-name=${_a}
                    OUTPUT_VARIABLE _p OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(NOT IS_ABSOLUTE "${_p}")
      execute_process(COMMAND ${CMAKE_CXX_COMPILER} -stdlib=libc++ -print-file-name=${_a}
                      OUTPUT_VARIABLE _p OUTPUT_STRIP_TRAILING_WHITESPACE)
    endif()
    if(NOT IS_ABSOLUTE "${_p}")
      message(FATAL_ERROR "cannot find ${_a}; set RA64_CXX_RUNTIME_LIBS")
    endif()
    list(APPEND _libs "${_p}")
  endforeach()
  set(RA64_CXX_RUNTIME_LIBS "${_libs}")
endif()

# compiler-rt's UBSan minimal runtime (Soong:
# UndefinedBehaviorSanitizerMinimalRuntimeLibrary, linked with hidden
# symbols into any shared library with a sanitized static dependency).
set(RA64_UBSAN_MINIMAL_RUNTIME "" CACHE FILEPATH
    "libclang_rt.ubsan_minimal archive for the target (empty: from the compiler's resource dir)")
if(NOT RA64_UBSAN_MINIMAL_RUNTIME AND RA64_UBSAN_MINIMAL_TOOLCHAIN AND EXISTS "${RA64_UBSAN_MINIMAL_TOOLCHAIN}")
  # Built with the C++ runtimes for the target (toolchain/build-runtimes.sh).
  set(RA64_UBSAN_MINIMAL_RUNTIME "${RA64_UBSAN_MINIMAL_TOOLCHAIN}")
endif()
if(NOT RA64_UBSAN_MINIMAL_RUNTIME)
  if(RA64_ARCH STREQUAL "x86_64")
    set(_cpu x86_64)
  else()
    set(_cpu aarch64)
  endif()
  execute_process(COMMAND ${CMAKE_CXX_COMPILER} -print-resource-dir
                  OUTPUT_VARIABLE _rd OUTPUT_STRIP_TRAILING_WHITESPACE)
  foreach(_c "${_rd}/lib/linux/libclang_rt.ubsan_minimal-${_cpu}.a"
             "${_rd}/lib/${_cpu}-unknown-linux-gnu/libclang_rt.ubsan_minimal.a")
    if(EXISTS "${_c}" AND NOT RA64_UBSAN_MINIMAL_RUNTIME)
      set(RA64_UBSAN_MINIMAL_RUNTIME "${_c}")
    endif()
  endforeach()
endif()

# The Rust code (one staticlib, librustlibs.a, as Soong's
# GenerateRustStaticlib makes for every cc_library_shared with Rust deps)
# comes from the rust track as the imported target `rustlibs`
# (rust/rustlibs.cmake) or RA64_RUSTLIBS_ARCHIVE. Without it the link
# fails and lists every Rust symbol it needs (-Wl,--error-limit=0).

# Soong adds -Wl,--gc-sections to shared libraries only for bionic
# toolchains (cc/library.go); a linux_glibc host library is linked without
# it, and host code is not compiled with -ffunction-sections either. Off by
# default for parity; on, it drops unreferenced sections of objects that are
# pulled in for other symbols.
option(RA64_GC_SECTIONS "Link libandroid_runtime with --gc-sections (Soong does not on glibc hosts)" OFF)

function(ra64_link_runtime target)
  cmake_parse_arguments(A "" "RUST;UBSAN_MINIMAL;VERSION_SCRIPT" "" ${ARGN})
  if(RA64_TOOLCHAIN)
    # The toolchain track's policy: static libc++/libunwind, -static-libgcc
    # --unwindlib=none, no RUNPATH, and toolchain/check-so.py after the link
    # (glibc floor, NEEDED, exports, stack). It overrides the Soong rpaths
    # emitted by bp2cmake.
    ra64_apply_shared_link_policy(${target} VERSION_SCRIPT "${A_VERSION_SCRIPT}")
  elseif(A_VERSION_SCRIPT)
    target_link_options(${target} PRIVATE "-Wl,--version-script,${A_VERSION_SCRIPT}")
  endif()
  if(RA64_GC_SECTIONS)
    target_link_options(${target} PRIVATE -Wl,--gc-sections)
  endif()
  if(A_RUST)
    if(TARGET rustlibs)
      target_link_libraries(${target} PRIVATE rustlibs)
    else()
      message(WARNING "${target}: no `rustlibs` target; the link will report the missing Rust symbols")
      target_link_options(${target} PRIVATE -Wl,--error-limit=0)
    endif()
  endif()
  if(A_UBSAN_MINIMAL)
    if(NOT RA64_UBSAN_MINIMAL_RUNTIME)
      message(FATAL_ERROR "libclang_rt.ubsan_minimal not found; set RA64_UBSAN_MINIMAL_RUNTIME")
    endif()
    get_filename_component(_n "${RA64_UBSAN_MINIMAL_RUNTIME}" NAME)
    target_link_libraries(${target} PRIVATE "${RA64_UBSAN_MINIMAL_RUNTIME}")
    target_link_options(${target} PRIVATE "-Wl,--exclude-libs=${_n}")
  endif()
  if(NOT RA64_TOOLCHAIN)
    target_link_libraries(${target} PRIVATE ${RA64_CXX_RUNTIME_LIBS})
  endif()
  # NOTICE next to the library, and the licence check (cmake/notices.cmake).
  if(A_RUST)
    ra64_notices(${target} RUST)
  else()
    ra64_notices(${target})
  endif()
endfunction()
