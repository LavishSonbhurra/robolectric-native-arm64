# Reproducibility of libandroid_runtime.so

Current claim: the stripped `libandroid_runtime.so` (arm64) is reproducible bit for bit with the pinned
inputs and the same compiler package revisions. Shown on 2026-10-20 for the source of the first release:
a local build on an Ampere Altra VM (Ubuntu 26.04 host, checkout under the home directory), the CI
`build` job (`ubuntu:26.04` container on a GitHub `ubuntu-24.04-arm` runner) and the CI `reproduce` job
(a clean runner, a different directory, `-j3`) gave the same file, SHA-256
`cf3815f778cc2ef9e1c56510f617d98949b77f738966f650ce7718b0438f6c64`, build-id
`366cf8c87a5de93f75b4a470f30695e4a8d16655`. The `reproduce` job in `.github/workflows/build.yml` keeps
testing this and fails on any byte of difference.

## What the comparison covers

The distributed file is the stripped library (`llvm-strip --strip-all`, dynamic symbols kept). Its GNU
build-id is `--build-id=sha1`, a hash of the unstripped output including its debug info, so equal
build-ids also mean equal unstripped files and equal `.debug` files. A path that leaks into the debug
info shows up as a difference in the 20 build-id bytes only; `ci/compare-libs.py` reports that case
separately (exit status 3) to make it easy to recognise.

## Inputs, and how each is pinned

| Input | Pinned by | Gap |
| --- | --- | --- |
| AOSP sources, about 60 projects | `config/sources.lock.json`: commit and content hash per project; `fetch.py` refuses any difference | None. The tarball hash is recorded but not enforced (Gitiles gzip output is not stable); the extracted-tree hash is. |
| LLVM 21.1.8 source (libc++, libc++abi, libunwind, compiler-rt) | SHA-256 and detached signature in `build-runtimes.sh` | None. |
| Rust 1.83.0 (staticlib compiler, std) | SHA-256 and signature in `install-toolchain.sh` | None. |
| Debian 11 sysroot (glibc 2.31, GCC 10 runtime) | snapshot.debian.org timestamp, `InRelease` hash, per-package hash in `toolchain/sysroot.lock.json` | None. |
| Cargo crates for the host tools (aconfig, cxxbridge) | `tools/cargo/*.Cargo.lock` | The host tools generate code that ends up in the library; their binaries do not. Output is deterministic for a given tool version. |
| **Compiler and linker that build the C++** | Ubuntu 26.04 packages `clang-21` 21.1.8-6ubuntu1, `lld-21`, `llvm-21` | **Partly pinned.** CI runs in an `ubuntu:26.04` image pinned by digest, but `apt-get` installs the archive's current package versions. A package revision change alters at least the `.comment` section ("Ubuntu clang version 21.1.8 (6ubuntu1)", "Linker: Ubuntu LLD 21.1.8") and may alter code; `build-info.txt` in every build records the versions used. A full pin would install from the Ubuntu snapshot service. |
| cmake, ninja, python3, flex, bison, system rustc/cargo (host tools only) | Ubuntu 26.04 packages | Not pinned; they influence generated files only if their output formats change. Pinned by the same container digest. |

## What can make two builds differ, and what the build does about it

| Source of variation | Status |
| --- | --- |
| Absolute source paths in `__FILE__`, assert and log strings | Handled. Every compile gets `-ffile-prefix-map=<src>/=` and `-ffile-prefix-map=<gen root>/=out/gen/` (`tools/soong_flags.py`). A `strings` scan of an unstripped build found no home-directory or build-directory path. |
| Checkout and build directory in debug info (`DW_AT_comp_dir`, `.debug_line`, sysroot headers) | Handled. Soong's `-fdebug-prefix-map=/proc/self/cwd=` does nothing here because we compile from the build directory, so every compile also gets `-ffile-prefix-map=<checkout>=.` and `-ffile-prefix-map=<build dir>=out`, before the two maps above (clang applies the last matching map). The only absolute paths left in the debug info are the same on every machine: `/usr/lib/clang/21`, `/rustc/<commit>`, `/rust/deps`, `/cargo/registry` (from the Rust toolchain) and `/x-tools` (from the Debian GCC runtime objects). |
| Rust paths | Handled by design: rustc runs with the source tree as working directory and `-Z remap-cwd-prefix=.`; std comes from the verified tarball (`/rustc/<commit>/library/...` strings). |
| LLVM runtime paths | `build-runtimes.sh` maps the LLVM source directory to `out/llvm-project/`, its build directory to `out/runtimes` and the rest of `toolchain/` (the sysroot) to `toolchain`. |
| Time | `__DATE__`/`__TIME__` are errors (`-Werror=date-time`, in Soong's global flags). `llvm-ar` writes uid 0 and date 1970 (checked: `adler32.c.o` in `libz.a`). No timestamps in the link. `SOURCE_DATE_EPOCH` is exported for any tool that honours it. |
| Archive and link order | Member order follows the generated CMake source lists; link order is Soong's dependency order. Both come from Python code that sorts its inputs (24 `sorted()` calls; the only unsorted `glob` calls are in `release_config.py` for flag declarations, to be audited). `PYTHONHASHSEED=0` is set so that no set or dict order depends on the process. |
| Parallelism (`-j`) | The reproduce job uses `-j3` against `-j4` in the first build. Object files do not depend on scheduling; lld output is deterministic with its default threading. ThinLTO is used only inside the Rust staticlib (one codegen unit per crate), also deterministic in principle. |
| Host CPU | No `-march=native` or `-mcpu=native` anywhere; target flags are fixed (`-march=armv8-a`). Cobalt 100 and Ampere hosts should give the same bytes. |
| Locale, timezone, user, hostname | `LC_ALL=C.UTF-8`, `TZ=UTC` are set; nothing in the outputs records user or host. |
| Compressed debug sections | `--compress-debug-sections=zstd` is deterministic for a fixed libzstd, and irrelevant after stripping. |
| Network | Fetches are verified by hash, so the same bytes are used regardless of mirror or order. |

## The job

`reproduce` (in `build.yml`):

1. starts from a clean runner and a clean container: no cache restore, so the sources, toolchains and Cargo
   crates are downloaded again;
2. unpacks `git archive HEAD` into `/opt/ra64-second` (a different path from the checkout used by `build`);
3. runs `ci/build.sh -j3` (the first build used `-j4`);
4. byte-compares `THIRD_PARTY_NOTICES` and the stripped library with the first build's artifact
   (`ci/compare-libs.py`). Any difference fails the job, including one confined to the build-id;
5. on a failure runs `diffoscope` over both libraries and uploads the report.

It runs weekly, on release tags and on request, not on every push, because it costs another 40 to 60
minutes of runner time.

Optional quick check (not in the workflow): generate the CMake files twice with different
`PYTHONHASHSEED` values and different build directories and diff `cmake-gen/` after replacing the
directory names. This catches ordering bugs in `bp2cmake.py` in a minute without compiling anything.

## What would still not be reproduced

* A build on another Ubuntu release or with a different clang package revision.
* A build with a different `-DRA64_USE_SYSROOT` setting (no sysroot gives a library that needs glibc
  2.43; it is not a release configuration).
* The x86_64 control build has not been compared across machines; it is not distributed.
