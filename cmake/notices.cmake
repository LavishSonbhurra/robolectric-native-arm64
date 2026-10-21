# NOTICE file of the final shared library (tools/gen_notices.py).
#
#   ra64_notices(<target> [RUST])
#
# Called by ra64_link_runtime() (cmake/link_runtime.cmake). For target
# m_<module> it adds:
#   * <module>_notices: checks the licence metadata of everything on the link
#     line (AOSP modules from closure.json, the Rust crates of librustlibs.a,
#     the toolchain parts in config/notices-extra.toml) and writes
#     notices/<module>/link-line/NOTICE. It runs before the link, and can be
#     built on its own (`ninja libandroid_runtime_notices`).
#   * a post-link step that reads what the linker took (lld --why-extract,
#     plus the link's dependency file when CMake writes one) and writes
#     NOTICE next to the library, covering only what was linked in, and
#     notices/<module>/notices.json (inventory with hashes). An archive or
#     object in the link that has no licence entry fails the build.
#
# RA64_NOTICE_CHECK makes licence problems fatal. It defaults to ON with the
# sysroot toolchain (cmake/toolchain-sysroot.cmake), whose runtimes and
# sysroot carry the licence texts; without it the problems are warnings.

option(RA64_NOTICE "Write the NOTICE file next to the final library" ON)
if(RA64_TOOLCHAIN)
  set(_ra64_notice_check_default ON)
else()
  set(_ra64_notice_check_default OFF)
endif()
option(RA64_NOTICE_CHECK "Fail the build on licence problems in the NOTICE check" ${_ra64_notice_check_default})

set(_RA64_NOTICES_DIR "${CMAKE_CURRENT_LIST_DIR}")

function(ra64_notices target)
  cmake_parse_arguments(N "RUST" "" "" ${ARGN})
  if(NOT RA64_NOTICE)
    return()
  endif()
  get_filename_component(_root "${_RA64_NOTICES_DIR}/.." ABSOLUTE)
  string(REGEX REPLACE "^m_" "" _mod "${target}")
  set(_dir "${CMAKE_BINARY_DIR}/notices/${_mod}")
  set(_gen "${_root}/tools/gen_notices.py")

  # The target's config directory (config/ or config/compat/, CMakeLists.txt).
  set(_cfg "${_ra64_config}")
  set(_args --src "${AOSP_SRC}" --closure "${AOSP_GEN_CMAKE}/closure.json" --module "${_mod}"
      --extra "${_cfg}/notices-extra.toml" --policy "${_cfg}/notices-policy.toml"
      --var "src=${AOSP_SRC}")
  set(_deps "${_gen}" "${_root}/tools/blueprint.py" "${AOSP_GEN_CMAKE}/closure.json"
      "${_cfg}/notices-extra.toml" "${_cfg}/notices-policy.toml"
      "${_cfg}/sources.lock.json")
  # A pixel mode (RA64_PIXELS) may add components of its own.
  if(RA64_PIXELS AND NOT RA64_PIXELS STREQUAL "native"
     AND EXISTS "${_cfg}/pixels/${RA64_PIXELS}-notices.toml")
    list(APPEND _args --extra "${_cfg}/pixels/${RA64_PIXELS}-notices.toml")
    list(APPEND _deps "${_cfg}/pixels/${RA64_PIXELS}-notices.toml")
  endif()
  if(RA64_SYSROOT)
    list(APPEND _args --var "sysroot=${RA64_SYSROOT}")
  endif()
  if(RA64_RUNTIMES)
    list(APPEND _args --var "runtimes=${RA64_RUNTIMES}")
  endif()
  if(N_RUST)
    if(RUSTLIBS_RUSTC)
      get_filename_component(_rt "${RUSTLIBS_RUSTC}" DIRECTORY)
      get_filename_component(_rt "${_rt}" DIRECTORY)
      list(APPEND _args --var "rust_toolchain=${_rt}")
    endif()
    if(RA64_RUSTLIBS_ARCHIVE)
      list(APPEND _args --var "rustlibs=${RA64_RUSTLIBS_ARCHIVE}")
    elseif(RUSTLIBS_ARCHIVE)
      list(APPEND _args --var "rustlibs=${RUSTLIBS_ARCHIVE}")
    endif()
    # crates.tsv is written by tools/bp2rust.py at configure time.
    if(RUSTLIBS_DIR AND EXISTS "${RUSTLIBS_DIR}/crates.tsv")
      list(APPEND _args --rust-crates "${RUSTLIBS_DIR}/crates.tsv")
      list(APPEND _deps "${RUSTLIBS_DIR}/crates.tsv")
    endif()
  endif()
  set(_check "")
  if(RA64_NOTICE_CHECK)
    set(_check --check)
  endif()

  # Before the link: everything on the link line.
  add_custom_command(
    OUTPUT "${_dir}/link-line/NOTICE"
    COMMAND ${Python3_EXECUTABLE} -I "${_gen}" ${_args}
            --notice "${_dir}/link-line/NOTICE" --json "${_dir}/link-line/notices.json"
            --depfile "${_dir}/link-line/NOTICE.d" ${_check}
    DEPENDS ${_deps}
    DEPFILE "${_dir}/link-line/NOTICE.d"
    BYPRODUCTS "${_dir}/link-line/notices.json"
    COMMENT "notices: licence check of the ${_mod} link line"
    VERBATIM)
  add_custom_target(${_mod}_notices DEPENDS "${_dir}/link-line/NOTICE")
  add_dependencies(${target} ${_mod}_notices)

  # Module archives on the link line, for mapping the linker's inputs back
  # to modules.
  get_target_property(_libs ${target} LINK_LIBRARIES)
  set(_tsv "")
  foreach(_l IN LISTS _libs)
    if(TARGET "${_l}" AND _l MATCHES "^m_")
      get_target_property(_type "${_l}" TYPE)
      if(_type STREQUAL "STATIC_LIBRARY")
        string(REGEX REPLACE "^m_" "" _m "${_l}")
        string(APPEND _tsv "${_m}\t$<TARGET_FILE:${_l}>\n")
      endif()
    endif()
  endforeach()
  file(GENERATE OUTPUT "${_dir}/archives.tsv" CONTENT "${_tsv}")

  # After the link: what the linker took.
  get_target_property(_outdir ${target} LIBRARY_OUTPUT_DIRECTORY)
  if(NOT _outdir)
    set(_outdir "${CMAKE_CURRENT_BINARY_DIR}")
  endif()
  set(_objdir "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/${target}.dir")
  target_link_options(${target} PRIVATE "-Wl,--why-extract=${_dir}/why-extract.tsv")
  # The post-link step only runs when the target relinks, so relink when the
  # generator or its inputs change.
  set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS ${_deps})
  add_custom_command(TARGET ${target} POST_BUILD
    COMMAND ${Python3_EXECUTABLE} -I "${_gen}" ${_args}
            --archives "${_dir}/archives.tsv" --own-objects "${_objdir}"
            --why-extract "${_dir}/why-extract.tsv" --link-deps "${_objdir}/link.d"
            --build-dir "${CMAKE_BINARY_DIR}"
            --notice "${_outdir}/NOTICE" --json "${_dir}/notices.json" ${_check}
    BYPRODUCTS "${_outdir}/NOTICE" "${_dir}/notices.json" "${_dir}/why-extract.tsv"
    COMMENT "notices: ${_mod}"
    VERBATIM)
endfunction()
