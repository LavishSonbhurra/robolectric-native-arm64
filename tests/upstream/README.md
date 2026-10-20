# Robolectric's own test suites on the arm64 library

This directory runs three of Robolectric 4.17's own test suites at SDK 36 against the arm64
`libandroid_runtime.so`, with the loader plugin from `loader/` injected into the build. It is the
broad compatibility check; `tests/rig/` is the pixel-level one.

| Module | Upstream sources | Notes |
| --- | --- | --- |
| `robotests` | `robolectric/src/test` | minus 7 files that need SDK 37 APIs (listed in `harness/robotests/build.gradle.kts`) |
| `nativegraphics` | `integration_tests/nativegraphics` | |
| `ctesque` | `integration_tests/ctesque` (`sharedTest`) | with `testapp` |

All tests run with `-Drobolectric.enabledSdks=36`. Robolectric 4.17 defaults to the native
SQLite mode, so every SDK 36 test in these modules loads `libandroid_runtime`, not only the
graphics ones. Each module also gets `harness/probe/`, one test that prints which library file
the test JVM mapped.

## Layout

| Path | What |
| --- | --- |
| `harness/` | Gradle 8.13 project that compiles the upstream test sources against the published Robolectric 4.17 artifacts |
| `harness/probe/` | the probe test |
| `scripts/run.sh` | `run.sh arm64\|x86\|none <name> <gradle args>`, results in `results/<name>/` |
| `scripts/quick.sh` | short arm64 run (ctesque by default) with a summary |
| `scripts/arm64.init.gradle.kts` | init script that injects the loader jar and the library path into any build |
| `scripts/compare.py` | summary of one run, or the per-test outcome diff of two |
| `src/` | shallow clone of robolectric at tag `robolectric-4.17`, made by `run.sh` on first use (not committed, used unmodified) |
| `results/` | run output (not committed) |

The harness does not use Robolectric's own Gradle build, which needs Gradle 9.6, compileSdk 37,
all 15 `android-all` jars and a from-source build of the shadows. It keeps the upstream test
sources and test JVM flags but uses the released jars, which is also what users run. Other
differences from upstream: compileSdk 36, and the tests compile against the plain
`android-all:16-robolectric-13921718` jar (the instrumented jars have non-constant
`VERSION_CODES`).

## Requirements

* Linux arm64 host, JDK 21 (Gradle and the test JVM both need it: `android-all` 16 is class
  file 65).
* Android SDK with `platforms;android-36` and `build-tools;36.0.0`, found through
  `ANDROID_HOME` or `sdk.dir` in `harness/local.properties`.
* The library, by default `build/out/lib/libandroid_runtime.so` at the repository root.
* git and network access for the first run (clone of robolectric, Maven dependencies, and the
  `android-all` jars that Robolectric downloads at test time).
* About 3 GB of RAM for the test JVM with `-Psuite.heap=3g`.

## Running

From the repository root:

```sh
# short check: ctesque only, about 430 tests
tests/upstream/scripts/quick.sh

# all three suites
tests/upstream/scripts/run.sh arm64 full -Psuite.heap=3g \
    :robotests:test :nativegraphics:testDebugUnitTest :ctesque:testDebugUnitTest

# one class
tests/upstream/scripts/run.sh arm64 bitmap :nativegraphics:testDebugUnitTest \
    --tests '*ShadowNativeBitmapTest'

# check the failures against the known list
python3 -I ci/check-upstream-failures.py tests/upstream/results/full/junit \
    --expected ci/upstream-expected-failures.txt
```

`run.sh arm64` builds the loader with `./gradlew :loader:jar` at the repository root unless
`LOADER_JAR` is set. Other environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `ARM64_LIB` | `build/out/lib/libandroid_runtime.so` | library under test |
| `LOADER_JAR` | built from `loader/` | loader plugin jar |
| `JAVA_HOME` | (from the environment) | JDK 21 for Gradle, and the arm64 test JVM |
| `SUITE_JAVA` | `$JAVA_HOME/bin/java` | java executable of the test JVM |
| `GRADLE` | the repository's `gradlew` | Gradle 8.13 command |
| `X86_JAVA` | none | x86_64 JDK 21 `java`, required for mode `x86` |
| `QEMU_LD_PREFIX` | none | x86_64 sysroot for qemu-user (mode `x86`) |
| `ROBOLECTRIC_REF` | `robolectric-4.17` | tag cloned into `src/` |
| `BUILD_LOCK` | none | file to `flock` for the whole run, to serialise with other builds |
| `MIN_MEM_MB` | none | wait until this much memory is available before starting |

