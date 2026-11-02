# Building from source

These steps build `libandroid_runtime.so` for SDK 36 from the AOSP tag `android-16.0.0_r1`. They were
run end to end on Ubuntu 26.04 arm64, for both target architectures. `ci/build.sh` runs the same
sequence for the arm64 release build, plus the checks, stripping and checksums.

One tree builds every library. `RA64_TARGET` picks one, and each target has its own sources, build
directory and Rust:

| Target | Library | AOSP | Rust | Sources | Clean build, 2 cores, `-j2` | Stripped size |
| --- | --- | --- | --- | --- | --- | --- |
| `sdk35` | `libandroid_runtime.so`, SDK 35 | `android-15.0.0_r1` plus 36 patches | 1.78.0 | `src-sdk35/`, 0.9 GB | 68 min | 14.6 MB |
| `sdk36` (default) | `libandroid_runtime.so`, SDK 36 | `android-16.0.0_r1` | 1.83.0 | `src/`, 0.9 GB | 35 to 45 min | 15.2 MB |
| `sdk37` | `libandroid_runtime.so`, SDK 37 | `android-17.0.0_r1` plus 3 patches | 1.93.1 | `src-sdk37/`, 1.8 GB | 2 h 23 min | 24.0 MB |
| `compat` | `librobolectric-nativeruntime.so`, SDK 26 to 34 | `android12-hostruntime-dev` | none | `src-compat/` | 20 min | 15.3 MB |

The steps below are for `sdk36`. For the others, see "The other targets".

## Requirements

* An arm64 Linux machine. The instructions assume Ubuntu 26.04; other distributions need the same tools
  (clang and lld 21, CMake, Ninja, Python 3, flex, bison, a system Rust for the build-time tools).
* About 4 GB of disk: sources 0.9 GB, build output 1.2 GB, toolchains and downloads 1.6 GB.
* About 1.2 GB of RAM per parallel job. The largest compiler process peaks at about 1.15 GB.
* Network access to android.googlesource.com, snapshot.debian.org, the LLVM and Rust release
  servers, and crates.io. Every download is checked against a hash in this repository.

```
sudo apt-get install clang lld llvm cmake ninja-build python3 patch libc++-21-dev libc++abi-21-dev \
    rustc cargo flex bison git curl xz-utils ca-certificates gnupg gpgv debian-archive-keyring \
    libclang1-21
```

`libclang1-21` is for bindgen, which only the `sdk37` target runs.

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

## The other targets

Each one needs its own Rust, because Soong's Rust version is pinned per AOSP release and the library
holds that compiler's standard library. They install next to each other under `rust/`.

```
rust/install-toolchain.sh --version 1.78.0      # rust/toolchain-1.78.0, for sdk35
RA64_TARGET=sdk35 python3 -I tools/fetch.py     # src-sdk35/
cmake -S . -B build/sdk35 -G Ninja -DRA64_TARGET=sdk35 -DRA64_USE_SYSROOT=ON
ninja -C build/sdk35 -j2

rust/install-toolchain.sh --version 1.93.1      # rust/toolchain-1.93.1, for sdk37
RA64_TARGET=sdk37 python3 -I tools/fetch.py     # src-sdk37/
cmake -S . -B build/sdk37 -G Ninja -DRA64_TARGET=sdk37 -DRA64_USE_SYSROOT=ON
ninja -C build/sdk37 -j2
```

The sysroot and the C++ runtimes are shared. `ci/build.sh --sdk 35` does all of it with the checks,
stripping and checksums, and `ci/build-compat.sh` does the same for `compat`. `ci/sdk-env.sh` lists what
differs between the targets. Inputs and results per target: [SDK35.md](SDK35.md), [SDK37.md](SDK37.md),
[COMPAT.md](COMPAT.md).

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

## The jars

The loader is a jar of its own and holds no library. Each library has its own jar. Strip the library
first (`ci/build.sh` does) if the jar is meant for distribution.

```
./gradlew :loader:jar
./gradlew :sdk35:jar -Pra64.sdk35Lib=$PWD/dist/libandroid_runtime.so   # also :sdk36, :sdk37
./gradlew :compat:jar -Pra64.compatLib=$PWD/dist-compat/librobolectric-nativeruntime.so
```

The notices file next to the library goes into the jar. All of them together, as a Maven repository in
`build/central-staging` (each library needs its property):

```
./gradlew publishAllPublicationsToStagingRepository -Pra64.sdk35Lib=... -Pra64.sdk36Lib=... \
    -Pra64.sdk37Lib=... -Pra64.compatLib=... -Pra64.compatX86Lib=...
```

To test a library without building a jar, pass
`-Drobolectric.arm64.nativeLibrary=/abs/path/libandroid_runtime.so` to the test JVM, with
`-Drobolectric.arm64.nativeLibrarySdk=<sdk>` if it is not for SDK 36.

## Tests

* `tests/rig/`: the fidelity rig. It renders 37 scenes with the library and compares them with goldens
  made by the official x86_64 library, one set per SDK. `RIG_ARTIFACT_REPO` runs it through the jars in
  a Maven repository, the way a user's build gets them. See `tests/rig/README.md`.
* `tests/upstream/`: runs Robolectric's own test suites against the library. See
  `tests/upstream/README.md`.

## Debugging the generated build

```
tools/bp2cmake.py --out /tmp/x --binary-dir /tmp/y --explain <module>
```

prints how a module was resolved (variants, defaults, `select()` branches) and its exact compiler
command lines.

## Moving to another AOSP release

A new SDK level gets its own target, as `config/sdk35/` and `config/sdk37/` did: a directory with the
files below, a branch in `tools/target.py` and `CMakeLists.txt`, an entry in `ci/sdk-env.sh`, a project
under `libraries/` and a value for `NEWEST_LIBRARY_SDK` in the loader. The steps are the same either way.

1. Edit `config/aosp.toml` (tag, release config).
2. Run `tools/fetch.py`. It resolves every project again, and `config/sources.lock.json` changes
   accordingly.
3. Re-run CMake and fix what `bp2cmake.py` reports: missing projects go in `config/projects.toml`,
   everything else in `overrides/overrides.toml` or `patches/`.
4. Run the checks above, the rig and the upstream suites. The library must match the `android-all`
   build Robolectric uses for that SDK.

[NOTES.md](NOTES.md) explains how Soong's rules are mirrored, where every compiler flag comes from, and
each deviation from Soong.
