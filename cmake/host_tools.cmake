# Rust host tools and libraries, built with cargo from the fetched AOSP
# sources (see tools/cargo_build.py). Soong builds these with rustc directly;
# the upstream crates also ship Cargo.toml files, which we use instead.

set(AOSP_RUST_STAGE "${CMAKE_BINARY_DIR}/rust/tree")
set(AOSP_RUST_TARGET "${CMAKE_BINARY_DIR}/rust/target")
set(_cargo_build ${Python3_EXECUTABLE} -I "${CMAKE_SOURCE_DIR}/tools/cargo_build.py"
    --stage "${AOSP_RUST_STAGE}" --target-dir "${AOSP_RUST_TARGET}")

# aconfig code generator (build/make/tools/aconfig/aconfig). The storage read
# API Rust library (rust_ffi_static libaconfig_storage_read_api_cxx_bridge)
# is part of the Rust staticlib the rust track provides, like every other
# Rust dependency of libandroid_runtime.
set(_aconfig_args
    --workspace build/make/tools/aconfig
    --manifest "${CMAKE_SOURCE_DIR}/tools/cargo/aconfig-workspace.toml"
    --lock "${CMAKE_SOURCE_DIR}/tools/cargo/aconfig.Cargo.lock"
    --copy build/make/tools/aconfig --copy external/rust/cxx
    --link prebuilts/sdk)
add_custom_command(
  OUTPUT "${AOSP_RUST_TARGET}/release/aconfig"
  COMMAND ${_cargo_build} ${_aconfig_args} -- build --release --locked -p aconfig
  DEPENDS "${CMAKE_SOURCE_DIR}/tools/cargo/aconfig-workspace.toml"
          "${CMAKE_SOURCE_DIR}/tools/cargo/aconfig.Cargo.lock"
          "${CMAKE_SOURCE_DIR}/config/sources.lock.json"
  COMMENT "cargo: aconfig" USES_TERMINAL VERBATIM)
add_custom_target(aconfig_tool DEPENDS "${AOSP_RUST_TARGET}/release/aconfig")

# cxxbridge (external/rust/cxx/gen/cmd), used by genrules.
add_custom_command(
  OUTPUT "${AOSP_RUST_TARGET}/release/cxxbridge"
  COMMAND ${_cargo_build}
          --workspace external/rust/cxx
          --lock "${CMAKE_SOURCE_DIR}/tools/cargo/cxx.Cargo.lock"
          --copy external/rust/cxx
          -- build --release --locked -p cxxbridge-cmd
  DEPENDS "${CMAKE_SOURCE_DIR}/tools/cargo/cxx.Cargo.lock"
          "${CMAKE_SOURCE_DIR}/config/sources.lock.json"
  COMMENT "cargo: cxxbridge" USES_TERMINAL VERBATIM)
add_custom_target(cxxbridge_tool DEPENDS "${AOSP_RUST_TARGET}/release/cxxbridge")
