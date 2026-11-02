# Rust host tools and libraries, built with cargo from the fetched AOSP
# sources (see tools/cargo_build.py). Soong builds these with rustc directly;
# the upstream crates also ship Cargo.toml files, which we use instead.

set(AOSP_RUST_STAGE "${CMAKE_BINARY_DIR}/rust/tree")
set(AOSP_RUST_TARGET "${CMAKE_BINARY_DIR}/rust/target")
set(_cargo_build ${Python3_EXECUTABLE} -I "${CMAKE_SOURCE_DIR}/tools/cargo_build.py"
    --stage "${AOSP_RUST_STAGE}" --target-dir "${AOSP_RUST_TARGET}")
# Workspace manifest and lock files: the target's own when it has them.
set(_cargo_dir "${CMAKE_SOURCE_DIR}/tools/cargo")
if(EXISTS "${_ra64_config}/cargo")
  set(_cargo_dir "${_ra64_config}/cargo")
endif()

# aconfig code generator (build/make/tools/aconfig/aconfig). The storage read
# API Rust library (rust_ffi_static libaconfig_storage_read_api_cxx_bridge)
# is part of the Rust staticlib the rust track provides, like every other
# Rust dependency of libandroid_runtime.
set(_aconfig_args
    --workspace build/make/tools/aconfig
    --manifest "${_cargo_dir}/aconfig-workspace.toml"
    --lock "${_cargo_dir}/aconfig.Cargo.lock"
    --copy build/make/tools/aconfig --copy external/rust/cxx
    --link prebuilts/sdk)
# Android 17's aconfig crates name these two by path.
foreach(_crate anyhow clap)
  if(EXISTS "${AOSP_SRC}/external/rust/android-crates-io/crates/${_crate}/Cargo.toml")
    list(APPEND _aconfig_args --copy external/rust/android-crates-io/crates/${_crate})
  endif()
endforeach()
add_custom_command(
  OUTPUT "${AOSP_RUST_TARGET}/release/aconfig"
  COMMAND ${_cargo_build} ${_aconfig_args} -- build --release --locked -p aconfig
  DEPENDS "${_cargo_dir}/aconfig-workspace.toml"
          "${_cargo_dir}/aconfig.Cargo.lock"
          "${_ra64_config}/sources.lock.json"
  COMMENT "cargo: aconfig" USES_TERMINAL VERBATIM)
add_custom_target(aconfig_tool DEPENDS "${AOSP_RUST_TARGET}/release/aconfig")

# cxxbridge (external/rust/cxx/gen/cmd), used by genrules.
add_custom_command(
  OUTPUT "${AOSP_RUST_TARGET}/release/cxxbridge"
  COMMAND ${_cargo_build}
          --workspace external/rust/cxx
          --lock "${_cargo_dir}/cxx.Cargo.lock"
          --copy external/rust/cxx
          -- build --release --locked -p cxxbridge-cmd
  DEPENDS "${_cargo_dir}/cxx.Cargo.lock"
          "${_ra64_config}/sources.lock.json"
  COMMENT "cargo: cxxbridge" USES_TERMINAL VERBATIM)
add_custom_target(cxxbridge_tool DEPENDS "${AOSP_RUST_TARGET}/release/cxxbridge")

# bindgen, for rust_bindgen modules (Android 17 closure). Soong builds it from
# external/rust/android-crates-io; the same release comes from crates.io here,
# with the lock file inside the crate.
if(EXISTS "${_ra64_config}/rustlibs.toml")
  file(READ "${_ra64_config}/rustlibs.toml" _rustlibs_conf)
  if(_rustlibs_conf MATCHES "bindgen_cli = \"([0-9.]+)\"")
    set(_bindgen_version "${CMAKE_MATCH_1}")
    set(AOSP_RUST_BINDGEN "${CMAKE_BINARY_DIR}/rust/bindgen/bin/bindgen")
    add_custom_command(
      OUTPUT "${AOSP_RUST_BINDGEN}"
      COMMAND cargo install bindgen-cli --version =${_bindgen_version} --locked
              --root "${CMAKE_BINARY_DIR}/rust/bindgen" --target-dir "${AOSP_RUST_TARGET}"
      COMMENT "cargo: bindgen-cli ${_bindgen_version}" USES_TERMINAL VERBATIM)
    add_custom_target(bindgen_tool DEPENDS "${AOSP_RUST_BINDGEN}")
  endif()
endif()
