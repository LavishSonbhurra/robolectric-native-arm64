# SDK 37: libandroid_runtime.so for Linux arm64

Robolectric loads `libandroid_runtime.so` for SDK 37 from the `android-all` jar
`17-robolectric-15733970` (build CLR2.260407.039, security patch 2026-06-05). That jar has no Linux
arm64 library. This document covers the `sdk37` target, which builds one from AOSP source with this
project's generator, not with Soong.

Inputs live in `config/sdk37/` (`aosp.toml`, `projects.toml`, `sources.lock.json`,
`overrides.toml`, `rustlibs.toml`, `cargo/`, `notices-*.toml`, `patches/`, `reference/`), sources in
`src-sdk37/`. `RA64_TARGET=sdk37` (CMake cache variable and environment for the tools) switches
every path. `sdk36` and `compat` are unchanged: from main and from this branch they generate the
same 251 and 128 files under `cmake-gen` and the same 4 Rust build files, byte for byte, and the same
`build.ninja` apart from hashes of the checkout path and the list of tool files CMake watches.

## Building

```
rust/install-toolchain.sh --version 1.93.1
RA64_TARGET=sdk37 python3 -I tools/fetch.py
cmake -S . -B build/sdk37 -G Ninja -DRA64_TARGET=sdk37 -DRA64_USE_SYSROOT=ON
ninja -C build/sdk37
```

A clean build without ccache took 8,604 s of ninja time (2 h 23 min), `-j2` on the 2 vCPU, 11 GB VM,
with memhold stopped. That includes cargo builds of aconfig, cxxbridge and bindgen. It ran in three
slices under the shared build lock, because two steps failed on the way and were fixed; nothing was
recompiled between slices. The result is byte-identical to the incremental ccache build that the
tests below ran on (SHA-256 `b406e55ddea0c95e...`, unstripped; stripped 23,999,864 bytes).

The closure has 289 modules, 168 of them compiled, 3,559 C and C++ sources and 6 host tools (SDK
36: 115, 81, 2,350 and 4). The Rust part is 44 crates, 31 of them in `librustlibs.a`.

## Tag: android-17.0.0_r1

The official library is not a build of a public tag. `android-17.0.0_r1` (BUILD_ID
CP2A.260605.016, frameworks/base `94b4c163b7df`, 2026-05-21) is the only public Android 17 tag, the
tip of the public `android17-release` branch, and public `main` stops in March 2025, so there is no
later public source to pick from. The release configuration is `cp2a`. The target builds it as a
debuggable product, as SDK 36 does.

JNI tables, exports and NEEDED match the official library at this tag with no JNI patch (see
Results), so the JNI surface of the official build and r1 are the same. Two small behaviours differ
and are patched, see Patches.

## Why the official library is so much larger than SDK 36

The official file is 29 MB against 16 MB for SDK 36: `.text` 22.3 MB against 11.8 MB, `.rodata`
2.3 MB against 1.5 MB, `.bss` 0.54 MB against 0.05 MB. It is a larger closure. It is not sanitizers
and not debug strings.

At Android 17 `HostRuntime.cpp` registers `InputChannel`, `InputEventReceiver`, `InputEventSender`
and `MotionPredictor` on host, and that pulls in much more of the tree:

| Added code | Why it is linked |
| --- | --- |
| TensorFlow Lite (`libtflite_static`), with ruy, Eigen, gemmlowp, flatbuffers, fft2d, re2 and the textclassifier hash | `MotionPredictor` runs a TFLite model |
| Full `libinput`, including `InputTransport`, `MotionPredictor`, `MotionPredictorMetricsManager` and the Rust `input` crate with serde_json | the input JNI classes |
| libjxl with highway and brotli | `libdng_sdk` now uses it |
| XMP-Toolkit-SDK | whole static library of `libdng_sdk` |
| Skia Fontations (`libskia_rust_ffi`, skrifa, read-fonts, font-types) | Skia's Rust font backend |

