# SDK 35: libandroid_runtime.so for Linux arm64

Robolectric loads `libandroid_runtime.so` for SDK 35 from the `android-all` jar
`15-robolectric-13954326` (build ALR1.240830.040, security patch 2024-08-05, file date August
2025). That jar has no Linux arm64 library. This document covers the `sdk35` target, which builds
one from AOSP source.

Inputs live in `config/sdk35/` (`aosp.toml`, `projects.toml`, `sources.lock.json`,
`overrides.toml`, `rustlibs.toml`, `cargo/`, `notices-*.toml`, `patches/`, `reference/`), sources
in `src-sdk35/`. `RA64_TARGET=sdk35` (CMake cache variable and environment for the tools) switches
every path. The default target, `sdk36`, and `compat` are unchanged: from main and from this
branch they generate the same 375 files under `cmake-gen`, the same Rust build files, and the same
`build.ninja` apart from hashes of the checkout path and one extra dependency line.

## Building

```
rust/install-toolchain.sh --version 1.78.0
RA64_TARGET=sdk35 python3 -I tools/fetch.py
cmake -S . -B build/sdk35 -G Ninja -DRA64_TARGET=sdk35 -DRA64_USE_SYSROOT=ON
ninja -C build/sdk35
```

A clean build without ccache takes 68 minutes on 2 vCPU (`-j2`), and gives the same library,
byte for byte, as the incremental build the tests ran on.

The closure has 111 modules, 77 of them compiled, 2,313 C and C++ sources and 4 host tools.

## Tag choice: android-15.0.0_r1

The official library is not a build of any public tag. It is closest to `android-15.0.0_r1`
(AP3A.240905.015.A2, frameworks/base `4e43ad12e1b`), with host runtime commits from later main
added by hand. We pin r1 and add the same commits as patches.

Why r1:

* The native directories of frameworks/base are the same from r1 through r4, and their last change
  is from mid-June 2024, so r1 to r4 are one snapshot for this purpose.
* JNI fit, counted as entries in the sources the host build registers that the official library
  does not have: r1 17, r6 24, r20 42, r36 42, android-16.0.0_r1 53. The 17 at r1 are all behind
  `__ANDROID__`, and they exist at every tag.
* The only official JNI name that no r1 source registers is `nNextHost` (patch 0013).
* The official library has 1,299 JNI methods and 223 exports. SDK 36 has 1,328 and a different
  export list, so `android-16` is too late.
* The security patch level does not pick a tag. The ap3a string was 2024-08-05 until July 2024 and
  r1 already says 2024-09-05, so ALR1 sits next to r1 but is not a build of it.
* Tags scanned: r1, r2, r4, r6 (AP4A), r20 (BP1A), r36. r18 and r19 do not exist. No android-15 tag
  has `core/jni/platform/linux`, which confirms that the host work was added separately.

The reference for all of this is the official x86_64 library. Its sources are not public, so a
statement below that it "has" a commit is an inference from its tables, strings, imports and
machine code.

## Patches

Every patch is in `config/sdk35/patches/<project>/` with its source and reason in the header.
Most of them are the 2024 and early 2025 host runtime work on main. Dates are author dates.

### frameworks/base

