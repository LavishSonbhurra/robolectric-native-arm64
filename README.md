# robolectric-native-arm64

Robolectric's native graphics runtime (`libandroid_runtime.so`) built from source for Linux arm64
(aarch64, glibc), plus the Robolectric plugin that loads it.

Robolectric 4.17 runs native graphics and native SQLite for SDK 35 and later through a
`libandroid_runtime.so` that ships inside the `android-all` jar for linux/x86_64, mac/aarch64, mac/x86_64
and windows/x86_64. There is no Linux arm64 build, so tests that need it fail on arm64 CI runners and in
arm64 Linux containers on Apple-silicon Macs with `The Robolectric native runtime is not supported on
Linux (aarch64)`
([robolectric#9166](https://github.com/robolectric/robolectric/issues/9166)). The reason is upstream of
Robolectric: AOSP's build system, Soong, has no glibc Linux arm64 host.

This project reads the same `Android.bp` files Soong reads and generates a CMake build from them, so
moving to a new AOSP release is a change of a tag and not a port.

This is an unofficial community build. It is not affiliated with, endorsed by or supported by Google or the
Robolectric project. "Android" is a trademark of Google LLC.

## Status

* Target: SDK 36, Robolectric 4.17, android-all `16-robolectric-13921718`, AOSP tag `android-16.0.0_r1`
  plus four host fixes from later AOSP tags that the official library also contains
  ([docs/rng-audit.md](docs/rng-audit.md)).
* Platform: Linux arm64 with glibc 2.31 or newer (Debian 11, Ubuntu 20.04, RHEL 9, Amazon Linux 2023 and
  later). Java 21 is required by SDK 36.
* SDK 26 to 34: the compat artifact `robolectric-nativeruntime-compat-linux-aarch64` holds the other
  native library Robolectric uses below SDK 35 (`librobolectric-nativeruntime.so`, the one in
  `nativeruntime-dist-compat` 1.0.19), built from source the same way. A second build of it,
  `robolectric-nativeruntime-compat-linux-aarch64-x86pixels`, renders exactly like the x86_64 library
  under qemu. See [docs/COMPAT.md](docs/COMPAT.md). Not covered: SDK 37. SDK 35 is untested.
* Released on GitHub:
  [v4.17-16-robolectric-13921718-1](https://github.com/LavishSonbhurra/robolectric-native-arm64/releases/tag/v4.17-16-robolectric-13921718-1),
  built and attested by CI on GitHub's arm64 runners. Publishing to Maven Central comes later.

## Quick start

Coordinates:

| | |
| --- | --- |
| Group | `io.github.lavishsonbhurra` |
| Artifact | `robolectric-nativeruntime-linux-aarch64` |
| Version | `4.17-16-robolectric-13921718-1` (Robolectric, android-all build, revision) |

Until the artifact is on Maven Central, download the jar from the
[GitHub releases](https://github.com/LavishSonbhurra/robolectric-native-arm64/releases) and use it as a
file dependency.

```kotlin
dependencies {
    testImplementation("org.robolectric:robolectric:4.17")
    // Inert on every platform except Linux aarch64.
    testRuntimeOnly("io.github.lavishsonbhurra:robolectric-nativeruntime-linux-aarch64:4.17-16-robolectric-13921718-1")
    // Only for tests at SDK 26 to 34 (needs loader 4.17-16-robolectric-13921718-2 or later). For
    // x86-identical pixels use robolectric-nativeruntime-compat-linux-aarch64-x86pixels instead:
    // testRuntimeOnly("io.github.lavishsonbhurra:robolectric-nativeruntime-compat-linux-aarch64:1.0.19-1")
    // Before Maven Central: testRuntimeOnly(files("libs/robolectric-nativeruntime-linux-aarch64-4.17-16-robolectric-13921718-1.jar"))
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) })
    jvmArgs(
        "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED",
    )
    systemProperty("robolectric.graphicsMode", "NATIVE")
}
```

Then run your tests as usual, for example with `@Config(sdk = [36])`. On any other platform the stock
Robolectric loader is used, so the same build file works on x86_64 and macOS machines.

To load a library you built yourself instead of the bundled one:
`-Drobolectric.arm64.nativeLibrary=/abs/path/libandroid_runtime.so`.

More in [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md): Maven usage, the version scheme, and how new
Robolectric and android-all releases are handled.

## How it was verified

Three kinds of evidence, all reproducible with the code in this repository.

**Structure.** The library exports the same 226 symbols as the official x86_64 library and registers the
same 1,328 JNI methods in the same tables and the same order. A post-link checker enforces the glibc
floor (highest symbol version GLIBC_2.30), the allowed `NEEDED` entries, the export list, `RELRO` and
`BIND_NOW`. CI repeats the JNI and export comparison against the official library on every build.

**Robolectric's own test suites.** `robolectric/src/test` (minus 7 files that need SDK 37),
`integration_tests/nativegraphics` and `integration_tests/ctesque`, compiled against the published 4.17
artifacts and run with `-Drobolectric.enabledSdks=36` on a native arm64 JVM:

| Module | Tests | Pass | Fail | Skipped |
| --- | --- | --- | --- | --- |
| robotests | 7,886 | 7,865 | 14 | 7 |
| nativegraphics | 770 | 767 | 1 | 2 |
| ctesque | 430 | 427 | 0 | 3 |
| Total | 9,086 | 9,059 | 15 | 12 |

None of the 15 failures involves the library: 13 tests force the legacy sqlite4java mode, which has no
linux-aarch64 native; one runs at SDK 37; one (`ShadowNativeTableMaskFilterTest`) fails the same way with
the official library in this harness. The full run takes about 5 minutes on a 2-core Ampere Altra (Neoverse-N1) VM with 11 GB RAM.
The same suites on the official x86_64 library under qemu-user were estimated at over three hours, so
the comparison with the official library was made on a subset: 81 native-relevant robotests classes plus
all of nativegraphics and ctesque, about 2,650 tests. On that subset both libraries fail
`ShadowNativeTableMaskFilterTest`, and the arm64 build additionally fails only the SQLite and SDK 37
tests above.

**Pixels.** A rig renders 37 scenes (canvas, bitmaps and codecs, text in 12 scripts, framework views,
Compose Material 3) through `PixelCopy` and Roborazzi and compares them with goldens made by the official
x86_64 library:

* The same tree built for **x86_64** and run under qemu-user renders **37 of 37 images identical to the
  official library**, maximum difference 0. So the build recipe (flags, toolchain, closure) is faithful.
* The **arm64** build renders 28 of 37 images identical. The other nine differ by 1 to 4 levels per
  channel in seven images, by up to 29 levels in one (a rotated bilinear bitmap) and by 135 levels in
  8 pixels of one (a perspective shader sample landing on the neighbouring texel). These differences come
  from Skia's NEON code paths, not from the build: NEON reciprocal estimates with a different number of
  Newton steps, an exact `div255` where the SSE path is off by one, a legacy fixed-point sampler that
  exists only on ARM. Google's own mac/aarch64 library is built from the same Skia with NEON enabled and
  should show the same differences; this has been reasoned from the code and not tested on a Mac.
  If you use screenshot tests, goldens recorded on x86_64 need a tolerance of a few levels on arm64.
  The rig keeps per-image ceilings in `tests/rig/baseline/arm64.json` so that an image cannot get worse
  unnoticed.

Details, including the audit of later AOSP host fixes, are in [docs/NOTES.md](docs/NOTES.md),
"Verification".

## Limitations

* **One SDK, one android-all build.** The library registers natives for one android-all build. The loader
  uses it only for SDK 36 and hands every other SDK to the stock loader, because a mismatch aborts the JVM
  in `JNI_OnLoad`.
* **Reflection into Robolectric 4.17.** The plugin calls private methods of `DefaultNativeRuntimeLoader`.
  It fails with a message naming the missing method when a Robolectric release renames one, but each
  Robolectric release needs a check.
* **Sandboxes copy the library.** Each Robolectric sandbox extracts the library, fonts and ICU data under
  `java.io.tmpdir` (tens of MB per sandbox). Put it on disk if `/tmp` is in memory.
* **Reproducible with the same compiler packages.** A local build and two CI builds in different
  directories gave the same stripped library, byte for byte. The CI image is pinned by digest, but the
  clang and lld package revisions come from the Ubuntu archive at build time, so a later package update
  can change the output ([docs/reproducibility.md](docs/reproducibility.md)).
* **Architecture details.** `char` is unsigned and `long double` is IEEE binary128 on aarch64. SQLite may
  round a text-to-real conversion near the precision limit differently from the x86_64 library.

## Building from source

On Ubuntu 26.04 arm64:

```
sudo apt-get install clang lld llvm cmake ninja-build python3 patch libc++-21-dev libc++abi-21-dev \
    rustc cargo flex bison git curl xz-utils ca-certificates gnupg gpgv debian-archive-keyring
tools/fetch.py                           # AOSP sources into src/, about 0.9 GB, verified against the lock file
rust/install-toolchain.sh                # rustc 1.83.0 (SHA-256 and signature checked)
python3 -I toolchain/make-sysroot.py     # Debian 11 arm64 sysroot, about 30 MB
toolchain/build-runtimes.sh              # static libc++, libc++abi, libunwind 21.1.8
cmake -S . -B build/out -G Ninja -DRA64_USE_SYSROOT=ON
ninja -C build/out -j2                   # build/out/lib/libandroid_runtime.so and NOTICE
```

A clean build takes 35 to 45 minutes with `-j2` on a 2-core Ampere Altra (Neoverse-N1) VM with 11 GB RAM. Each parallel job needs about
1.2 GB of RAM, and the whole build about 4 GB of disk. `ci/build.sh` runs the same sequence plus the
checks, stripping and checksums.

[docs/BUILDING.md](docs/BUILDING.md) has the details: what each step verifies, the x86_64 control build,
the comparison with the official library, the loader jar, and moving to another AOSP release.
[docs/NOTES.md](docs/NOTES.md) explains how Soong's rules are mirrored, where each compiler flag comes
from, and the deviations from Soong.

The fidelity rig and the harness for Robolectric's own suites are in `tests/` (`tests/rig/README.md`,
`tests/upstream/README.md`).

## Repository layout

| Path | What |
| --- | --- |
| `config/`, `overrides/`, `patches/` | The AOSP pin, the projects to fetch, lock files, manual build knowledge, source patches |
| `tools/`, `cmake/`, `CMakeLists.txt` | The `Android.bp` to CMake generator and the CMake build |
| `toolchain/`, `rust/` | Debian 11 sysroot, LLVM runtimes, the pinned Rust toolchain and the Rust part of the library |
| `loader/` | The Robolectric `NativeRuntimeLoader` plugin, packaged as the published jar |
| `tests/rig/` | Fidelity rig: scenes, x86_64 goldens, arm64 baseline |
| `tests/upstream/` | Harness for Robolectric's own test suites |
| `ci/`, `.github/workflows/` | CI build script, checks and the GitHub Actions workflow |
| `docs/` | Build notes, licensing audit, distribution and reproducibility notes |

## Licenses

The scripts, the loader plugin, the rig and the documentation in this repository are licensed under the
Apache License 2.0 (see `LICENSE` and `NOTICE`).

The compiled library is built from the Android Open Source Project and other open source projects under
their own licenses. The build writes their notices to `NOTICE` next to the library; releases ship that
file as `THIRD_PARTY_NOTICES`, next to the library and inside the jar. Notices that the licenses require
to be displayed with binary redistributions:

* This product includes DNG technology under license by Adobe Systems Incorporated.
* This product includes Gain Map technology under license by Adobe.
* This software is based in part on the work of the Independent JPEG Group.
* This software is based in part on the work of the FreeType Team. Portions of this software are
  copyright (c) 2023 The FreeType Project (www.freetype.org). All rights reserved. FreeType is used under
  the FreeType License.

The library includes Adobe's DNG SDK, which is distributed under the DNG SDK License Agreement. Among its
terms, a party that distributes the software in a commercial product agrees to indemnify Adobe against
claims arising from that distribution (section 5). Using the library as a test dependency does not
redistribute it. If you ship it inside a product, read that agreement first. The official Robolectric
library contains the same component.

[docs/LICENSING.md](docs/LICENSING.md) has the full audit.