The source-path strings are the same story. Of the 99 paths (24 in SDK 36), most are panic locations
of the new Rust crates (read-fonts, skrifa, serde_json, ryu and others), with a few from
tensorflow/lite, frameworks/native/libs/input, ruy, libjxl and XMP-Toolkit-SDK, and libc++ paths of
AOSP's clang-r584948b. There is no Perfetto code in the official library.

Our stripped library is 24.0 MB. Its `.text` is 17.5 MB, 78% of the official 22.3 MB; at SDK 36 the
same ratio is 92%, while `.rodata` is 86% and 85%. The likely reason for the wider `.text` gap is
per-ISA code on x86_64: highway builds several x86 targets of libjxl, and ruy, gemmlowp and Eigen
have SSE and AVX paths. This was not measured symbol by symbol, because the official library is
stripped.

## What differs from the SDK 36 closure

174 more modules. The big new ones, in sources: `libstats_proto_host` 333 (host tool only),
`libtflite_static` 181, `libjxl` 136, composer3-V5-ndk 61, `xmp_toolkit_sdk` 48, `flatc` 38,
`libbrotli` 31, `libruy_static` 29, common-V7-ndk 28, `libregex_re2` 22, about 100 abseil modules
(protobuf needs abseil now), and `libprotoc` went from 167 to 271. New host tools:
`stats-log-api-gen` and `flatc`. `libPlatformProperties` is linked now, because `MotionPredictor`
reads `InputProperties`; SDK 36 could drop it.

Soong's flags changed too, in `tools/soong_flags_17.py`: `-Winit-self` is gone,
`-Werror=bool-operation` moved to the common list, `-Werror=format-security`, `-Werror=multichar`
and `-Werror=sizeof-pointer-memaccess` are new, the experimental C standard is gnu2y, and the
noOverride and external lists were revised. The C++ default stays gnu++20 for `cp2a`.
`libbase`, `libutils` and other libraries are now built with the UBSan minimal runtime on host, so
host tools link it as well.

## What the generator learned

* `RA64_TARGET=sdk37` and a flag profile `android17`, following `compat`.
* `sysprop_library`: gives the cc library `lib<name>`.
* `cc_atomslog_library_static`: runs `stats-log-api-gen` for the header and the source.
* `gensrcs`, used by the Skia Rust bridge.
* abseil's `cp --parents $(in)` genrules, which need paths relative to the source root.
* `whole_archive` for a host tool in `overrides.toml`: `stats-log-api-gen` finds atoms through the
  descriptors that the `.pb.cc` files register at startup.
* The Rust generator reads `rustlibs.toml` from the target's config and the Rust version from
  `[rust]` in `aosp.toml`, and handles crates generated at build time, in `tools/rust_gen.py`:
  `rust_bindgen`, `rust_aconfig_library` and the AIDL Rust backend, plus `srcs: [":module"]` read
  through `OUT_DIR`, and cargo_embargo's checked-in build script output.

## Toolchain

* C and C++: system clang 21.1.8, as for SDK 36. The official library has clang-r584948b paths. The
  stale SDK 36 comments were updated in `overrides.toml`; no new `[compat]` flag was needed.
* Rust: rustc 1.93.1 (commit `01f6ddf7588f`), the official library's own, from the signed release
  tarball through `rust/install-toolchain.sh --version 1.93.1`, into `rust/toolchain-1.93.1`. From
  this release the licence texts are only at the top of the tarball, so the script copies them.
* bindgen 0.72.1 from crates.io with `--locked`, the version in `pseudo_crate/Cargo.toml`, run with
  system libclang 21 and `--formatter none`.
* cxx 1.0.189. `external/rust/cxx/macro/Android.bp` still says 1.0.119; the macro's version is part
  of the bridge symbol names and has to match cxxbridge, so `rustlibs.toml` lists it as stale.

`libstats_proto_host` is 333 generated protos used only by the host tool. It is built at `-O0 -g0`
(`overrides.toml`), which cannot change the tool's output.

## Patches

In `config/sdk37/patches/`. Each file says what it is and why. No upstream commit could be used for
any of them, because r1 is the newest public source.