| No. | Commit | Change | Evidence in the official library |
| --- | --- | --- | --- |
| 0001 | `81abd23cc1a` | JVM-compatible libnativehelper | no libnativehelper in NEEDED |
| 0002 | `167d1cfe96f` | host build of libhwui | prerequisite of the hwui bindings |
| 0003 | `cd7eda911cf` | more hwui JNI bindings on host | JNI tables |
| 0004 | `99d1ea7a1cb` | Surface binding on host | JNI tables |
| 0005 | `79f29ea8cf7` | host builds use the JVM libnativehelper | as 0001 |
| 0006 | `1d8183361b1` | AndroidRuntime for host | `N7android11HostRuntimeE`, `use_base_native_hostruntime` |
| 0007 | `42291f2bda9` | rename NativeAllocationRegistry_Delegate | `libcore/util/NativeAllocationRegistry` |
| 0008 | `a19127a199d` | no JNI_OnLoad on Windows | no Linux effect, keeps later patches applying |
| 0009 | `688b3704864` | hostgraphics header target | build prerequisite |
| 0010 | `89acb1c5843` | wrong type in host ThreadBase | host fix, prerequisite |
| 0011 | `c80e7d04dbd` | JNI method binding name | `method_binding_format` |
| 0012 | `771b570ddc9` | same in hwui | as 0011 |
| 0013 | `c7bd207395f` | PathIterator `nNextHost` | JNI tables |
| 0014 | `e28dd9f756f` | MappedFile in CursorWindow | row count at 0x40 instead of 0x38 |
| 0015 | `a8c4d1ad696` | CursorWindow.cpp of the commit only | table order |
| 0016 | `9cf2fa6a79a` | `method_binding_format` in HostRuntime | as 0011 |
| 0017 | `3248101b101` | host runtime reorganised for Windows | Linux side, base of later patches |
| 0018 | `c8c6c179be2` | fix for the previous patch | follow-up |
| 0019 | `d6a86e84998` | NativeAllocationRegistry through jni_wrappers | follows from 0016 |
| 0020 | `2b592f4ed64` | Robolectric ICU fix | `icu.data.path` |
| 0021 | `26667c51a8b` | ICU default locale | `icu.locale.default` |
| 0022 | `68a4e350155` | binding names in hwui's loader | as 0011 |
| 0023 | `c1f14111220` | delta over 0017: `use_base_native_hostruntime` defaults to true | what Robolectric expects |
| 0024 | `b233f1527e7` | static dependencies, adapted | six NEEDED entries, all glibc |
| 0025 | `9a629e24776` | Hyphenator on host, adapted | `ro.hyphen.data.dir`, JNI tables |
| 0026 | `003ace9953d` | export list, adapted | 223 exports |
| 0027 | `30eb173fa210` | allocateHardwareBitmap copies pixels | function at 0x726980 |
| 0028 | `67ed6fce1304` | no `am` pattern file | Hyphenator init at 0x406490 |
| 0029 | none | HintSessionWrapper.h includes `<memory>` | build fix |
| 0030 | `f85416259fd` | ImageReader jni files move to core | prerequisite of 0031 |
| 0031 | `79e0a16c62e` | ImageReader on host, adapted | JNI tables and two exports |

Notes on the ones that needed judgement:

* **0026**: Linux only, plus the typeinfo of RefBase, VectorImpl and AndroidRuntime. The official
  library exports those because this Soong does not pass `-fno-rtti` on host.
* **0027**: same patch as SDK 36. The official function is `allocateHeapBitmap` followed by
  `memcpy`, the `android12-hostruntime-dev` form. The upstream form uses `readPixels`, which gives
  the same result for minimal row bytes and also handles padded rows.
* **0028**: an August 2025 commit. The official init builds `af`, `as`, `be` with no `am` between
  them, and the only `am` left is the later alias.
* **0031**: adapted to the r1 files, which have no P210 support. `nativeGetFenceFd` is also left
  out on host. The commit keeps it, but the official SurfaceImage table has four methods without
  it, so the official port was not the commit as written.

### Other projects

| Project | Patch | Why |
| --- | --- | --- |
| frameworks/minikin | 0001, `ab6c0e5` | r1 links the `libicu` shim on host, which pulls in all of ICU. The official library has none of the strings of collation, transliteration or date formatting (`DateTimePatterns`, `Translit`, `+Infinity`). |
| system/core | 0001, `7c4beee9` (ashmem-host.cpp only) | `ashmem_create_region` uses `tmpfile()`. The official library imports `tmpfile` and has no `/tmp/android-ashmem` string. Merged to main in March 2024 but not in r1. |
| frameworks/native | 0001, not upstream | see below |
| frameworks/native | 0002, `4878c0d5a` | `android/api-level.h` does not exist on host. Build fix. |
| external/fmtlib | 0001, not upstream | see "Toolchain". Build fix. |

`frameworks/native` 0001 is the one patch written here. At r1, android.os.Trace goes through
`libtracing_perfetto`, which needs the Perfetto SDK. The official library has the Trace table but
no Perfetto strings or dependency, and its natives are, from the disassembly:
`nativeRegisterWithPerfetto` is empty, `nativeTraceBegin` tests `atrace_get_enabled_tags()` and
calls `atrace_begin_body`, `nativeIsTagEnabled` is `atrace_get_enabled_tags() & tag`. The patch
gives the host the same behaviour with stubs in `tracing_perfetto.cpp`. The function bodies are
ours, the behaviour is taken from the binary. The real commit is not public.

### Checked and not applied

