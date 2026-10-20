# Notes

Design decisions, where every compiler flag comes from, and where this build
deviates from Soong. Keep this file in step with `tools/` and `overrides/`.

## Layout

| Path | What |
| --- | --- |
| `config/aosp.toml` | The pin: manifest tag, release config, Soong variant. The only place to change when moving to a new AOSP release. |
| `config/projects.toml` | Which AOSP projects (or sub-directories, or single files) to download. |
| `config/sources.lock.json` | Written by `tools/fetch.py`: resolved commit, content hash of the extracted tree and tarball hash per project. |
| `overrides/overrides.toml` | All manual knowledge: closure roots, product variables, soong_config variables, compiler compatibility flags, modules built outside the generated CMake. |
| `patches/<project path>/*.patch` | Source patches, applied by `tools/fetch.py` after extraction (section "Source patches"). |
| `tools/fetch.py` | Downloads and verifies sources into `src/`. |
| `tools/blueprint.py` | Android.bp parser and evaluator (including `select()`). |
| `tools/release_config.py` | Evaluates `build/release` (release flags, aconfig value sets). |
| `tools/bp2cmake.py` | Soong variant resolution, cc module model, closure, CMake emission. |
| `tools/soong_flags.py` | Soong's global flags and the per-file flag assembly order. |
| `tools/generators.py`, `tools/aidl_interface.py` | Code generation steps (genrule, aconfig, sysprop, proto, yacc/lex, aidl). |
| `tools/cargo_build.py`, `cmake/host_tools.cmake`, `tools/cargo/` | Rust host tools (aconfig, cxxbridge) built with cargo, out of tree, with committed lock files. |
| `tools/bp2rust.py`, `rust/` | The Rust linked into libandroid_runtime: rustc 1.83.0 invocations generated from Android.bp, `librustlibs.a`, its CMake interface and tests (section "Rust"). |
| `tools/gen_notices.py`, `config/notices-policy.toml`, `config/notices-extra.toml`, `cmake/notices.cmake` | The NOTICE file next to the library and the licence check of everything linked into it (section "Notices"). |

## Sources

* Pin: manifest tag `android-16.0.0_r1`. Every project is resolved through
  Gitiles to the commit the tag points at; the commit goes in the lock file.
* Gitiles serves per-directory tarballs, so large projects are fetched by
  sub-directory (`frameworks/base` is 14 MB this way instead of several GB).
  For projects where Gitiles answers 503 (it refuses big archives, e.g.
  `external/libjpeg-turbo`), `fetch.py` falls back to a shallow `git fetch` of
  the single commit and `git archive`.
* Verification uses a content hash of the extracted tree (paths, modes,
  file hashes, symlink targets), not the tarball hash, because Gitiles does
  not promise byte-stable gzip output. The tarball hash is recorded for
  information only; a run that gets different gzip bytes for the same content
  leaves the lock file alone.
* Symlinks are kept when they stay inside `src/`, dropped otherwise (a few
  point at files of projects we do not fetch).
* A project fetched in parts also gets the licence files at its top level
  (NOTICE, LICENSE, COPYING, COPYRIGHT, PATENTS, MODULE_LICENSE_*, METADATA),
  found by listing its root directory at the pinned commit. They are
  recorded as `license_files` in the lock, so later runs need no listing.
  A licence module that lives in an Android.bp outside the fetched parts
  must be added to `projects.toml` by hand (build/soong `licenses/`,
  the top-level Android.bp of hardware/interfaces and googletest);
  `gen_notices.py` reports any that is missing. Single files are cached in
  `src/.cache/files`.
* `src/` is never edited by the build. Rust crates are copied into
  `build/<dir>/rust/tree` before cargo runs, because cargo writes
  `Cargo.lock` and needs workspace manifests we replace.

### Source patches

Only upstream AOSP commits that the official library demonstrably has and
the pin does not. Each patch file starts with its provenance (commit, author,
date, the tag that first has it, the URL the diff was fetched from) and the
evidence; the diff itself is unchanged. `fetch.py` records the patch hashes
in the project's stamp, so changing a patch re-extracts the project from the
tarball cache; the lock file keeps the hash of the unpatched tree.

| Patch | Upstream | Why |
| --- | --- | --- |
| `frameworks/base/0001-hwui-host-allocateHardwareBitmap-copies-pixels.patch` | `30eb173fa210` "[RNG] Bitmap::allocateHardwareBitmap() must copy source content." (2025-04-11, first in `android-16.0.0_r3`) | Host `Bitmap::allocateHardwareBitmap` returns a zeroed heap bitmap at `android-16.0.0_r1`, so `Bitmap.copy(HARDWARE)`, HARDWARE decodes (BitmapFactory, ImageDecoder, BitmapRegionDecoder) and hardware gainmaps come back transparent. See "HARDWARE bitmaps" under Verification. |
| `frameworks/base/0002-CursorWindow-jni-CriticalNative-table-order.patch` | `06b30aa5b930` "Update @CriticalNative usage for framework methods" (2025-07-25, first in `android-16.0.0_r4`), only its `android_database_CursorWindow.cpp` hunks | No code change on the host (`CRITICAL_JNI_PARAMS_COMMA` is `JNIEnv*, jclass,` there); it gives the CursorWindow JNI table the order the official library has, and 0003 is written against it. |
| `frameworks/base/0003-CursorWindow-MappedFile-sqlite-jni-all-hosts.patch` | `a86bb7e46466` "Make sqlite JNI available for host Mac and Windows in libandroid_runtime" (2025-08-08, first in `android-16.0.0_r4`) | CursorWindow maps its ashmem region through `android::base::MappedFile` instead of `mmap`/`munmap`; the official library has the extra `mMappedFile` member (fields 8 bytes later) and lacks exactly those four `mmap`/`munmap` call sites. On Linux the Android.bp hunks select the same sources. |
| `frameworks/base/0004-Hyphenator-no-am-pattern-file.patch` | `67ed6fce1304` "Remove call to `addHyphenator("am", 1, 1)`" (2025-08-06, first in `android-16.0.0_r4`) | `hyph-am.hyb` does not exist, so r1 logs "Unable to find pattern file or unable to map it for am" at every Hyphenator init; the official library has no such call (Amharic still resolves through the `und-Ethi` alias). |

The list comes from an audit of every host-only and "[RNG]" commit
between `android-16.0.0_r1` and r4 (the public `main` ends 2025-03-26) in
frameworks/base, the `android12-hostruntime-dev` branch and the other
projects in `config/projects.toml`, each checked against the official
binary: [rng-audit.md](rng-audit.md) has the table and the
evidence. The official library is r1 plus a hand-picked set of host fixes
from August 2025, not a later snapshot: `c80d23f520` (defensive CursorWindow
parcel checks, merged the same week as 0003), `cb2d94a92f` (HostRuntime
error message) and `8d01b95436` (Ravenwood: real aconfig values for host
hwui flags) are not in it and are not applied. The same audit found three
build-level differences that are not commits (a debuggable product,
`LOG_ALWAYS_FATAL_IF` without messages in `core/jni`, libinput contents).
The first is settled: we build a debuggable product too (`debuggable =
true`, see "Debuggable product" under Verification); the other two are
described there and left as they are.

## Variant evaluation (what bp2cmake does, and the Soong code it mirrors)

The variant is `host`, os `linux_glibc`, arch `arm64`, multilib `lib64`,
static linkage.

1. **Parsing** (`blueprint.py`): Blueprint syntax incl. `+=`, `+` on strings,
   lists and maps, and `select()` with tuple conditions, `any @ x` bindings,
   `default` and `unset`. Variables are scoped to the rest of the file and to
   Android.bp files in sub-directories, as in Blueprint. `select()` is
   resolved eagerly since only one configuration exists: `os()` is
   `linux_glibc`, `arch()` is `arm64`, `release_flag()` comes from the release
   config, `soong_config_variable()` and `product_variable()` from overrides.
2. **Load hooks**: `soong_config_module_type` modules are rewritten to their
   base type and their `soong_config_variables` blocks are appended
   (`android/soong_config_modules.go`, `AppendProperties`), with bool, string
   and value variables and `conditions_default`.
3. **Defaults** (`android/defaults.go`): the defaults list is flattened by a
   pre-order walk of `defaults` (each module once), then each one is
   *prepended* in that order (`PrependProperties`). The result is that the
   last-walked defaults' list entries come first, and for scalars the module
   wins, then the first defaults that sets the property.
4. **OS and arch properties** (`android/arch.go`): merged in Soong's order:
   `target.host`, `target.linux`, `target.host_linux`, `target.glibc`,
   `target.linux_glibc`, `target.not_windows`, then `arch.arm64`,
   `multilib.lib64`, `target.linux_arm64`, `target.linux_glibc_arm64`,
   `target.glibc_arm64`. Lists append, except properties tagged
   `variant_prepend` in Soong's structs (include dirs, `static_libs`,
   `whole_static_libs`, `header_libs`, `export_include_dirs`,
   `export_header_lib_headers`, `generated_headers`), which prepend.
   `target.platform.cflags` is applied because host modules do not use an SDK.
5. **Product variables** (`android/variable.go`): appended when the variable
   is true or set; `%d`/`%s` are substituted.
6. **Static/shared blocks**: `cc_library` is built as its static variant
   (`static: {}` appended). `cc_library_shared` modules in the closure are
   also compiled as archives (with `shared: {}`), because libandroid_runtime
   links its "shared" dependencies statically on the host.
7. **Dependencies**: `exclude_static_libs`, `exclude_shared_libs`,
   `exclude_header_libs`, `exclude_srcs`, `exclude_generated_sources` are
   honoured. Exported include dirs follow `cc/cc.go` `depsToPaths`: a
   dependency's exports are used by its direct dependents; they are
   re-exported only through `whole_static_libs`, `export_*_lib_headers` and
   `export_generated_headers`. Libraries with `.sysprop` sources re-export
   the sysprop include dir; `proto.export_proto_headers` re-exports proto dirs.