| Patch | What | Evidence |
| --- | --- | --- |
| `frameworks/base/0001` | `Bitmap.cpp`: no Perfetto track events on host | The official library has none of the file's slice names and no Perfetto code, though `libperfetto_c` is on the host link line at r1. With this patch `libperfetto_c` (`link_only`) and `libtracing_perfetto` stay out, and the `--no-undefined` link proves nothing else needs them. |
| `frameworks/native/0001` | `IdGenerator::nextId` gives up after 10 attempts on host | Reconstructed from the disassembly of the official function, which has the string "Failed to generate random bytes for id". r1 loops forever if `/dev/urandom` cannot be read. |
| `system/libhwbinder/0001` | `zeroMemory`: `memset` plus a compiler barrier | Reverts efd89fe for this build. glibc 2.31 has no `memset_explicit`, and the polyfill is in no project we fetch. Same code as `libs/binder/Utils.h` on non-bionic hosts. |

`config/sdk37/rustlibs.toml` also prunes dependencies that no live code uses, each with its reason. One of them, for `libinput_flags_rust`, strips an unused `use` line from aconfig's generated
crate; the compile fails if a flag of that package ever becomes read-write.

## Results

Everything below is from the library at the commit of this document.

### check-so

Passes: glibc floor 2.31, BIND_NOW, RELRO, no RUNPATH. Exports equal the official list, 225 of 225
(`tools/jni_tables.py dynsym`, list in `config/sdk37/reference/`). NEEDED is the same 6 entries:
libdl, libpthread, libm, librt, libc and the architecture's dynamic loader.

### JNI tables

`tools/jni_tables.py compare`: identical, 1380 methods in the same tables and the same order. No JNI
patch was needed.

### Strings

JNI tables do not see every difference, so `tools/audit/strdiff.py` was run both ways.

* Only in the official library, apart from x86_64 names and Rust string merging: AOSP's
  `prebuilts/clang` libc++ paths, and "Fatal Error" (see below). The string "Failed to generate
  random bytes for id" was the only one that pointed at a missing change, and is now patched.
* Only in ours: the `LOG_ALWAYS_FATAL` messages of `core/jni`, for example "Can not find ImagePlane
  class". The official library replaces them: 323 call sites call
  `__android_log_call_aborter("Fatal Error")`. The abort is the same; ours keeps the message. The
  mechanism is not in public source.
* Also only in ours: about 720 evdev label strings (`KEY_*`, `BTN_*`, `ABS_*`) from
  `input.h-labels.h`, used by `InputEventLookup::getLinuxEvdevLabel`, and aarch64 names. Nothing in
  the library calls those functions. Why the official build lacks the tables is not known.

### Fidelity rig

Native arm64 JDK 21.0.12 against goldens from the official x86_64 library under qemu with an x86_64
JDK, both at `RIG_SDK=37`: 33 of 33 tests pass on each side, 37 images and 3 text files.

28 of 37 images are identical and all 3 text files are identical. The 9 others are the same 9 as at
SDK 36, with the same numbers within one pixel:

| Image | Largest channel delta | Differing pixels | SDK 36 pixels |
| --- | --- | --- | --- |
| bitmap-scaling-filters | 29 | 3768 | 3768 |
| canvas-blend-modes | 3 | 1776 | 1776 |
| canvas-color-filters | 1 | 4065 | 4065 |
| canvas-gradients | 1 | 84 | 84 |
| canvas-shaders | 1 | 3992 | 3992 |
| canvas-transforms-clips | 135 | 8 | 8 |
| compose-graphics | 4 | 18679 | 18678 |
| compose-material-light | 1 | 1 | 2 |
| text-effects | 1 | 378 | 378 |

Goldens are in `tests/rig/goldens/x86_64-sdk37`, ceilings in `tests/rig/baseline/arm64-sdk37.json`.

### Robolectric's suites

Robolectric 4.17, native arm64, JDK 21, `SDKS=37`, `-Psuite.heap=3g`:

| Module | Pass | Fail | Skip |
| --- | --- | --- | --- |
| robotests | 7779 | 13 | 8 |
| nativegraphics | 765 | 1 | 3 |
| ctesque | 426 | 0 | 3 |

Wall time on the 2 vCPU VM: 353 s for robotests and nativegraphics, 84 s for ctesque.