| Commit | Title | Why not |
| --- | --- | --- |
| `bbaf2abfe8f` | ImageDecoder_nCreateFd on host | official `nCreateFd` throws "Only supported on Android" (the r1 code) |
| `9729118333e` | Cross platform native resources | official lacks `duping %d to %d`, has `Implement me` |
| `6e80d1dc9d9` | [Ravenwood] Support resources | no `adoptFd`, no `nativeApplyStyleWithArray` |
| `ce5321e824c` | Remove native tracing on host | official keeps the android.os.Trace table |
| `14f082e4220` | Restrict exported symbols, second form | no `__system_property_*` exports |
| `a86bb7e46466`, `06b30aa5b930` | SDK 36 patches 0002 and 0003 | official `create` uses malloc and `createFromParcel` writes `mAshmemFd` directly: the 2024 form |
| `eae382b9b2c` | Release buffer in HostBufferQueue | official `detachBuffer` is an empty return |
| `01fc279c11d` | nullptr check in Image_getFormat | official dereferences the buffer without a test |
| `60ff9761594` | Java exceptions on ICU load failure | official has `Unable to load ICU data` |
| `8b53f4656c9` | Ravenwood graphics, parcel on Linux | official has `Cannot use parcels outside of Android` |
| `3923961aa8c` | RuntimeXfermode on host | no such class in the official library |
| libbase `38c889f` | host system properties | official `GetProperty` reads the map with no lock |
| `dd7c86dbb68`, `facb96af9f4` | StringBlock and XmlBlock on all platforms, parcel on Linux | no effect on Linux |
| `c044abcbbd3`, `b0e071f39f6` | Dataspace constant in Color.cpp, `<format>` in Bitmap.cpp | source changes only, same generated code |
| `7f86ad5930f` | revert | reverts part of `a8c4d1ad696` that is not applied |
| `0bde9f0ea0d`, `0ef0f5dfef2` | ArrayUtils for host, `attachBuffer` stub | code not present at this tag, or not called |

minikin `e5c9cf7`, `b9de9b2`, `4066fcd`, `736e80b`, native `4ec75f112`, `99510a271`, `ce4d63616`
and libnativehelper `a16d4b5` are for Mac or Windows, or change no generated code.

### Found by the string audit and not applied yet

Skia `d7c30a790` (Remove log spam about Perfetto being unavailable in Android host builds,
2024-11-12) deletes one `SkDebugf`. The official library does not have that string, so it has this
commit or an equivalent. This build still prints `Tracing Skia with Perfetto is not supported in
this environment (host build?)` from `Properties.cpp`: on 4 lines of the arm64 nativegraphics and
ctesque log, 0 lines of the same suites on Google's library. It goes to the log only. Results here are for the
library without the commit. Applying it changes the library, so the rig and suites would have to
run again.

## Toolchain

The tree's Soong (android-15.0.0_r1) differs from SDK 36's in `tools/soong_flags_v.py`:
`-D_FORTIFY_SOURCE=2`, no `-fno-omit-frame-pointer`, C standard gnu17, `-Wno-error=format` in the
common flags, no RTTI flag on host, and no `-Z unstable-options` for Rust.

Soong builds this tag with clang-r522817 (clang 18) and Rust 1.78.0. We use clang 21 and Rust
1.78.0. The official library's `/rustc/9b00956e...` path is the 1.78.0 commit, and this build has
the same one. Deviations for clang 21:

* `-fno-relaxed-template-template-args` and `-Wno-error=enum-constexpr-conversion` are dropped.
  Clang 21 no longer has them.
* `-Wno-error=cast-function-type-mismatch` is added (libutils Threads.cpp), as for `compat`.
* fmtlib: `basic_format_string` evaluates a `FMT_STRING` literal twice. Clang 21 treats the two as
  different objects, so the compile-time check is rejected. The patch hands the same view to both
  places. The check runs at compile time only.

Crates are separate projects under `external/rust/crates` at this tag. `libcxxbridge_macro` is
1.0.119 in its sources although Android.bp still says 1.0.93 (`stale_cargo_pkg_version` in
`aosp.toml`).

## What differs from SDK 36

* Modules only in SDK 35: `android.hardware.graphics.common-V5-ndk`,
  `android.hardware.graphics.composer3-V3-ndk`, `libtracing_perfetto`,
  `libvendorsupport_llndk_headers`, `libz_static`.
* Only in SDK 36: `android.companion.virtualdevice.flags-aconfig-cc`,
  `android.hardware.drm.common-V1-ndk`, `graphics.common-V6-ndk`, `composer3-V4-ndk`,
  `com.android.window.flags.window-aconfig_flags_c_lib`, `hwui_flags_cc_lib`,
  `libaidl_transactions`, `libflags_rust_cpp_bridge`, `native_headers`.
* Exports: SDK 35 has `addKeyRemapping` and three typeinfos. SDK 36 has
  `__android_log_logd_logger_with_timestamp`, four `__system_property_*`,
  `InputDeviceInfo::operator=` and `setKeyRemapping`.