8. **Duplicates**: `ndk_library`/`llndk_library` are renamed `<name>.ndk` /
   `<name>.llndk` as in Soong. Other duplicate names (only from Soong
   namespaces) keep the first definition and print a warning.

The closure starts at `closure.roots` in overrides (`libandroid_runtime`)
and follows header, whole static, static and shared libraries. Modules in
`closure.headers_only` contribute exported headers only (none at present).
A module with `link_only = true` in overrides (`libhidlbase`) compiles none
of its own sources or generated code but exports its include dirs, and its
`whole_static_libs` are built and linked.

9. **Blueprint `build = [...]`**: files listed there (for example
   `frameworks/base/AconfigFlags.bp`) are parsed with the listing file's
   scope as parent, as Blueprint does.
10. **Rust dependencies** (`rust_ffi_static`, `rust_library`, ...): not
    compiled here. bp2cmake walks their `whole_static_libs`, `static_libs`
    and `rustlibs` to find the C/C++ halves (`libcxxbridge05`,
    `libminikin_from_rust_to_cpp`, `libinput_from_rust_to_cpp`,
    `libflags_rust_cpp_bridge`), which are cc modules and are built and
    linked like any other static library. The Rust code itself is the
    imported target `rustlibs` (see "Linking").

## Compiler flags

Every compile gets exactly Soong's flags, in Soong's order, from a response
file per module and language (`build/out/cmake-gen/rsp/<module>.<lang>.rsp`).
Response files avoid CMake's option de-duplication, which would reorder
warning flags. CMake's own flags are empty (`CMAKE_<LANG>_FLAGS_INIT`, no
build type).

Order (`cc/builder.go` transformSourceToObj, `cc/compiler.go` compilerFlags):

```
C:   globalCommon globalC globalConly localCommon localC localConly systemIncludes noOverride
C++: globalCommon globalC globalCpp   localCommon localC localCpp   systemIncludes noOverride
asm: globalCommon globalAs            localCommon localAs           systemIncludes
```

| Group | Content | Source |
| --- | --- | --- |
| globalCommon | toolchain cflags (`linuxCflags`), `commonGlobalCflags`, `-ftrivial-auto-var-init=zero`, `-g`, `-fdebug-prefix-map=/proc/self/cwd=`, `extraExternalCflags` for third-party dirs, toolchain `-march=armv8-a` | `cc/config/global.go`, `x86_linux_host.go`, `arm64_linux_host.go` |
| globalC | `-target aarch64-linux-gnu`, `-DANDROID_STRICT` outside `external/` | `cc/compiler.go` |
| globalCpp | `commonGlobalCppflags` (`-Wimplicit-fallthrough`, `-D_LIBCPP_ENABLE_THREAD_SAFETY_ANNOTATIONS`, `-Wno-gnu-include-next`) | `global.go` |
| globalAs | `-target`, `-D__ASSEMBLY__ -fdebug-default-version=4` | `global.go` |
| localCommon | own `export_include_dirs`, `local_include_dirs`, `include_dirs`, module dir, proto/yacc/sysprop gen dirs, dependency exports (`-I`, then `-isystem`) | `cc/compiler.go`, `cc/library.go`, `cc/cc.go` |
| localC | `-Werror` (prepended unless the module has `-Werror`/`-Wno-error`; Soong only exempts `device/` and `vendor/`), module `cflags` minus `ClangUnknownCflags` and illegal flags, `target.platform.cflags` | `cc/compiler.go`, `cc/config/clang.go` |
| localCpp/localConly | `-std=` (`gnu++20`/`gnu23` default, `experimental` = `gnu++2b`/`gnu2x`, `gnu_extensions: false` swaps gnu for c), module flags, `-fno-rtti` unless `rtti: true`, STL flag | `cc/compiler.go`, `cc/stl.go` |
| systemIncludes | `CommonGlobalIncludes` that exist (`system/core/include`, `frameworks/native/include`, ...) | `global.go` |
| noOverride | `noOverrideGlobalCflags`, plus `noOverrideExternalGlobalCflags` for third-party dirs | `global.go` |
| toolchain headers | `-isystem` of a directory with bionic's `stdatomic.h` and `bits/stdatomic.h` (not a Soong flag; see below) | AOSP clang's resource dir |

Sanitizers (`cc/sanitize.go`): host modules with a `sanitize` block get
UBSan with the minimal runtime, exactly as Soong does on a glibc host. The
flags go at the end of the module's C flags (after `-Werror` and the module
cflags, before `-std=`): `-fsanitize=<list>` (`all_undefined` gives
`undefined`; `undefined` gives Soong's short list; then `misc_undefined`;
`integer_overflow` adds the two overflow checks and Soong's
`integer_overflow_blocklist.txt`), `-fno-sanitize=vptr,function`,
`-fno-sanitize-recover=all`, `-fsanitize-minimal-runtime
-fno-sanitize-trap=integer,undefined -fno-sanitize-recover=integer,undefined`,
then `-fno-sanitize=implicit-integer-sign-change` and
`-fno-sanitize=unsigned-shift-base` (Soong's string test on the joined
flag), then `sanitize.blocklist`. A `sanitize` block with only a blocklist
enables nothing (`SanitizerEnabled` is false), as in Soong. Modules affected
in this closure: libutils, libutils_binder, libbinder, libbinder_ndk,
libhwbinder-impl-internal (`integer`), libui-types (`bounds` plus
integer_overflow), libziparchive(_for_incfs), libdng_sdk, libimage_io,
libminikin (overflow checks), libinput (`undefined`). The first builds
compiled these without sanitizers; the official library contains the UBSan minimal
runtime (its `ubsan: add-overflow by 0x` strings), so this is required for
parity: a check that fires aborts the process, on both builds.

AOSP's clang ships bionic's `stdatomic.h` (and `bits/stdatomic.h`) as its
builtin `stdatomic.h`: in C++ it maps the C11 names onto `std::atomic`.
Upstream clang's builtin defines C11 macros (`atomic_load`,
`memory_order_relaxed`, `kill_dependency`) that break C++ that includes
`<cutils/atomic.h>` together with `<atomic>` (libbinder, libhwbinder,
libinput, `android_util_Binder.cpp`). `overrides [toolchain]
builtin_headers` puts bionic's two files (fetched from `bionic/libc/include`)
in a directory searched after every other include flag.

Third-party is `android.IsThirdPartyPath`: `external/`, `vendor/`,
`hardware/` minus `hardware/interfaces`, `hardware/libhardware*`,
`hardware/google`, `hardware/ril`.

Module flags go through Soong's shell escaping rule
(`proptools.ShellEscape`): a flag whose only unsafe characters are spaces is
not quoted, so the shell splits it (expat uses `"-include stdio.h"`); a flag
with any other unsafe character stays one argument. Relative paths in module
flags (`-I`, `-include`, ...) are then made absolute, because Soong compiles
from the source root and we compile from the build directory.

## Deviations from Soong