The expected-failure list is `config/sdk37/upstream-expected-failures.txt`: 14 tests, and
`ci/check-upstream-failures.py` passes on 8,984 tests. The comparison with the official library is
per test, on the subset that is practical under qemu (the 81 robotests classes that touch native
code, all of nativegraphics, all of ctesque), x86_64 JDK 21 with the stock loader, 2,446 s:

| Module | Official pass/fail/skip | Ours pass/fail/skip |
| --- | --- | --- |
| robotests (subset) | 1435 / 0 / 1 | 1422 / 13 / 1 |
| nativegraphics | 765 / 1 / 3 | 765 / 1 / 3 |
| ctesque | 426 / 0 / 3 | 426 / 0 / 3 |

Exactly 13 tests differ, and none is in the library: `ShadowSQLiteConnectionTest` (12) and
`SQLiteLibraryLoaderTest` (1) force the LEGACY SQLite mode, and sqlite4java has no linux-aarch64
native ("Architecture 'aarch64' is not supported"). `ShadowNativeTableMaskFilterTest` fails the
same way with the official library. `ShadowViewThreadTest.testNewestSdk`, on the SDK 36 list, passes
here because it is the test that runs at SDK 37.

## What the test harnesses need for SDK 37

* The rig and the suites run as they are with `RIG_SDK=37` or `SDKS=37`, plus
  `-Prig.nativeLibSdk=37` or `-Parm64.nativeLibrarySdk=37`. They still compile against android-36.
* Espresso 3.7.0 calls `InputManager.getInstance()`, which SDK 37 removed, so Compose tests and
  ctesque fail with `NoSuchMethodException` on either library. 3.8.0-alpha03 works. The rig takes
  `-Prig.espresso=3.8.0-alpha03` and the suites `-Psuite.espresso=3.8.0-alpha03`. 3.8 needs minSdk
  24, so ctesque moves from 23 to 24 when that property is set.
* `robotests` still excludes 7 files that need SDK 37 APIs to compile. Running them needs compileSdk
  37 and the plain `android-all:17-robolectric-15733970` jar on the compile classpath.

## What the loader needs

Nothing in the library. With `-Drobolectric.arm64.nativeLibrary=<file>` and
`-Drobolectric.arm64.nativeLibrarySdk=37` the current loader loads it and every test above ran that
way. To ship it, the loader has to pick the bundled library by `SDK_INT`, since a library only
matches its own android-all, and `LIBRARY_SDK_PROPERTY` defaults to 36 today. The stripped library
is 24.0 MB, against 15.2 MB for SDK 36.

## Notices

`gen_notices.py --check` reports 0 problems with 79 components linked.
`tools/check_notice_holders.py` reports 0 holders missing over 1,615 linked sources.
New entries in `config/sdk37/notices-*.toml`:

* Eigen is MPL-2.0, built with `EIGEN_MPL2_ONLY`. It is acknowledged in the policy, with the source
  location. It is compiled unmodified through TensorFlow Lite.
* fft2d is "by exception only" in AOSP. It is built but not linked: only TensorFlow Lite's rfft2d
  kernel needs it and the linker drops that kernel, so nothing from it is in the library.
* Excerpts of the contributors' copyright lines from three expat sources, and notes naming The
  TensorFlow Authors.
* The Rust standard library entry uses 1.93.1's `COPYRIGHT-library.html`, which lists the licences
  of std's own dependencies.

## Not verified

* The cause of the 9 differing images at SDK 37. They match SDK 36, where a source-built x86_64
  library was pixel-identical to the official one, which pinned them on Skia's NEON paths
  (`docs/NOTES.md`). No x86_64 build of SDK 37 was made.
* MotionPredictor with a real model: the JNI loads and the suites pass, but no test here runs TFLite
  inference. Our build has no way to compare its output with the official library.
* How the official build drops Perfetto and the fatal messages, and which change gave it the
  `nextId` fix. Public source stops at r1.
* The 7 robotests files above, which need compileSdk 37.
* The x86_64 target of this config, and the release path (`ci/`, jars): nothing was published.