* The official SDK 35 library has no host parcel support for Bitmap or Region, and
  `ImageDecoder.nCreateFd` and `Image.nativeGetFenceFd` do not work on host. This build matches
  that.
* 1,299 JNI methods against 1,328.
* Fatal checks: both official libraries have calls to
  `__android_log_call_aborter("Fatal Error")` with no message, 812 sites at SDK 35 and 317 at SDK 36.
  At SDK 36 this was `core/jni` only (docs/rng-audit.md). At SDK 35 hwui has it too: `Already have an
  AnimationHandle!` is in the official SDK 36 library and not in the SDK 35 one.
* `platform_sdk_version` 35, release config `ap3a`, Rust 1.78.0 against 1.83.0, C gnu17.

## Results

Numbers are from the logs of the build with library SHA-256
`1aea79a5fba64fb53e7786e8b33024161ef047337595d52f3629f738eff7772b`. The x86_64 control library is
`5db6a6ab250ab6f0180b28096768af09b13c0ac83ad5fc91aa8b48dc13f606ea`, same sources and flags.

### Library

* check-so: passes. Highest glibc symbol 2.30 (floor 2.31), 223 exports, NEEDED `libdl.so.2`,
  `libpthread.so.0`, `libm.so.6`, `librt.so.1`, `libc.so.6`, `ld-linux-aarch64.so.1`, which is the
  official list with the arm64 loader.
* `tools/jni_tables.py compare`: identical, 1,299 methods, same tables and same order.
* `tools/jni_tables.py dynsym`: 223 of 223, no differences.
* All class names in the registration maps match the official library.
* `rust/check-live.py`: every non-std Rust source file and marker live in the official library is
  present.
* The x86_64 control library has the same JNI result (1,299 methods, identical), 223 of 223 exports
  and passes `rust/check-live.py`.

### Strings, x86_64 against x86_64

`tools/audit/strdiff.py`, our x86_64 control library against the official one.

Only in ours, 1,208 strings:

| Count | What |
| --- | --- |
| 715 | evdev labels (`ABS_*`, `KEY_*` and so on) from `toolbox_input_labels`. Same as SDK 36, item 3 of the differences in docs/rng-audit.md |
| 163 | mangled and type names |
| 31 | fragments of 7 characters or fewer |
| 8 | Rust paths and panic text |
| 291 | the rest, below |

Of the 291, 198 are direct arguments of `LOG_ALWAYS_FATAL` or `LOG_ALWAYS_FATAL_IF` in hwui and
`core/jni`. 22 are the `com.android.input.flags` names, all 22 in `input_flags.aconfig` (the same
SDK 36 item). 24 are from libc++abi's demangler. The other 47 are mostly fatal-check conditions, log
tags and merged fragments, read by eye and not classified one by one. Two of them need a word:

* `Tracing Skia with Perfetto...`: a missing commit, see "Found by the string audit".
* `%s: No JPEG/HEIC header detected, defaulting to size=width=%d` is an `ALOGW`, not a fatal check,
  in `Image_getBlobSize`. Not explained. The official ImageReader was a hand port, so its version of
  this code is not known.

Only in the official library, 233 strings: 155 mangled and type names (lambda types, compiler
output), 24 `ubsan:` messages, 8 Rust, 6 short, and 40 others:

* `Fatal Error`, the message-less fatal checks.
* The DisplayViewport group (`isActive`, `logicalFrame`, `physicalPort` and so on), the dead code
  listed under "Not verified".
* libc++abi messages (`cannot allocate __cxa_eh_globals` and so on): toolchain.
* Eight class names such as `android.os.Binder`. Our source table has them, but they are not stored
  as whole strings in our binary, so this comparison cannot see them. The JNI tables are identical.
* `Failed to generate random bytes for id`, not explained. See "Not verified".
* Strings that the linker merged differently.

### Fidelity rig

`RIG_SDK=35`, 33 tests pass on arm64, 37 images and 3 text files. Goldens are in
`tests/rig/goldens/x86_64-sdk35` (official library, stock loader, x86_64 JDK under qemu, 33 tests
pass).

* 24 of 37 images identical, 3 of 3 text files identical, worst delta 135 in 8 pixels.
* Nine images differ, with the same numbers as SDK 36: `bitmap-scaling-filters` (29),
  `canvas-transforms-clips` (135 in 8 pixels), and seven with deltas of 1 to 4.
* Four more than SDK 36: `view-light` and `view-dark`, software and pixelcopy, delta 1 in 504 and
  865 pixels. They are single levels on anti-aliased glyph edges. Layout and shapes are the same.