| What | Soong | Here | Why |
| --- | --- | --- | --- |
| Compiler | clang-r547379 (clang 20) | system clang 21.1.8 | No prebuilts for linux-arm64. Diagnostics that clang 21 added and that trip `-Werror` are demoted in `overrides [compat]` (list below). |
| Toolchain | linux_glibc x86_64 with GCC 4.8 sysroot (glibc 2.17) | linux_glibc arm64 does not exist in Soong; we use `linuxCflags` with no x86 flags, triple `aarch64-linux-gnu`, `-march=armv8-a` (from Soong's linux_bionic arm64 toolchain) | |
| `--gcc-toolchain`, `--sysroot` | Soong prebuilts (glibc 2.17, GCC 4.8) | With `RA64_USE_SYSROOT=ON`: a Debian 11 arm64 sysroot (glibc 2.31, GCC 10 runtime) and `--gcc-install-dir`. Without it: the build machine's glibc and GCC runtime | See Toolchain below. |
| C++ library | `-nostdinc++` + external/libcxx headers (LLVM ~20 snapshot), prebuilt static libc++ | With `RA64_USE_SYSROOT=ON`: `-nostdinc++ -isystem` our libc++ 21.1.8 headers and our static libc++. Without it: `-stdlib=libc++`, system libc++ 21 | Same ABI family; libc++ 21 is stricter in places. |
| `__FILE__`, debug paths | relative (compiles run from the source root) | absolute paths mapped back with `-ffile-prefix-map=<src>/=` | Keeps strings and debug info like Soong's. |
| Compat flags | none | a shared response file, not tracked as an object dependency | Only diagnostic flags may go there, so adding one need not rebuild. |
| bison/flex | prebuilts/build-tools | system bison 3.8.2, flex 2.6.4 | Only the `aidl` tool. |
| Rust host tools | rustc driven by Soong, crates from external/rust | cargo with crates from crates.io, except `cxx` which is patched to external/rust/cxx 1.0.119 so the bridge code matches | See below. |
| Rust in libandroid_runtime | rustc 1.83.0 prebuilt, every rlib of the closure in librustlibs.a | the same rustc release and flags, only the crates live in the official library | See "Rust". |

Clang 21 diagnostics demoted (`overrides [compat]`):

* `-Wno-error=character-conversion` (new in clang 21, on by default;
  `gtest-printers.h`).
* `-Wno-error=unnecessary-virtual-specifier` (new in clang 21, in
  `-Wextra`; ICU's `UnicodeSet` and other final classes).
* `-Wno-error=nontrivial-memcall` (new in clang 21, on by default;
  `memset` on androidfw's `ConfigDescription`, utils' `KeyedVector`).
* C only: `-Wno-error=incompatible-pointer-types-discards-qualifiers`.
  Not a clang issue: glibc 2.36+ headers in C23 mode make `strrchr` return
  `const char *` for a const argument (`sqlite3.c`). Not needed with the
  old-glibc sysroot.
* C++ only: `-Wno-invalid-specialization`. libc++ 21 marks standard type
  traits `[[clang::no_specializations]]` (an error by default); AOSP's libc++
  snapshot does not, and `libs/math/half.h` specializes
  `std::is_floating_point<android::half>`.

## Generated code

| Generator | Used for | Tool | Notes |
| --- | --- | --- | --- |
| aconfig | `hwui_flags_cc_lib` and other `cc_aconfig_library` | `aconfig`, built by cargo from build/make/tools/aconfig | Mirrors `aconfig/init.go` create-cache and `codegen/init.go` create-cpp-lib. |
| sysprop | `HWUIProperties.sysprop` in libhwui | `sysprop_cpp` from system/tools/sysprop, built by the generated CMake | `cc/gen.go` genSysprop. |
| aidl | `android.hardware.graphics.common-V6-ndk`, `...composer3-V4-ndk`, `...drm.common-V1-ndk`, `...common-V2-ndk` | `aidl` from system/tools/aidl, built by the generated CMake | `aidl_interface` is expanded as `system/tools/aidl/build` does (frozen versions from `aidl_api/`, `.hash`, `--structured --version --hash -t --stability --min_sdk_version`, `-p` preprocessed imports). |
| genrule | cxx bridge code and headers | `cxxbridge`, built by cargo from external/rust/cxx | |
| proto | `sysprop_cpp` (host tool) | `aprotoc` from external/protobuf (v21.12), built by the generated CMake | Same as Soong. An attempt with the system libprotobuf failed: it is built against libstdc++ and our code uses libc++. |
| yacc, lex | `aidl` (host tool) | system bison and flex | |
| aidl (cc srcs) | `.aidl` in `srcs` of libbinder, libgui_window_info_static, iinputflinger_aidl_lib_static, libandroid_runtime (`deviceproductinfoconstants_aidl`) | `aidl-cpp` from system/tools/aidl | `cc/gen.go` genAidl: one `aidl-cpp -d<dep> --ninja <flags> -I<base> <file> <gen/aidl> <cpp>` per file; flags from `aidl.flags`, `aidl.local_include_dirs`, `aidl.include_dirs`, `-t`, `--min_sdk_version` (min_sdk_version, else sdk_version, else `platform_apis`). The package path is the file's path relative to its filegroup's `path` (Soong's `Path.Rel()`). `-I gen/aidl` comes after the yacc dir; `aidl.export_aidl_headers` exports it. |
| aconfig (test mode) | `com.android.input.flags-aconfig-cc`, `android.companion.virtualdevice.flags-aconfig-cc` (`mode: "test"`), plus libguiflags and the window flags in production mode | `aconfig` | Same create-cache and create-cpp-lib steps with `--mode test`. Every flag is read-only in bp2a, so no generated file calls the aconfig storage API. |
| cxxbridge (C++ side) | `libminikin_cxx_bridge_code/_header`, `libinput_cxx_bridge_code/_header`, `libflags_rust_generated_cpp_bridge`, `cxx-bridge-header` | `cxxbridge` | genrules, compiled into the C++ halves of the Rust modules. |
| toolbox_input_labels | libinput (`InputEventLabels.cpp`) | python3 genrule over bionic's kernel `input.h` | genrule. |

Not generated, on purpose: `hidl-gen` (libhidlbase's android.hidl.base and
android.hidl.manager code; libhidlbase is `link_only`, see Linking) and
`stats-log-api-gen` (`libstatslog_libinput` is in libinput's android section
only).

### Release config and flag values

* Release config: **bp2a** (`config/aosp.toml`). At this tag build/release
  only has `ap2a ap3a ap4a bp1a bp2a` plus `root` and the build-variant
  configs; `aosp_current` aliases `bp2a`. Public AOSP has no `trunk_staging`.
  bp2a is the Android 16 (Baklava) release config.
* Chain applied (`release_config.go` GenerateReleaseConfig): root, ap3a,
  ap4a, bp1a, bp2a. `RELEASE_PLATFORM_VERSION` becomes `BP2A`.
* The build-variant overlay (`user`) is not applied: Soong only inherits it
  when `RELEASE_BUILD_USE_VARIANT_FLAGS` is set, and it is empty in bp2a.
* aconfig value sets, in order: `aconfig_value_set-platform_build_release-`
  `root`, `ap3a`, `ap4a`, `bp1a`, `bp2a`.
* `RELEASE_ACONFIG_FLAG_DEFAULT_PERMISSION=READ_ONLY` and
  `RELEASE_ACONFIG_REQUIRE_ALL_READ_ONLY=true` (so `--allow-read-write false`):
  every aconfig flag is a compile-time constant in this release, which is
  what a release build of the platform does.
* Product variables: `debuggable=true`, `eng=false`,
  `platform_sdk_version=36`. The android-all jar's build is not documented;
  the reference library has the code only a debuggable product compiles in
  (see "Debuggable product" under Verification). `eng` cannot be told from
  the binary and changes nothing here: its two stanzas are core/jni's
  `-DNO_RESET_STACK_PROTECTOR` (read only by the bionic part of
  `com_android_internal_os_Zygote.cpp`, not built for host) and libgui's
  `DEBUG_ONLY_CODE` (BufferQueue sources, not in the closure). The `user`
  build-variant overlay in `config/aosp.toml` only matters for release
  flags and is not applied.

## Rust

### What is live

Android.bp links far more Rust into libandroid_runtime than the official
library contains. Soong compiles every rlib of a shared library's closure
into one staticlib through a generated stub (`cc/builder.go`
GenerateRustStaticlib: `#![no_std]` plus `extern crate <name>;` for each
rlib), and the host link has no `--gc-sections` (Soong adds it only for
Bionic). Thin LTO inside the staticlib still drops everything not reachable
from the symbols the C++ side references, so what survives is the code
reachable from the cxx bridges.

Evidence from the official x86_64 library
(`ref/x86/native/linux/x86_64/libandroid_runtime.so`, stripped, no Rust in
`.dynsym`): Rust panic locations carry source file names, and Soong compiles
from the source root, so `.rodata` lists every live Rust file.
`rust/check-live.py` extracts them:

| Crate | Live files (official library) | Other markers |
| --- | --- | --- |
| minikin (frameworks/minikin/rust) | `hyphenator.rs` | `Minikin`, `minikin::ffi::load_hyphenator`, `minikin::ffi::hyphenate` |
| cxx 1.0.119 | `src/rust_vec.rs`, `src/symbols/rust_string.rs`, `src/unwind.rs` | `panic in ffi function` |
| env_logger 0.10.2 | `src/logger.rs`, `src/filter/mod.rs`, `src/fmt/mod.rs`, `src/fmt/writer/mod.rs` | `RUST_LOG_STYLE` |
| log 0.4.26 | none (no panics) | `SetLoggerError` |
| logger (system/logging/rust) | none (no panics) | reached from minikin, see below |
| std | `/rustc/90b35a6239c3d8bdabc530a6a0816f7ff89a0aaf/library/...` (rustc 1.83.0), its deps addr2line 0.22.0, gimli 0.29.0, miniz_oxide 0.7.4, rustc-demangle 0.1.24 | |

env_logger is live, not just linked: `Hyphenator::new` (hyphenator.rs, not
test code) calls `logger::init`, which on host builds an
`env_logger::Builder`. Not live: the `input` crate and its chain
(libinput_rust_ffi is only reached from InputTransport.cpp, which the host
JNI never registers), the aconfig storage read API (every flag is read only
in bp2a), flags_rust (used only in `#[cfg(test)]` code of hyphenator.rs),
env_filter (logger uses it only on Android), anyhow and thiserror (listed
for cxx, unused by `external/rust/cxx/src`).

`rust/rustlibs.toml` holds this decision: the root (`libminikin_rust_ffi`,
libminikin's `target.linux.whole_static_libs`) and the dependencies pruned,
with reasons. The pruned crates are not passed to rustc, so a pruned crate
that is actually used fails the build.

### Build

* Toolchain: `rust/install-toolchain.sh` installs the official
  `rust-1.83.0-aarch64-unknown-linux-gnu.tar.xz` (rustc and rust-std
  components only) into `rust/toolchain/`. The script pins the SHA-256 and
  checks the detached signature against the Rust release key
  `108F 6620 5EAE B0AA A8DD 5E1C 85AB 96E6 FA1B E5FE` in a throwaway
  keyring. 1.83.0 is Soong's `RustDefaultVersion` and the commit hash in
  the official library matches.
* `tools/bp2rust.py` reads the Android.bp files with bp2cmake's index and
  resolver (defaults, target blocks, select()), follows `rustlibs` and
  `proc_macros` from the roots, and writes `build/.../rustlibs/build.ninja`.
  10 crates: unicode-ident 1.0.8, proc-macro2 1.0.94, quote 1.0.40,
  syn 2.0.100, cxxbridge_macro 1.0.119 (proc macro, host), cxx 1.0.119,
  log 0.4.26, env_logger 0.10.2, logger, minikin. Every version is checked
  against the crate's Cargo.toml and
  `external/rust/android-crates-io/pseudo_crate/Cargo.lock` (`crates.tsv`
  records the result).
* The Ninja file runs with the source root as working directory
  (`ninja -C src -f <out>/build.ninja`; outputs and Ninja logs go to
  `<out>`, nothing is written under `src/`). Inputs are relative and
  `-Z remap-cwd-prefix=.` is passed, as in Soong, so panic locations read
  `external/rust/...` exactly like the official library.
* Per crate, in Soong's order (`rust.go` compilerFlags, cfgFlags,
  featureFlags; `builder.go` transformSrctoCrate): GlobalRustFlags
  (`-Z stack-protector=strong -C opt-level=3 -C debuginfo=2
  -C relocation-model=pic -C overflow-checks=on -C force-unwind-tables=yes
  -C symbol-mangling-version=v0 --cfg soong ...`), lints by directory
  (`--cap-lints allow` for external/, `-D warnings -D missing-docs ...` for
  first-party), module `flags`, `--edition` (default 2021),
  `--extern proc_macro` for proc macros, `-C metadata=<module>`, `cfgs`
  (twice for libraries, as library.go does), `features`, `--crate-type`,
  `--crate-name`, `--target`, `-C codegen-units=1`, and
  `-Zallow-features=""` outside third-party paths. Environment:
  `OUT_DIR=out`, `ANDROID_RUST_VERSION=1.83.0`, `CARGO_*` for
  `cargo_env_compat` modules (`rustEnvVars`).
* `librustlibs.a`: the stub `librustlibs.rs` with
  `extern crate minikin, cxx, logger, env_logger, log`, compiled with the
  global flags, `-C metadata=libandroid_runtime -C lto=thin
  --crate-type=staticlib --crate-name=generated_rust_staticlib` and
  `-Zallow-features=""` (frameworks/base/core/jni is first-party), as in
  `TransformRlibstoStaticlib`. Panics unwind on host (`-C panic=abort` is
  device only).
* cxx bridge code: the cxxbridge genrules used by the C++ halves of the live
  crates (`cxx-bridge-header`, `libminikin_cxx_bridge_header`,
  `libminikin_cxx_bridge_code`) run from Android.bp's `cmd`. The cxxbridge
  binary must report the cxx crate's version (1.0.119); this is checked at
  build time.
* `rust/rustlibs.cmake` runs bp2rust at configure time and defines the
  IMPORTED STATIC target `rustlibs` (`librustlibs.a`, interface include dirs
  = the generated header dirs), `rustlibs_build`, and
  `RUSTLIBS_GEN_SOURCES` and `RUSTLIBS_CC_DEPS` (`libcxxbridge05` and
  `libminikin_from_rust_to_cpp`, the C++ libraries the Rust needs at link
  time, which Soong propagates from the rust modules' `whole_static_libs`).

Deviations from Soong: `RUSTC_BOOTSTRAP=1` (the official stable rustc
rejects `-Z`; AOSP's prebuilt accepts them); `--sysroot=/dev/null` is
dropped (std comes from rust/toolchain's own sysroot instead of
`prebuilts/rust` rlibs); proc macros are linked with the host clang and
lld; `--color=always` kept.

### Verification

* `rust/test/` is a CMake project that uses `rust/rustlibs.cmake`, compiles
  `cxx.cc` (`-DRUST_CXX_NO_EXCEPTIONS`), the generated minikin bridge and a
  smoke test (rust::String, rust::Vec, `load_hyphenator`, `hyphenate` with a
  Rust to C++ `getScript` call), and links an executable and a shared
  library with `-Wl,--no-undefined`. Both link and the test passes.
* `rust/check-live.py --ref <official .so> --ours <stripped test .so>`:
  identical sets of Rust source files for cxx (3), env_logger (4),
  minikin (1) and std (29 files plus the same four std deps), same rustc
  commit, all marker strings present.
* glibc: the objects in librustlibs.a carry no symbol versions; the floor is
  set by the link. Linked against the Debian 11 sysroot with static libc++,
  libc++abi and libunwind, the test library needs GLIBC_2.17 only, plus
  weak `statx@GLIBC_2.28` and `__cxa_thread_atexit_impl@GLIBC_2.18` (the
  official library has the same two weak imports). Linked against the build
  machine's glibc 2.43 instead, `stat64`/`fstat64` bind to 2.33 and
  `pthread_key_*` to 2.34, so the sysroot matters.
* External references of librustlibs.a: `_Unwind_*` (from libunwind), a
  few libc/libpthread/libdl functions, and
  `minikin$rust$cxxbridge1$getScript`/`getJoiningType`
  (libminikin_from_rust_to_cpp).

Cost on the 2 vCPU VM: a clean Rust build takes about 2.5 minutes alone
(4 to 5 minutes with other builds running), peak 1.1 GB for a single
process, about 85 MB of output. The toolchain takes 0.7 GB installed plus the
237 MB tarball.

## Flag parity audit

Checked against build/soong/cc/config (`global.go`, `x86_linux_host.go`,
`arm64_device.go`, `arm64_linux_host.go`) and `cc/sanitize.go`,
`cc/lto.go`, `cc/library.go`, `cc/linker.go`, `cc/stl.go`, and against the
response files the build writes.

| Flag | Soong (glibc host) | Here | Notes |
| --- | --- | --- | --- |
| `-O2` | global; modules may add `-O3`/`-O0` after it | same | libz, libpng, libjpeg, ICU use `-O3`; the aidl tools `-O0` (from their Android.bp). |
| `-ffp-contract=off` | global | same | Matters most on arm64, where clang would otherwise fuse into FMA (`-ffp-contract=on` is clang's default). No module overrides it; no `-ffast-math` anywhere in the closure. |
| `-fno-strict-aliasing` | global | same | libjpeg adds `-fstrict-aliasing` itself. |
| `-fno-exceptions`, `-fno-rtti` | global / per module | same | `-fexceptions`: libdng_sdk, libskia; `-frtti`: ICU, libdng_sdk, libimage_io, libultrahdr. |
| `-fPIC` | linuxCflags | same | |
| `-fvisibility` | not set globally on host (`-fvisibility-inlines-hidden` is device only) | same | `-fvisibility=hidden` from Android.bp in libbinder, libhwui, ICU, skia; `protected` in libnativehelper_any_vm. |
| `-ftrivial-auto-var-init=zero` | global default | same | libsqlite adds `=pattern` itself. |
| `-fno-omit-frame-pointer` | linuxCflags | same | |
| `-U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=3`, `-fstack-protector-strong` | linuxCflags | same | Fortify level 3 with glibc headers; the toolchain sysroot decides which `__*_chk` symbols exist. |
| `-march=armv8-a` | x86_64 host: none; linux_bionic arm64 host: `-march=armv8-a` | `-march=armv8-a` | No `-mbranch-protection` (device `armv8-a-branchprot` variant only). System clang adds nothing (checked with `-###`): no branch protection, no stack clash protection. |
| outline atomics | clang default on aarch64 Linux | same | Needs `__aarch64_*` helpers from libgcc.a (with `-static-libgcc`) or compiler-rt builtins. |
| UBSan | per-module `sanitize` blocks, minimal runtime | same | Was missing in the first builds of the static closure; see "Compiler flags". |
| LTO | none on host unless `lto.thin` (`cc/lto.go`) | none | No module in the closure asks for it. |
| `-ffunction-sections`, `--gc-sections` | device only | none by default | See "Linking". |
| `-Wl,--icf=safe` | hostGlobalLldflags | same | Needs `-faddrsig` (global). |
| max page size | device: `-z max-page-size=` | lld default (64 KiB on aarch64) | Works on 4K, 16K and 64K page kernels. |

Arm64-specific behaviour that flags cannot make identical to the x86_64
reference, recorded so test differences can be traced:

* `char` is unsigned on aarch64 Linux (as on Android arm64 devices); Soong
  passes no `-fsigned-char` for arm64. Kept, to match the platform ABI.
* `long double` is IEEE binary128 (software) on aarch64, x87 80-bit on
  x86_64. SQLite chooses long double arithmetic at run time when it has more
  precision than double, so text-to-real conversions near the precision
  limit can round differently from the reference.
* NEON code paths in libpng, libjpeg-turbo, libwebp, zlib, Skia (see the
  SIMD note below).

## Linking libandroid_runtime.so

The root is a `cc_library_shared`; bp2cmake emits it as a CMake SHARED
library and links the static closure into it (`link_closure`, Soong's
dependency order; lld resolves archives in any order). Link flags follow
`cc/linker.go` CommonLinkerFlags and `cc/library.go` for a glibc host:

```
-fuse-ld=lld -Wl,--icf=safe -Wl,--no-demangle          hostGlobalLldflags
-Wl,--no-undefined
-Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now -Wl,--no-undefined-version
-Wl,--compress-debug-sections=zstd                       linuxLldflags
-ldl -lpthread -lm -lrt
rpath $ORIGIN/ $ORIGIN/lib64 $ORIGIN/../lib64 $ORIGIN/../../lib64 $ORIGIN/../../../lib64
-shared -Wl,-soname,libandroid_runtime.so               (CMake's SHARED rule)
-nostdlib++                                              stl libc++_static
-static-libgcc                                           overrides (see below)
-Wl,--version-script,platform/linux/libandroid_runtime_export.txt
```

* `-static-libgcc`: Soong adds it in `target.linux_glibc_x86_64` only (there
  is no linux_glibc_arm64 target). The same flag is the arm64 equivalent
  (libgcc.a and libgcc_eh.a instead of libgcc_s.so); it is added to the
  module's ldflags in overrides.
* `--gc-sections`: Soong passes it only with bionic toolchains
  (`cc/library.go`), not for glibc hosts, and host code is not built with
  `-ffunction-sections`. `RA64_GC_SECTIONS` (default OFF) adds it.
* Inputs that do not come from Android.bp are CMake-level
  (`cmake/link_runtime.cmake`), so the toolchain file and the Rust build can
  supply them:
  * `RA64_CXX_RUNTIME_LIBS`: static C++ runtime archives (Soong:
    libc++_static with libc++abi; the official library also contains LLVM
    libunwind). Default: the system `libc++.a` and `libc++abi.a`.
  * `RA64_UBSAN_MINIMAL_RUNTIME`: `libclang_rt.ubsan_minimal` for aarch64,
    linked with `--exclude-libs` because at least one static dependency is
    sanitized (Soong's MinimalRuntimeDep). Default: the compiler's resource
    dir.
  * `rustlibs`: imported target with librustlibs.a, from
    `rust/rustlibs.cmake` (the Rust build) or `RA64_RUSTLIBS_ARCHIVE` (a prebuilt
    archive, for testing). The C++ halves are built here, so
    `RUSTLIBS_CC_DEPS` and `RUSTLIBS_GEN_SOURCES` are not added again.
    Without `rustlibs` the link fails and lists the missing Rust symbols
    (`-Wl,--error-limit=0`).
* Rust modules in Soong's closure (`AOSP_libandroid_runtime_RUST_MODULES`):
  `libminikin_rust_ffi`, `libinput_rust_ffi`,
  `libaconfig_storage_read_api_cxx_bridge`. Only the first is live; the
  others' C++ halves are compiled but nothing references them. An earlier
  cargo build of the aconfig storage staticlib is gone.

Closure decisions (`overrides.toml`, each checked by the `--no-undefined`
link: any reference into dropped code would fail it):

* `android_view_InputChannel.cpp`, `android_view_InputEventReceiver.cpp`,
  `android_view_InputEventSender.cpp` are dropped from libandroid_runtime:
  `platform/host/HostRuntime.cpp` does not register them, and the official
  library has none of their strings. They are the only users of
  InputTransport and so of the `input` Rust crate.
* libinput: `MotionPredictor.cpp`, `MotionPredictorMetricsManager.cpp`,
  `TfLiteMotionPredictor.cpp` (TensorFlow Lite, flatbuffers, Eigen) are not
  built; their only user is `android_view_MotionPredictor.cpp`, android
  only. `libtinyxml2` and `libPlatformProperties` are listed but unused.
* libhidlbase is `link_only`: only its `libhwbinder-impl-internal` is used
  (by libbinderthreadstateutils), so hidl-gen is not needed.
* `libandroid_runtime_lazy` (frameworks/native/libs/android_runtime_lazy) is
  built as Android.bp says (libbinder_ndk's JNI glue loads
  libandroid_runtime.so through it).

## Notices

Building `libandroid_runtime.so` also writes `lib/NOTICE` next to it, the
licence texts of exactly what was linked in, and
`notices/libandroid_runtime/notices.json`, an inventory with the SHA256 of
every text. `tools/gen_notices.py` does both, in two steps wired up by
`cmake/notices.cmake` (called from `ra64_link_runtime()`):

1. `libandroid_runtime_notices`, before the link (the library depends on
   it, and it can be built on its own): every module on the link line from
   `closure.json`, the crates of librustlibs.a (`rustlibs/crates.tsv`,
   `in_staticlib` = yes) and every entry of `config/notices-extra.toml`.
   Output in `notices/libandroid_runtime/link-line/`.
2. After the link: the link runs with `-Wl,--why-extract=...`, and the
   POST_BUILD step (after check-so) keeps the module archives that had at
   least one member extracted, the library's own objects, librustlibs.a if
   used, and the extra components whose `archives` had a member extracted or
   whose `objects` were inputs of the link (from CMake's link dependency
   file, `CMakeFiles/<target>.dir/link.d`, when it exists).

Licence metadata is resolved as Soong does: a module's `licenses`, else the
`default_applicable_licenses` of the nearest enclosing Android.bp with a
`package` module; the `license` module gives the kinds and text files.
`config/notices-extra.toml` covers what Android.bp does not: libc++ with
libc++abi and libunwind, the UBSan minimal runtime, the GCC crt objects and
libgcc.a, glibc's crti.o, crtn.o and libc_nonshared.a, the Rust standard
library, `README.ijg` for libjpeg-turbo, and the attribution sentences
(Adobe DNG, Adobe Gain Map, IJG, FreeType) printed at the top of the file.
Paths there use `{sysroot}`, `{runtimes}`, `{rust_toolchain}` and
`{rustlibs}`; the NOTICE file prints them as `<sysroot>` and so on.

The check (`RA64_NOTICE_CHECK`, on with the sysroot toolchain) fails the
build for: a module without licence metadata or with a licence module that
is not fetched, a missing text, a licence kind outside
`config/notices-policy.toml`, a "by exception only" licence without an
`[[acknowledged]]` reason, and, after the link, an extracted archive or a
linked object that belongs to no module and no extra component.
`RA64_NOTICE=OFF` skips all of it. Toolchain outputs made before the
licence texts were kept fail the check: re-run
`python3 -I toolchain/make-sysroot.py [--arch amd64]` (it unpacks again,
seconds) and `toolchain/build-runtimes.sh --licenses-only [--arch x86_64]`.

Results at the pin (2026-10-19, arm64; the post-link step checked with a
relink of the existing archives, byte-identical output with
`--why-extract`):

* Link line: 52 components, 57 distinct texts, 0 problems.
* Linked in: 51 archives contribute members (47 module archives, libc++.a,
  librustlibs.a, libclang_rt.ubsan_minimal, libc_nonshared.a; libgcc.a
  contributes none, crtbeginS.o and crtendS.o do). 23 modules on the link
  line contribute nothing, among them the four hardware/interfaces AIDL
  libraries, libexpat, libmodpb64, libkernelconfigs (libvintf),
  libnativehelper_any_vm and the aconfig flag libraries, so their projects
  drop out. Result: 48 components (8 of them only for header libraries), 55
  distinct texts, 0 problems, 646 KB.
* Every module of the closure (104, header-only modules and host tools
  included) and every crate resolves to a fetched licence text.

Header-only modules of the closure are listed as well, marked
`(headers)`, in both steps: their inline code and templates are compiled
into the linked objects, and closure.json does not record which module
includes which header library. They add six frameworks/native and
libnativehelper Apache-2.0 notices, libhidl's and googletest's.

## Verification

`tools/jni_tables.py` extracts JNINativeMethod tables from the three
consecutive R_*_RELATIVE relocations of each entry (x86_64 and aarch64), and
compares two libraries as a multiset of tables, each an ordered list of
(name, signature): `compare REF OURS`. `dynsym REF OURS` compares exported
symbols (va_list mangling normalized). The stripped reference has no
symbols, so adjacent arrays read as one run there; ours keeps `.symtab`
(and aarch64 `$d` mapping symbols), so the check is that every reference
run is a concatenation of our tables, each used once.
Because of that, the check needs our unstripped library (the stripped one
reads as one large run too).

Names such as `results/full-arm64-audit` or `out/arm64-audit` below are
local output directories of the harnesses in `tests/upstream/` and
`tests/rig/`. They are not committed; the numbers are reproduced here.

### Results (2026-10-19)

Closure: 115 modules, 81 compiled (2,350 sources), plus the host tools
`aidl`, `aidl-cpp`, `aprotoc`, `sysprop_cpp`.

Without `rustlibs` the link fails with exactly 156 undefined symbols, all
Rust: 152 cxx runtime symbols (`cxxbridge1$string$*`, `cxxbridge1$str$*`,
`cxxbridge1$slice$*`, `cxxbridge1$rust_vec$<type>$*` for 17 element types,
`cxxbridge1$box$minikin$rust$Hyphenator${alloc,dealloc,drop}`,
`cxxbridge1$exception`) and 4 minikin FFI symbols
(`minikin$rust$cxxbridge1$load_hyphenator`, `...$hyphenate`,
`...$Hyphenator$operator$sizeof`, `...$alignof`). Nothing else is missing,
which also proves the closure decisions above (dropped Input JNI files,
tflite sources, libhidlbase objects) remove nothing that is referenced.

| | System clang, no sysroot, no gc-sections | Toolchain file (glibc 2.31 sysroot, own libc++ 21.1.8) + librustlibs.a from `rust/` |
| --- | --- | --- |
| Wall time, clean, `-j2` | 84 min (two other builds sharing the 2 vCPUs, load 4 to 6) | 46 min (mostly idle machine) |
| Size (unstripped / stripped) | 63.6 MB / 15.3 MB | 62.5 MB / 14.7 MB (reference: 16.2 MB stripped) |
| Exported symbols | 226, identical to the reference | 226, identical |
| JNI tables | 1,328 methods, all present; one order difference (below) | 1,327: the unregistered 1-entry `InputApplicationHandle` table is dropped by `--gc-sections`; otherwise the same (1,328 since the policy dropped `--gc-sections`, below) |
| NEEDED | libm, libc, ld-linux (glibc 2.43 has no separate libdl/libpthread/librt) | libdl, libpthread, libm, librt, libc, ld-linux, as the reference |
| Highest GLIBC version | 2.43 | 2.30 (`check-so.py`: floor 2.31 OK) |
| Weak undefined | CallStack x3 | CallStack x3, statx (reference: also `__cxa_thread_atexit_impl`) |

The one JNI difference against the reference in both builds is the order
inside `android_database_CursorWindow.cpp`'s table: the reference has
`nativeCreate, nativeDispose, nativeCreateFromParcel, ...`, the source at
`android-16.0.0_r1` (and so our library) has `nativeCreate,
nativeCreateFromParcel, nativeDispose, ...`. Same 21 entries; the reference
was built from BLR2.250402.052, not from the tag. RegisterNatives does not
depend on the order. The difference was a source difference after all: the
reference has `a86bb7e46466` and the CursorWindow part of `06b30aa5b930`
(patches 0002 and 0003, see "Source patches"); with them the tables are
identical, order included.

The reference keeps the `InputApplicationHandle` table although
`HostRuntime.cpp` never registers it: further evidence that Soong links
glibc host libraries without `--gc-sections`. The sysroot toolchain's link
policy added `--gc-sections` at first; it is gone since (2026-10-19), so the
toolchain build also has all 1,328 methods (62.5 MB became 63.2 MB
unstripped, 14.7 MB became 15.2 MB stripped on arm64). `RA64_GC_SECTIONS=ON`
still adds it, for either link path.

### HARDWARE bitmaps (2026-10-19)

Robolectric 4.17's own suites (the harness in `tests/upstream/`) found one
library bug: `ShadowNativeBitmapTest.testCreateBitmap_picture_`
`requiresHWAcceleration_checkPixels` failed on arm64 and passed on x86_64
with the official library. `Bitmap.copy(Config.HARDWARE, false)` returned a
transparent bitmap.

* Not the architecture: our x86_64 build under qemu fails the same way
  (`results/q-hw-x86ours`: same test fails, the probe's HARDWARE copy reads
  `0`, the ARGB_8888 copy reads the pixel).
* Not a flag or define: on host, `Bitmap_copy` (`jni/Bitmap.cpp`) calls
  `Bitmap::allocateHardwareBitmap(src)`, whose `#else` (non-`__ANDROID__`)
  branch at `android-16.0.0_r1` is `return allocateHeapBitmap(info)`: a
  calloc'd bitmap, no copy. No aconfig flag is involved.
* The official library has different source. Disassembly of its
  `nativeCopy(JIZ)` (found through the JNI table) calls a function that does
  `allocateHeapBitmap(info)` and then `memcpy(dest pixels, src.getPixels(),
  src.computeByteSize())`. That is exactly the host branch on
  `android12-hostruntime-dev` (the Robolectric native graphics branch):
  "Per header description, factories that accept const SkBitmap& should
  copy the contents ...". It reached AOSP's main as `30eb173fa210`
  ("[RNG] Bitmap::allocateHardwareBitmap() must copy source content.",
  merged 2025-04-11, "Merge android12-hostruntime-dev 25874ec"), in the
  `readPixels` form, which is first tagged in `android-16.0.0_r3`
  (r1 and r2 do not have it). Gitiles history pages need a login; the
  history came from the LineageOS mirror of frameworks/base
  (`lineage-23.1`) and the commit was then checked on
  android.googlesource.com.
* Fix: that commit, as `patches/frameworks/base/0001-...patch` (see "Source
  patches"). `readPixels` with identical source and destination info is a
  row copy; it equals the official memcpy for every source with minimal row
  bytes and does not overrun for padded ones.

| Check (arm64 unless noted) | Before | After |
| --- | --- | --- |
| upstream subset: robotests (81 classes) | 1444 pass / 14 fail | 1444 / 14 (all environment: 13 LEGACY sqlite4java, the SDK 37 test) |
| upstream: nativegraphics (all) | 766 / 2 | 767 / 1 (TableMaskFilter harness gap, fails on x86_64 too) |
| upstream: ctesque (all) | 427 / 0 | 427 / 0 |
| rig vs x86_64 goldens | 28/37 identical | 28/37, pixel-identical to the previous arm64 run |
| x86_64 build under qemu: ShadowNativeBitmapTest, ShadowNativeImageDecoderTest, probe | 1 fail (the same test) | 0 fail (`results/q-hw-x86fix`) |
| x86_64 build: rig vs goldens | 37/37 identical | 37/37 identical, max delta 0 |

Both libraries (patch plus no `--gc-sections`): check-so OK (highest
GLIBC_2.30), 226 exports identical to the reference, 1,328 JNI methods
(only the CursorWindow order difference). Clean `-j2` builds with the host
tools from a native build: arm64 50.6 min (4,116 s user, peak 1.15 GB),
x86_64 39.4 min (3,882 s user), with Gradle runs sharing the machine.

The subset now differs from the x86_64 official run only in the 14
environment failures (`results/subset-arm64-fix`).

### Host commit audit (2026-10-19)

After patches 0002 to 0004 (docs/rng-audit.md), clean `-j2` rebuilds: arm64
36.2 min (3,944 s user, peak 1.15 GB), x86_64 35.6 min (3,884 s user, peak
1.13 GB). Both: check-so OK (highest GLIBC_2.30), 226 exports identical to
the reference, JNI tables identical to the reference including order (1,328
methods; the CursorWindow order difference is gone). The x86_64 library now
has 17 `mmap` and 16 `munmap` call sites, like the reference (was 19 and 18).

| Check | Result |
| --- | --- |
| x86_64 build, rig under qemu (`out/x86-audit`) vs official goldens | 33/33 tests, 37/37 images identical, max delta 0 |
| arm64 build, rig (`out/arm64-audit`) | 33/33 tests; 28/37 identical to the x86_64 goldens as before, 37/37 identical to the previous arm64 run (`out/arm64-fix`) |
| upstream full suites, arm64 (`results/full-arm64-audit`, 293 s) | robotests 7865/14, nativegraphics 767/1, ctesque 427/0 |

Against the first full run (`results/full-arm64`, before 0001) the only
outcome change is the HARDWARE bitmap test (FAIL to PASS); the remaining
failures are the known environment ones (12 `ShadowSQLiteConnectionTest`
and 1 `SQLiteLibraryLoaderTest` forcing LEGACY sqlite4java,
`ShadowViewThreadTest` at SDK 37) and `ShadowNativeTableMaskFilterTest`.
The SQLite/CursorWindow classes that run on our library (SQLiteDatabaseTest
72, SQLiteCursorTest 47, ShadowCursorWindowTest 4, ...) and the
StaticLayout/LineBreaker ones all pass.

### Debuggable product (2026-10-19)

The audit (docs/rng-audit.md, "Not commits", item 1) found code in the
reference library that only a debuggable product compiles in. With
`debuggable = true` in `overrides.toml`, bp2cmake changes exactly three
modules (the generated CMake is otherwise identical):

| Module | Added by `product_variables.debuggable` |
| --- | --- |
| libminikin | `-DENABLE_ASSERTION` and the source `Debug.cpp` |
| libbinder | `-DBINDER_RPC_DEV_SERVERS -DBINDER_ENABLE_RECORDING` |
| liblog | `-UANDROID_DEBUGGABLE -DANDROID_DEBUGGABLE=1` (read only by `pmsg_writer.cpp`, which the host variant does not compile) |

libhidl's `-DLIBHIDL_TARGET_DEBUGGABLE` is in libhidlbase, which is
`link_only` here (only libhwbinder-impl-internal is used), so it is not
compiled.

Strings (`tools/audit/strdiff.py`, `.rodata` C strings of 6+ characters),
x86_64, against the reference:

| | Only in the reference | Only in ours |
| --- | --- | --- |
| `debuggable = false` | 117 | 951 |
| `debuggable = true` | 70 | 948 |

The 47 strings that close are all minikin assertions (16 `!(...)`
conditions such as `!(start <= end)`, and messages such as "Font collection
must have at least one valid typeface", "TAB is not supported in optimal
line breaker") and libbinder recording and RPC dev server messages
("Started Binder recording.", "%s: No keepAliveBinder provided.",
"RpcBinder: Started Binder debug on %s", ...). The three that leave ours are
the release-build counterparts ("Binder recording disallowed because
recording is not enabled", "setRpcClientDebug disallowed because RPC is not
enabled", "%s: disallowed because RPC is not enabled"). Nothing moves the
other way: no string of the reference goes missing and ours gains none. The
arm64 build gains and loses the same 47 and 3 strings. The 70 left are the
known build-level differences: "Fatal Error" (core/jni's message-less fatal
checks), libbinder's `!ownershipTransferred` (a message-less
`LOG_ALWAYS_FATAL_IF` in `RpcSession.cpp`), and toolchain parts (compiler-rt
UBSan minimal runtime messages, Rust std and panic string layout, libc++abi's
`__cxa_thread_atexit` fallback, lambda type names). The symbol tables
differ by one local libc++ template instance (`std::set` insert for
`BBinder::RpcServerLink`); the recording functions exist in both builds,
only their bodies change. The reference is stripped, so its local symbols
cannot be compared.

| Check | x86_64 | arm64 |
| --- | --- | --- |
| check-so | OK (GLIBC_2.30) | OK (GLIBC_2.30) |
| Exports, JNI tables vs reference | 226 identical; 1,328 methods identical incl. order | same |
| Size unstripped / stripped (was) | 64,024,984 / 16,357,600 (64,013,784 / 16,352,784) | 63,266,048 / 15,216,720 (63,270,464 / 15,211,680) |
| NOTICE | 48 components, 0 problems, identical to the release build's | same |
| Build, clean `-j2` | 35.6 min, 3,747 s user, peak 1.12 GB | 34.1 min, 3,763 s user, peak 1.14 GB |
| Rig | 33/33 tests; 37/37 images and 3/3 text files identical to the official goldens, max delta 0 (`out/x86-debuggable`) | 33/33 tests; 28/37 vs the x86_64 goldens as before, 37/37 and the text files identical to the release build (`out/arm64-debuggable`) |
| Upstream 4.17 suites (`results/full-arm64-debuggable`, 262 s) | | robotests 7865/14, nativegraphics 767/1, ctesque 427/0; 0 outcome differences against `full-arm64-audit`; no aborts |

Effect at run time: minikin now aborts on a violated `MINIKIN_ASSERT`, as
the official library does; none fired in the suites. libbinder's recording
and RPC debug paths are reachable only through binder transactions, which
Robolectric does not make. liblog's define changes no compiled code.

### Rebuild in another directory (2026-10-20)

Built the tree again in a fresh checkout at a different path, following
the build instructions (arm64 in `build/out` with in-tree host tools, 43
min; x86_64 with `RA64_HOST_TOOLS_DIR`, 40 min). Stripped libraries are
identical to the verified builds above except `.note.gnu.build-id`, which hashes the unstripped file and so picks up the build directory from the debug info. check-so OK on both.

The arm64 NOTICE first listed one extra entry, `libaidl_transactions (headers)`: with in-tree host tools, aidl's modules share closure.json, and gen_notices listed every header-only module in it. closure.json now records `header_libs` and gen_notices lists only header-only modules reachable from the link line, so both arches give the same 646,124-byte NOTICE. A change to the generator or its inputs now relinks the library (LINK_DEPENDS), since the NOTICE is written after the link.

### Path-independent debug info (2026-10-20)

The build-id difference above came from the checkout and build
directories in `DW_AT_comp_dir` and `.debug_line` (and, for the LLVM
runtimes, their own build directory). `tools/soong_flags.py` now maps the
checkout to `.` and the build directory to `out`, ahead of the existing
`src/` and `gen/` maps, and `build-runtimes.sh` maps its build and
toolchain directories. Code is unchanged: the stripped library is
identical to the previous one except the build-id. A local build and two
CI builds (different machines and directories) then gave the same file,
SHA-256 `cf3815f7...` and build-id `366cf8c8...`
([reproducibility.md](reproducibility.md)).

## Toolchain

The library has to load on older distributions than the build machine
(Ubuntu 26.04, glibc 2.43). The floor is **glibc 2.31** (Debian 11, Ubuntu
20.04, RHEL 9, Amazon Linux 2023 and newer). Soong does the same thing on
x86_64 with a glibc 2.17 sysroot; there is no arm64 one, so we build our own.

```
python3 -I toolchain/make-sysroot.py   # Debian 11 arm64 sysroot, ~30 MB, seconds
toolchain/build-runtimes.sh            # libc++/libc++abi/libunwind, a few minutes at -j2
cmake -S . -B build/out -G Ninja -DRA64_USE_SYSROOT=ON
ninja -C build/out -j2
```

`-DRA64_USE_SYSROOT=ON` is the same as
`-DCMAKE_TOOLCHAIN_FILE=<abs path>/cmake/toolchain-arm64-sysroot.cmake`.
Outputs live in `toolchain/out/` (gitignored); downloads in `toolchain/dl/`.

| File | What |
| --- | --- |
| `toolchain/make-sysroot.py` | Downloads libc6, libc6-dev, linux-libc-dev, libgcc-10-dev, libgcc-s1 for bullseye arm64 from snapshot.debian.org at a pinned timestamp and unpacks them with `dpkg-deb -x` (no root). Absolute symlinks are made relative; dangling ones (libasan.so and friends) and documentation are removed, except the licence texts: `usr/share/doc/<package>/copyright` and `usr/share/common-licenses`. For those, gcc-10-base (the doc directory of libgcc-10-dev links to it) and base-files are unpacked aside and only their doc and common-licenses files are copied in. |
| `toolchain/sysroot.lock.json` | Snapshot, InRelease hash, signing keys, and name, version, file and SHA256 of every package. With the lock present, any difference is an error; `--update` re-resolves. |
| `toolchain/build-runtimes.sh` | Static libc++, libc++abi, libunwind from the llvm-project 21.1.8 release tarball, built with the system clang against the sysroot, installed into `toolchain/out/runtimes`, with the four `LICENSE.TXT` files in `share/licenses/<component>/` (`--licenses-only` adds those to an existing prefix). |
| `cmake/toolchain-arm64-sysroot.cmake` | The toolchain file. |
| `cmake/ra64_link_policy.cmake` | `ra64_apply_shared_link_policy()` for the final shared library. |
| `toolchain/check-so.py` | Post-link checker. |
| `toolchain/sample/` | A small C++ shared library and loader that exercise the whole chain; `run-glibc231.sh` runs a program with the sysroot's own glibc 2.31 loader. |

**Trust.** The Debian `InRelease` is checked with `gpgv` against the Debian
archive keyring (from the installed `debian-archive-keyring` package, or
fetched with `apt-get download debian-archive-keyring`, which apt
authenticates through the host's Ubuntu archive signatures). A good
signature from one of the two pinned bullseye key fingerprints is required.
`Packages.xz` is checked against the SHA256 in `InRelease`, each `.deb`
against `Packages`. The LLVM tarball has a pinned SHA256 and its detached
signature must verify against `release-keys.asc` from releases.llvm.org with
the pinned signer (Douglas Yung, `FFB3 3689 80F3 E6BB 5737 145A 316C 56D0
64CA CBA5`).

**libc++ configuration.** Mirrors `toolchain/llvm_android`
(`base_builders.py`, `LLVMBuilder.cmake_defines` for Linux), which builds the
host libc++ behind Soong's `libc++_static`: `LIBCXXABI_USE_LLVM_UNWINDER`,
`LIBCXXABI_ENABLE_STATIC_UNWINDER`, `LIBCXX_ENABLE_STATIC_ABI_LIBRARY`,
`LIBCXX_HAS_ATOMIC_LIB=NO`, no ABI linker script, PIC, Release. Everything
else is LLVM's default: ABI version 1, namespace `std::__1` (as in the
reference library), exceptions and RTTI on, hardening mode none, libc++abi
and libunwind assertions on (the reference has libunwind's and libc++abi's
assertion strings), symbols not hidden. So `libc++.a` contains libc++abi and
libunwind; the separate archives are installed too. Source paths are mapped
to `out/llvm-project/` as in AOSP's build. Differences: static archives only,
no tests, LLVM 21.1.8 instead of AOSP's clang-r547379 (LLVM 20) snapshot,
because the compiler is clang 21 and libc++ should match it.

**Compile flags.** CMake adds `--target=aarch64-linux-gnu --sysroot=<sysroot>`,
the toolchain file adds `--gcc-install-dir=<sysroot>/usr/lib/gcc/aarch64-linux-gnu/10`
(crtbegin, libgcc). For the generated modules, `tools/soong_flags.py` emits
Soong's own host STL flags, `-nostdinc++ -isystem <runtimes>/include/c++/v1`,
when the toolchain file sets `RA64_LIBCXX_INCLUDE`. Hand-written C++ targets
get `-stdlib++-isystem <runtimes>/include/c++/v1`, which takes the place of
clang's default libc++ directory (the system libc++ 21 headers in
`/usr/lib/llvm-21/include/c++/v1` would otherwise win). Compiling against
glibc 2.31 headers also means no `__isoc23_*` redirects. Library and header
searches (`find_library`, `find_path`) only look in the sysroot.

**Link policy for the final library** (`ra64_apply_shared_link_policy(<target>
VERSION_SCRIPT <file> [ALLOW_UNDEFINED <glob>...] [NO_CHECK])`):

```
-fuse-ld=lld -nostdlib++ -static-libgcc --unwindlib=none
-Wl,--icf=safe -Wl,--no-demangle                      # hostGlobalLldflags
-Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now            # linuxLdflags
-Wl,--no-undefined -Wl,--no-undefined-version
-Wl,--build-id=sha1 -Wl,--compress-debug-sections=zstd
-Wl,--exclude-libs,libc++.a -Wl,--exclude-libs,libgcc.a -Wl,--exclude-libs,libgcc_eh.a
-Wl,--version-script,<file>
<objects and archives> <runtimes>/lib/libc++.a -ldl -lpthread -lm -lrt   (libc from the driver)
no RUNPATH, then a POST_BUILD run of check-so.py
```

`-static-libgcc` is in libandroid_runtime's `target.linux_glibc_x86_64`
block only, which the arm64 variant skips; we add it for arm64. Clang
refuses `--unwindlib=libunwind` with `--rtlib=libgcc`, so `--unwindlib=none`
plus the libunwind inside `libc++.a` is how we get the reference's layout:
libgcc.a for builtins and outline atomics, LLVM libunwind for `_Unwind_*`,
no libgcc_s and no libgcc_eh. The reference library has a RUNPATH of
`$ORIGIN/...` entries (Soong's host rpath); we drop it because nothing is
loaded from next to the library.

**check-so.py** (`python3 -I toolchain/check-so.py [--floor 2.31]
[--version-script FILE] LIB.so`) reads the ELF itself (no binutils) and fails
on: any `GLIBC_*` version above the floor, `GLIBC_PRIVATE` or any non-glibc
version (GLIBCXX, CXXABI, GCC_*), NEEDED outside libc, libm, libdl,
libpthread, librt and the loader of the ELF's architecture, an export that
is not global in the version script (patterns in `extern "C++"` blocks are
matched against demangled names), an executable or missing PT_GNU_STACK,
TEXTREL, RPATH/RUNPATH, missing GNU_RELRO or BIND_NOW, and strong undefined
symbols with no version. Results:

| Library | Result |
| --- | --- |
| `toolchain/sample` with the toolchain and policy | OK: NEEDED libdl, libpthread, libm, librt, libc; highest version GLIBC_2.18 (`__cxa_thread_atexit_impl`); 1 export; runs on the build machine and under the sysroot's glibc 2.31 loader (`run-glibc231.sh`). |
| the same sample linked naively on the build machine | FAIL: libgcc_s.so.1 (GCC_3.0), GLIBC_2.33 (`stat`), 2.34 (`pthread_*`), 2.38 (`__isoc23_*`), no BIND_NOW. Under glibc 2.31: `version GLIBC_2.33 not found`. |
| x86_64 reference, with `--version-script` | FAIL only on its RUNPATH; with `--allow-runpath --floor 2.17` OK: highest GLIBC_2.16, 226 exports all inside the version script. |

On arm64 the library has no NEEDED on `ld-linux-aarch64.so.1` (the x86_64
reference needs `ld-linux-x86-64.so.2` for `__tls_get_addr`; arm64 uses TLS
descriptors). `__cxa_thread_atexit_impl` binds to GLIBC_2.18 here, where the
reference leaves it weak and unversioned because glibc 2.17 lacks it.

**For other build steps.** The toolchain file exports `RA64_TOOLCHAIN`,
`RA64_TRIPLE`, `RA64_SYSROOT`, `RA64_RUNTIMES`, `RA64_GCC_INSTALL_DIR`,
`RA64_GLIBC_FLOOR` and complete flag strings `RA64_C_FLAGS`,
`RA64_CXX_FLAGS` and `RA64_LINK_FLAGS` for tools outside CMake. Any C or C++
object that ends up in the final library (for example code the `cc` crate
compiles for a Rust staticlib) must be compiled with `RA64_C_FLAGS` /
`RA64_CXX_FLAGS`, or it may pick up glibc 2.43 header redirects. Rust std
objects are fine as they are: their glibc symbol versions are bound at the
final link, against the sysroot.

**Static closure with the toolchain.** A clean `-DRA64_USE_SYSROOT=ON`
build of the static libhwui closure (2,245 build steps: 56 static libraries,
`aidl`, `aprotoc`, `sysprop_cpp`, the cargo tools) succeeds with no source
or flag changes beyond the STL flags above. Wall time was 1 h 32 min at
`-j2`, but the two vCPUs were shared with another build the whole
time (load 5 to 8); CPU time was 4,654 s user + 185 s system, which is the
same work as the 37 minute unshared build. Peak RSS 0.86 GB for one compiler
process. The static archives reference no `__isoc23_*` or other post-2.31
symbols. The host tools link libgcc_s dynamically (clang's default for
executables, as Soong's host binaries do) and need at most GLIBC_2.27; they
only run on the build machine. Building the sysroot takes seconds and the
C++ runtimes about a minute and a half at `-j2` on an idle machine.

## Architectures (RA64_ARCH)

The same tree builds for arm64 (default) or x86_64: `-DRA64_ARCH=x86_64`.
x86_64 exists for two reasons: it is Soong's own host architecture, so a
pixel comparison of our x86_64 library against the official one tests the
fidelity of this build without architecture effects, and the project may
later offer both.

```
python3 -I toolchain/make-sysroot.py --arch amd64
toolchain/build-runtimes.sh --arch x86_64
rust/install-toolchain.sh --target x86_64-unknown-linux-gnu
cmake -S . -B build/x86_64 -G Ninja -DRA64_USE_SYSROOT=ON -DRA64_ARCH=x86_64 \
      -DRA64_HOST_TOOLS_DIR=<native build>/bin
ninja -C build/x86_64 -j2
```

| Piece | arm64 | x86_64 |
| --- | --- | --- |
| Variant blocks | `arch.arm64`, `target.linux_arm64`, `linux_glibc_arm64`, `glibc_arm64` | `arch.x86_64`, `target.linux_x86_64`, `linux_glibc_x86_64`, `glibc_x86_64` (bp2cmake `--arch`; Skia's `SkOpts_hsw.cpp`/`SkOpts_skx.cpp`, libjpeg-turbo's SSE2/AVX2 `.asm`, zlib's and libpng's x86 lists) |
| Toolchain cflags (`soong_flags.ARCH_TOOLCHAINS`) | `-march=armv8-a` (from linux_bionic arm64) | `-m64` (`linuxX8664Cflags`), no `-march`: Soong's x86_64 glibc host toolchain has no ToolchainCflags, so the baseline is plain x86-64 (SSE2); Skia and libjpeg-turbo pick AVX2/SSSE3 code at run time |
| Link | | `-m64` (`linuxX8664Lldflags` minus the GCC prebuilt `-B`/`-L`) |
| `.asm` | none | yasm, as `cc/builder.go`: `-f elf64 -m amd64`, then asflags, local_include_dirs, include_dirs, the module dir (`cc/compiler.go` localYasmFlags). System yasm 1.3.0 (Soong: prebuilts/misc yasm). The object goes into the module's archive. |
| Sysroot | `toolchain/out/sysroot-bullseye-arm64` (`sysroot.lock.json`) | `sysroot-bullseye-amd64` (`sysroot-amd64.lock.json`), same snapshot and checks |
| C++ runtime and UBSan | `toolchain/out/runtimes` | `toolchain/out/runtimes-x86_64`; `build-runtimes.sh` also builds compiler-rt's `ubsan_minimal` (the system clang only has the build machine's), preferred by `link_runtime.cmake` when present |
| Rust | `aarch64-unknown-linux-gnu` | `x86_64-unknown-linux-gnu` std from the verified rust-std tarball; proc macros and their dependencies (syn, quote, proc-macro2, unicode-ident, cxxbridge_macro) are always built for the build machine |

Cross builds: when RA64_ARCH is not the build machine's CPU, the toolchain
file sets `CMAKE_SYSTEM_NAME`/`CMAKE_SYSTEM_PROCESSOR`, and the generators'
C++ tools (aidl, aidl-cpp, sysprop_cpp; aprotoc is only needed to build
sysprop_cpp) come from `RA64_HOST_TOOLS_DIR`, the `bin/` of a native build
of the same tree (bp2cmake `--host-tools-dir`). Their closures (11 modules)
are then not part of the build. The cargo tools (aconfig, cxxbridge) are
built natively as before. `cmake/toolchain-arm64-sysroot.cmake` remains as
a wrapper for the arm64 case. The arm64 generation is unchanged: every
response file, `modules.cmake` and `generators.cmake` are identical to the
output before the x86_64 support was added (paths aside).

### Control experiment: x86_64 build against the official library (2026-10-19)

Question: are the arm64 rendering differences (28/37 rig images identical to
the official x86_64 goldens, 9 off by 1 to 4 levels, two outliers of 29 and
135) caused by this build (flags, clang 21, libc++ 21, defines) or by the
architecture? The same tree was built for x86_64 and run through the
fidelity rig (`tests/rig`,
`RIG_X86_LIB=<ours> scripts/run.sh x86-via-loader`: Temurin 21 x64 under
qemu-user, the same JVM and qemu that made the goldens).

| | Result |
| --- | --- |
| Build | 104 modules, 71 compiled (the host tools' closures come from the native build), 1,170 steps; clean, no source or flag changes |
| check-so | OK: NEEDED libdl, libpthread, libm, librt, libc, ld-linux-x86-64; highest GLIBC_2.30; 226 exports |
| Exports, JNI tables | 226 exports identical; JNI tables as for arm64 (CursorWindow order, unregistered InputApplicationHandle table dropped by `--gc-sections`; all 1,328 since the policy dropped it) |
| Rig | **37/37 images and 3/3 text files identical to the goldens, max delta 0** |
| Time | about 63 min wall at `-j2` with other Gradle and qemu runs sharing the 2 vCPUs (the build was interrupted once and resumed); resumed part 28.5 min, 2,084 s user. Peak 0.66 GB for one process, 0.9 GB of output. Rig run 572 s. |

So the build is faithful to Soong's: compiled from the same sources with
the same flags, it renders bit for bit like the official library. The arm64
differences are inherent to arm64 code paths in Skia, not to this build.

qemu-user 10.2 reports SSE4.1, AVX, AVX2, FMA, F16C, BMI1/2 (no AVX-512)
and an XCR0 with YMM state, so Skia's run-time dispatch picks its HSW
raster pipeline (AVX2 + FMA), SSSE3 bilerp and the AVX2 `blit_row` on both
the official and our x86_64 library. The goldens are therefore the HSW
rendering; an x86_64 CPU without AVX2 would itself render slightly
differently.

Where Skia (external/skia at the pin) takes a different path on arm64, and
which rig scenes it explains:

| Code | x86_64 (as run) | arm64 (NEON) | Scenes |
| --- | --- | --- | --- |
| `SkOpts::S32_alpha_D32_filter_DXDY` (`src/opts/SkBitmapProcState_opts.h`) | nullptr, so `legacy_shader_can_handle()` (`SkImageShader.cpp`) refuses rotated/skewed matrices and the raster pipeline does a float bilerp | defined, so a rotated bilinear bitmap goes through the legacy `SkBitmapProcState` shader: 4-bit (1/16 px) fixed-point weights | `bitmap-scaling-filters` (max 29, only the rotated filtered bitmap) |
| `rcp_precise` (`matrix_perspective` stage) | `_mm256_rcp_ps` + one Newton step | `vrecpeq_f32` + two Newton steps | `canvas-transforms-clips` (8 pixels, max 135: a perspective bitmap shader sample lands on the neighbouring texel) |
| `rcp_approx`, `rsqrt_approx`, `rcp_fast` (unpremul, conical gradients, ...) | `rcp_ps`/`rsqrt_ps`, about 12 bits | estimate + one Newton step, about 16 bits | gradients, shaders, color filters (max 1) |
| lowp `div255` (`SkRasterPipeline_opts.h`) | `(v+255)/256`, off by up to 1 | exact rounding `(v + ((v+128)>>8) + 128)>>8` | blend modes (max 3), color filters, shaders, text effects (max 1) |
| `blit_row_s32a_opaque` (`SkBlitRow_opts.h`) | `s + (d*(256-a))>>8` | `s + SkMulDiv255Round(255-a, d)` | any srcover of translucent 32-bit spans (not isolated per scene) |
| `from_half`/`to_half`, `mad` | F16C, FMA | `vcvt_f32_f16`, `vfmaq_f32` | none seen (both fused, both IEEE conversions) |

`-ffp-contract=off` keeps scalar code from fusing on either architecture;
the fused multiply-adds above are explicit intrinsics in Skia's SIMD code.
compose-graphics (18,678 pixels, max 4) is concentrated in its rotated
sweep-gradient square and the ring gradient, consistent with the
`rcp_approx`/`div255` rows; it was not traced further.

The official mac/aarch64 library is built from the same Skia with
`SK_ARM_HAS_NEON` defined (any AArch64 compiler defines `__ARM_NEON`), and
none of these choices depend on the OS, so it takes the same NEON paths and
should show the same differences against the x86_64 goldens. This is
reasoned from the code; macOS cannot be run here.

## Open questions

* JNI compatibility of `android-16.0.0_r1` with the android-all jar
  (`BLR2.250402.052`): the JNI tables are identical with patches 0002 and
  0003, and Robolectric's own suites pass (see "Verification"). Moving to a
  newer android-all build needs the same checks again. The tag lives only in
  `config/aosp.toml`.
* SIMD: on arm64, `arch: { arm64: ... }` blocks apply to the host too, so
  libpng, libjpeg-turbo, libwebp and zlib get their NEON code (zlib also its
  `linux_arm64` block). The x86_64 reference gets no SSE paths for libpng
  (those are `android_x86*` only). Skia has no arm64-specific source lists
  (its arm64 code is selected in the sources by `SK_CPU_ARM64`), so the
  "use the android arm64 lists" fallback was not needed for this closure.
  Rendering differences against the x86_64 reference are explained by
  Skia's NEON paths (see "Control experiment"). A tolerance or per-arch
  goldens are needed for pixel tests that run on both architectures.
