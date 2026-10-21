# Link policy for the final shared library (libandroid_runtime.so).
#
#   ra64_apply_shared_link_policy(<target>
#       [VERSION_SCRIPT <file>]          # Soong's version_script
#       [ALLOW_UNDEFINED <glob>...]      # strong unversioned undefined symbols to accept
#       [NO_CHECK])                      # skip the post-link check-so.py run
#
# Call it on an add_library(<target> SHARED ...) target. It mirrors Soong's
# host linux_glibc link (cc/config/global.go hostGlobalLldflags,
# x86_linux_host.go linuxLdflags/linuxLldflags, cc/linker.go, cc/stl.go for
# stl: "libc++_static") with these differences:
#   * The C++ runtime is our libc++.a (which contains libc++abi and LLVM
#     libunwind, as AOSP's host libc++_static does), passed by path.
#   * -static-libgcc for arm64 too. libandroid_runtime only has it in
#     target.linux_glibc_x86_64, which does not apply to arm64. With
#     --unwindlib=none clang links libgcc.a (builtins, outline atomics) but
#     neither libgcc_s nor libgcc_eh, so _Unwind_* come from libunwind.
#   * No RUNPATH (Soong adds $ORIGIN/... paths; nothing we link is shared).
#   * --build-id=sha1 (Soong host links get the linker default).
# No --gc-sections: Soong passes it only with bionic toolchains
# (cc/library.go), and the official library keeps code that it would drop
# (the never-registered InputApplicationHandle JNI table).
#
# The reference x86_64 library has GNU_RELRO, BIND_NOW, a non-executable
# GNU_STACK and NEEDED libdl, libpthread, libm, librt, libc, ld-linux; the
# flags below give the same. After the link, toolchain/check-so.py verifies
# the glibc floor, NEEDED, exports against the version script and the stack.

set(_RA64_POLICY_DIR "${CMAKE_CURRENT_LIST_DIR}")

function(ra64_apply_shared_link_policy target)
  cmake_parse_arguments(P "NO_CHECK" "VERSION_SCRIPT" "ALLOW_UNDEFINED" ${ARGN})
  if(NOT RA64_TOOLCHAIN)
    message(FATAL_ERROR "ra64_apply_shared_link_policy needs -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-sysroot.cmake")
  endif()
  set(_rt "${RA64_RUNTIMES}/lib")
  if(RA64_CXX_RUNTIME STREQUAL "closure")
    # The C++ library is a module of the AOSP tree, linked as part of the
    # static closure (compat target: Android 12 external/libcxx with
    # libc++abi, Soong's libc++_static). Like Soong's Android 12 host link:
    # libgcc's unwinder (-static-libgcc: libgcc.a + libgcc_eh.a, the
    # reference's local _Unwind_* symbols), and libc++'s symbols stay
    # exported (no version script; the reference exports them too).
    target_link_options(${target} PRIVATE
      -fuse-ld=lld
      -nostdlib++ -static-libgcc
      -Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now
      -Wl,--no-undefined -Wl,--no-undefined-version
      -Wl,--build-id=sha1
      -Wl,--exclude-libs,libgcc.a -Wl,--exclude-libs,libgcc_eh.a)
  else()
  target_link_options(${target} PRIVATE
    -fuse-ld=lld
    -nostdlib++ -static-libgcc --unwindlib=none
    -Wl,--icf=safe -Wl,--no-demangle
    -Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now
    -Wl,--no-undefined -Wl,--no-undefined-version
    -Wl,--build-id=sha1
    -Wl,--compress-debug-sections=zstd
    # Keep the static C++ runtime and libgcc out of the dynamic symbol table
    # even if a version script pattern is too wide.
    -Wl,--exclude-libs,libc++.a -Wl,--exclude-libs,libgcc.a -Wl,--exclude-libs,libgcc_eh.a)
  endif()
  if(P_VERSION_SCRIPT)
    get_filename_component(_vs "${P_VERSION_SCRIPT}" ABSOLUTE)
    target_link_options(${target} PRIVATE "-Wl,--version-script,${_vs}")
    set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS "${_vs}")
  endif()
  # Soong's host order: the C++ runtime after everything else, then
  # -ldl -lpthread -lm -lrt (cc/linker.go), libc from the driver.
  if(RA64_CXX_RUNTIME STREQUAL "closure")
    target_link_libraries(${target} PRIVATE -ldl -lpthread -lm -lrt)
  else()
    target_link_libraries(${target} PRIVATE "${_rt}/libc++.a" -ldl -lpthread -lm -lrt)
  endif()
  set_target_properties(${target} PROPERTIES
    LINKER_LANGUAGE CXX
    SKIP_BUILD_RPATH TRUE
    INSTALL_RPATH ""
    BUILD_WITH_INSTALL_RPATH FALSE)
  if(NOT P_NO_CHECK)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    set(_check ${Python3_EXECUTABLE} -I "${_RA64_POLICY_DIR}/../toolchain/check-so.py"
        --floor ${RA64_GLIBC_FLOOR})
    if(P_VERSION_SCRIPT)
      list(APPEND _check --version-script "${_vs}")
    endif()
    foreach(_u IN LISTS P_ALLOW_UNDEFINED)
      list(APPEND _check --allow-undefined "${_u}")
    endforeach()
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND ${_check} "$<TARGET_FILE:${target}>"
      COMMENT "check-so: ${target}" VERBATIM)
  endif()
endfunction()