`tests/rig/baseline/arm64-sdk35.json` holds the ceilings.

x86_64 control: our x86_64 library, from the same sources and flags, loaded through the plugin on
the x86_64 JDK 17 under qemu, the same JDK as the goldens (`x86-via-loader` with `RIG_X86_LIB`).
33 tests pass. 37 of 37 images and 3 of 3 text files are identical to the goldens, max delta 0.

What that shows:

* The sources, patches and build flags reproduce Google's output on x86_64 for everything the rig
  covers, so none of them explains the 13 arm64 differences. That includes the four `view-*` images.
* The 13 differences appear only when the configuration changes from x86_64 under qemu to native
  arm64.

What it does not show: which part of that change causes them. Skia's NEON paths are the likely
cause, as measured at SDK 36, but this run changes other things together: compiler output for the
architecture, the JVM, and the glibc `libm` (the qemu sysroot's against the host's). The rig also
covers only these 40 outputs.

### Robolectric suites

`SDKS=35`, native arm64, JDK 21:

| Module | Tests | Pass | Fail | Skip |
| --- | --- | --- | --- | --- |
| robotests | 7,801 | 7,780 | 14 | 7 |
| nativegraphics | 769 | 766 | 1 | 2 |
| ctesque | 429 | 426 | 0 | 3 |

The 15 failures are the same tests as at SDK 36, and are listed in
`ci/upstream-expected-failures-sdk35.txt`:

* 12 in `ShadowSQLiteConnectionTest` and `SQLiteLibraryLoaderTest.shouldExtractNativeLibrary` force
  the LEGACY sqlite4java mode, which has no linux-aarch64 native.
* `ShadowViewThreadTest.testNewestSdk` runs at the newest SDK, not 35, where the stock loader rejects
  Linux arm64.
* `ShadowNativeTableMaskFilterTest.initializationError` fails while creating the test runner.

Against the official library: nativegraphics and ctesque also ran on Google's x86_64 library with
the stock loader, on an x86_64 JDK 21 under qemu (`tests/upstream/scripts/run.sh x86`). Of 1,198
tests in both runs, 0 differ in outcome, including the `ShadowNativeTableMaskFilterTest` failure,
which happens with Google's library too. Full robotests were not run under qemu, which is too slow
here. Its 14 failures are explained by their messages, not by a comparison.

### Notices

The build's notice check reports 49 components, 59 distinct texts, 0 problems.
`tools/check_notice_holders.py`: 1,267 linked sources, 0 holders not in the NOTICE file. The RSA
and Cornell notices of dng_sdk and the Adobe terms are in the file. The Rust standard library entry
is 1.78.0.

## What the loader needs

The loader works today with an override:
`-Drobolectric.arm64.nativeLibrary=/path/libandroid_runtime.so` and
`-Drobolectric.arm64.nativeLibrarySdk=35`. The system properties it sets already fit SDK 35:
`use_base_native_hostruntime`, `core_native_classes`, `graphics_native_classes` and
`method_binding_format`.

For a normal dependency it needs per-SDK library selection. `robolectric.arm64.nativeLibrarySdk`
defaults to 36, and there is a single `ARM64_RESOURCE` path, so a jar with both libraries needs one
resource path per SDK, chosen from the SDK under test.

SDK 35 needs a test JVM of Java 17 or later.

The class list passed in `core_native_classes` comes from Robolectric, so entries that the library
lacks would surface as missing registrations. All class names in the library match the official
list, so this is the same as with Google's library.

## Not verified

* The cause of the 13 arm64 image differences is narrowed down to the arm64 configuration, not to
  one code path. See "Fidelity rig".
* `d7c30a790`: the library tested here does not have it, see "Found by the string audit".
* The message-less fatal checks are not reproduced, because the change is not public. From the
  sources it should only remove text from fatal aborts, but that is not measured. The official
  library has 1,272 fatal call sites (812 + 460) and ours 1,156 (1 + 1,155). Compiler inlining can
  change those totals, so they neither confirm nor rule out that the same checks abort.
* `Failed to generate random bytes for id` is in both official libraries and in no source searched
  here. Its origin is unknown.
* `No JPEG/HEIC header detected` is only in ours and is not explained.
* The official library contains `register_android_hardware_display_DisplayViewport` although
  nothing calls it (no call site, no stored pointer). It is dead code from a host source list, left
  out here. It cannot change behaviour.
* `frameworks/native` 0001 reproduces observed behaviour, not a known commit.
* The suites were not run on the x86_64 control library.
* Tests ran on one arm64 VM with one glibc.
