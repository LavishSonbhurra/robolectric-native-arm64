# Building from source

These steps build `libandroid_runtime.so` for SDK 36 from the AOSP tag `android-16.0.0_r1`. They were
run end to end on Ubuntu 26.04 arm64, for both target architectures. `ci/build.sh` runs the same
sequence for the arm64 release build, plus the checks, stripping and checksums.

## Requirements

* An arm64 Linux machine. The instructions assume Ubuntu 26.04; other distributions need the same tools
  (clang and lld 21, CMake, Ninja, Python 3, flex, bison, a system Rust for the build-time tools).
* About 4 GB of disk: sources 0.9 GB, build output 1.2 GB, toolchains and downloads 1.6 GB.
* About 1.2 GB of RAM per parallel job. The largest compiler process peaks at about 1.15 GB.
* Network access to android.googlesource.com, snapshot.debian.org, the LLVM and Rust release
  servers, and crates.io. Every download is checked against a hash in this repository.

```
sudo apt-get install clang lld llvm cmake ninja-build python3 patch libc++-21-dev libc++abi-21-dev \
    rustc cargo flex bison git curl xz-utils ca-certificates gnupg gpgv debian-archive-keyring
```

## Release build (arm64, glibc 2.31 floor)

```
tools/fetch.py                          # AOSP sources into src/, about 0.9 GB
rust/install-toolchain.sh               # rustc 1.83.0 into rust/toolchain/
python3 -I toolchain/make-sysroot.py    # Debian 11 arm64 sysroot, about 30 MB
toolchain/build-runtimes.sh             # static libc++, libc++abi, libunwind 21.1.8
cmake -S . -B build/out -G Ninja -DRA64_USE_SYSROOT=ON
ninja -C build/out -j2
```

What each step checks:

* `tools/fetch.py` resolves every project of `config/projects.toml` to the commit the tag points at,
  downloads it from Gitiles, compares the content hash of the extracted tree with
  `config/sources.lock.json` (it refuses any difference) and then applies `patches/`.
* `rust/install-toolchain.sh` checks the SHA-256 and the signature of the Rust tarball.
* `toolchain/make-sysroot.py` downloads the Debian 11 packages from snapshot.debian.org at a fixed
  timestamp and checks them against `toolchain/sysroot.lock.json`.
* `toolchain/build-runtimes.sh` checks the SHA-256 and the signature of the LLVM source tarball.
* The CMake configure step runs `tools/bp2cmake.py`, which reads the `Android.bp` files and writes the
  build. Rust crates for the build-time tools are fetched by cargo; their versions are fixed by the
  lock files in `tools/cargo/`.

Output in `build/out/lib/`:

* `libandroid_runtime.so`, unstripped (about 63 MB; 15 MB after `llvm-strip --strip-all`).
* `NOTICE`, the license texts of everything linked into the library. The build fails if a linked part
  has no license entry. `ninja -C build/out libandroid_runtime_notices` runs the license check alone.
* The static libraries of the closure. Host tools (`aidl`, `aprotoc`, `sysprop_cpp`, ...) are in
  `build/out/bin/`.

The link runs `toolchain/check-so.py`, which enforces the glibc floor (highest symbol version
GLIBC_2.30), the allowed `NEEDED` entries, the export list, `RELRO` and `BIND_NOW`.

Measured on a 2-core Ampere Altra (Neoverse-N1) VM with 11 GB RAM, with `-j2`: 35 to 45 minutes for a clean build including the Rust parts.

Without `-DRA64_USE_SYSROOT=ON` (and without the sysroot and runtime steps) the library builds against
the machine's own glibc and libc++. That is faster to set up, but the result is only guaranteed to
load on the machine that built it.

## x86_64 build (control build)

The same tree builds for x86_64, cross-compiled on arm64. The build-time code generators are taken from
a native arm64 build, so do the arm64 build first. The x86_64 library is not distributed; it exists to
compare this build recipe against Google's x86_64 library without architecture effects
([NOTES.md](NOTES.md), "Architectures").

```
sudo apt-get install yasm                # libjpeg-turbo's x86 SIMD code
python3 -I toolchain/make-sysroot.py --arch amd64
toolchain/build-runtimes.sh --arch x86_64
rust/install-toolchain.sh --target x86_64-unknown-linux-gnu
cmake -S . -B build/x86_64 -G Ninja -DRA64_USE_SYSROOT=ON -DRA64_ARCH=x86_64 \
      -DRA64_HOST_TOOLS_DIR=$PWD/build/out/bin
ninja -C build/x86_64 -j2
```

About 40 minutes with `-j2` on the same machine.

## Checks against the official library

`tools/jni_tables.py` compares the JNI registration tables and the exported symbols with the official
x86_64 library from the `android-all` jar. The jar is not part of this repository; Robolectric
downloads it into the local Maven repository the first time an SDK 36 test runs.

```
jar=~/.m2/repository/org/robolectric/android-all-instrumented/16-robolectric-13921718-i7/android-all-instrumented-16-robolectric-13921718-i7.jar
mkdir -p ref && unzip -qo -j "$jar" native/linux/x86_64/libandroid_runtime.so -d ref
python3 -I tools/jni_tables.py compare ref/libandroid_runtime.so build/out/lib/libandroid_runtime.so
python3 -I tools/jni_tables.py dynsym ref/libandroid_runtime.so build/out/lib/libandroid_runtime.so
```

Use the unstripped library: the comparison groups methods into tables by our symbols. `ref/` is in
`.gitignore`; do not commit the official library.

## The loader jar

The loader plugin lives in `loader/`. To build the jar with your library inside:

```
./gradlew :loader:jar -Pra64.nativeLib=$PWD/build/out/lib/libandroid_runtime.so
```

Strip the library first (`llvm-strip --strip-all`) if the jar is meant for distribution. To test a
library without building a jar, pass `-Drobolectric.arm64.nativeLibrary=/abs/path/libandroid_runtime.so`
to the test JVM.

## Tests

* `tests/rig/`: the fidelity rig. It renders 37 scenes with the library and compares them with goldens
  made by the official x86_64 library. See `tests/rig/README.md`.
* `tests/upstream/`: runs Robolectric's own test suites against the library. See
  `tests/upstream/README.md`.

## Debugging the generated build

```
tools/bp2cmake.py --out /tmp/x --binary-dir /tmp/y --explain <module>
```

prints how a module was resolved (variants, defaults, `select()` branches) and its exact compiler
command lines.

## Moving to another AOSP release

1. Edit `config/aosp.toml` (tag, release config).
2. Run `tools/fetch.py`. It resolves every project again, and `config/sources.lock.json` changes
   accordingly.
3. Re-run CMake and fix what `bp2cmake.py` reports: missing projects go in `config/projects.toml`,
   everything else in `overrides/overrides.toml` or `patches/`.
4. Run the checks above, the rig and the upstream suites. The library must match the `android-all`
   build Robolectric uses for that SDK.

[NOTES.md](NOTES.md) explains how Soong's rules are mirrored, where every compiler flag comes from, and
each deviation from Soong.