Mode `x86` runs the same suites on an x86_64 JDK with the stock loader and the official library
from `android-all`. On an arm64 host that means qemu-user, and it is slow: the subset below took
42 minutes, and the full robotests suite was stopped after 25 minutes without finishing a class.

Gradle-level properties: `-Psuite.heap=3g` (test JVM heap, default 2g), `-Psuite.sdks=36`, and
`-Psuite.robotests.exclude=**/FooTest.java,...` for more exclusions.

The plugin can be injected into any Robolectric 4.17 build the same way:

```sh
gradle -I tests/upstream/scripts/arm64.init.gradle.kts \
    -Parm64.loaderJar=/abs/path/loader.jar \
    -Parm64.nativeLibrary=/abs/path/libandroid_runtime.so test
```

## Results

Full suites on arm64 (2 vCPU Ampere VM, `-Psuite.heap=3g`, about 5 minutes wall):

| Module | Pass | Fail | Skip |
| --- | --- | --- | --- |
| robotests | 7865 | 14 | 7 |
| nativegraphics | 767 | 1 | 2 |
| ctesque | 427 | 0 | 3 |

The same subset on both architectures (81 robotests classes that touch native code, all of
nativegraphics, all of ctesque), pass/fail:

| Run | robotests | nativegraphics | ctesque | Wall |
| --- | --- | --- | --- | --- |
| x86_64 JDK 21 under qemu, stock loader, official library | 1458/0 | 767/1 | 427/0 | 2506 s |
| arm64 JDK 21, loader plugin, this library | 1444/14 | 767/1 | 427/0 | 418 s |

None of the failures is in the library. The list CI checks against is
`ci/upstream-expected-failures.txt`.

| Test | Count | Cause |
| --- | --- | --- |
| `ShadowSQLiteConnectionTest` (12 tests), `SQLiteLibraryLoaderTest.shouldExtractNativeLibrary` | 13 | These force `SQLiteMode.LEGACY`, which uses sqlite4java. sqlite4java has no linux-aarch64 native library: `Architecture 'aarch64' is not supported by SQLite library`. |
| `ShadowViewThreadTest.testNewestSdk` | 1 | Runs at SDK 37, for which there is no arm64 library, so the stock loader refuses: `The Robolectric native runtime is not supported on Linux (aarch64)`. |
| `ShadowNativeTableMaskFilterTest.initializationError` | 1 | `NoClassDefFoundError: android/graphics/TableMaskFilter`. The class is hidden; upstream has `android-all` on the test runtime classpath and this harness only has it at compile time. Fails the same way on x86_64 with the official library. |

## Findings from these suites

The suites found two loader bugs and one library bug, all fixed:

* The loader loaded the library file in place. A second sandbox class loader in the same JVM then
  failed with `UnsatisfiedLinkError: ... already loaded in another classloader`. The loader now
  copies the file into each sandbox's temporary directory, as the stock loader does.
* The loader sent every SDK from 35 up to the arm64 library. Loading the SDK 36 library into an
  SDK 37 sandbox aborts the JVM in `JNI_OnLoad` (`RegisterNatives failed for
  android/graphics/HardwareRenderer`). Only the SDK in `robolectric.arm64.nativeLibrarySdk`
  (default 36) now uses it; other SDKs go to the stock loader, which fails cleanly.
* `Bitmap.copy(Config.HARDWARE, false)`, `Bitmap.createBitmap(Picture)` and HARDWARE decodes
  returned transparent bitmaps, because the host branch of `Bitmap::allocateHardwareBitmap` in
  hwui allocated a heap bitmap without copying the pixels. The official library has the fix,
  which reached AOSP as frameworks/base `30eb173fa210` after our pin; the build applies it as
  `patches/frameworks/base/0001-hwui-host-allocateHardwareBitmap-copies-pixels.patch`.
  It was found by `ShadowNativeBitmapTest.testCreateBitmap_picture_requiresHWAcceleration_checkPixels`.

## Notes

* Each sandbox copies the 62 MB library plus fonts and ICU data into `java.io.tmpdir`, which the
  harness points at `harness/.work/tmp/`. Killed runs leave these copies behind; delete
  `harness/.work/` when it grows.
* JVM crash logs go to `harness/.work/hs_err/` and are copied into `results/<name>/`.
* Test failures do not fail the Gradle build (`ignoreFailures`); use `compare.py` or
  `ci/check-upstream-failures.py` on `results/<name>/junit`.
