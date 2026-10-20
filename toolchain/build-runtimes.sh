#!/bin/bash
# Build static libc++, libc++abi and LLVM libunwind against the Debian 11
# sysroot (toolchain/make-sysroot.py) with the system clang, from the LLVM
# release that matches it, plus compiler-rt's UBSan minimal runtime.
#
# Output: toolchain/out/runtimes/{include/c++/v1,lib/libc++.a,libc++abi.a,
# libunwind.a,...} for arm64, toolchain/out/runtimes-<arch>/ otherwise.
# libc++.a also contains libc++abi and libunwind, as in AOSP's host
# prebuilts, so linking libc++.a alone is enough; the separate archives are
# installed too. lib/linux/libclang_rt.ubsan_minimal-<cpu>.a is the runtime
# Soong links into shared libraries with sanitized static dependencies
# (the system clang ships it for the build machine's architecture only).
#
# The configuration mirrors toolchain/llvm_android (base_builders.py,
# LLVMBuilder.cmake_defines, Linux runtimes), which builds the libc++ that
# Soong's host libc++_static uses:
#   LIBCXXABI_USE_LLVM_UNWINDER=ON, LIBCXXABI_ENABLE_STATIC_UNWINDER=ON,
#   LIBCXX_ENABLE_STATIC_ABI_LIBRARY=ON, LIBCXX_HAS_ATOMIC_LIB=NO,
#   LIBCXX_ENABLE_ABI_LINKER_SCRIPT=OFF, CMAKE_POSITION_INDEPENDENT_CODE=ON,
#   CMAKE_BUILD_TYPE=Release, everything else at LLVM's defaults (ABI v1,
#   namespace __1, exceptions and RTTI on, hardening mode none, libc++abi and
#   libunwind assertions on).
# Ours differs in: static archives only (no .so), no tests or benchmarks,
# glibc 2.31 instead of glibc 2.17.
#
# The licence texts of the four components go to
# <prefix>/share/licenses/<component>/LICENSE.TXT, where tools/gen_notices.py
# reads them. --licenses-only installs just those into an existing prefix
# (no build).
#
# Usage: toolchain/build-runtimes.sh [--arch arm64|x86_64] [-j N] [--licenses-only]
#        (defaults: arm64, -j2; x86_64 uses the amd64 sysroot)
set -euo pipefail

LLVM_VERSION=21.1.8
TARBALL=llvm-project-${LLVM_VERSION}.src.tar.xz
TARBALL_SHA256=4633a23617fa31a3ea51242586ea7fb1da7140e426bd62fc164261fe036aa142
URL=https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VERSION}
KEYS_URL=https://releases.llvm.org/release-keys.asc
# Douglas Yung, LLVM release signing key (signed the 21.1.8 tarballs).
SIGNER_FPR=FFB3368980F3E6BB5737145A316C56D064CACBA5
GCC_VERSION=10

JOBS=2
ARCH=arm64
LICENSES_ONLY=0
while [[ $# -gt 0 ]]; do
  case $1 in
    --licenses-only) LICENSES_ONLY=1; shift ;;
    -j) JOBS=$2; shift 2 ;;
    -j?*) JOBS=${1#-j}; shift ;;
    --arch) ARCH=$2; shift 2 ;;
    --arch=*) ARCH=${1#--arch=}; shift ;;
    *) echo "usage: $0 [--arch arm64|x86_64] [-j N] [--licenses-only]" >&2; exit 2 ;;
  esac
done
case $ARCH in
  arm64)  TRIPLE=aarch64-linux-gnu; DEB_ARCH=arm64; CPU=aarch64; SUFFIX= ;;
  x86_64) TRIPLE=x86_64-linux-gnu;  DEB_ARCH=amd64; CPU=x86_64;  SUFFIX=-x86_64 ;;
  *) echo "unknown arch $ARCH" >&2; exit 2 ;;
esac

HERE=$(cd "$(dirname "$0")" && pwd)
SYSROOT=$HERE/out/sysroot-bullseye-$DEB_ARCH
PREFIX=$HERE/out/runtimes$SUFFIX
DL=$HERE/dl/llvm-$LLVM_VERSION
BUILD=$HERE/build/runtimes$SUFFIX
SRC=$DL/llvm-project-$LLVM_VERSION.src

log() { echo "build-runtimes: $*"; }

[[ -f $SYSROOT/.ra64-sysroot.json ]] || { log "no sysroot; run toolchain/make-sysroot.py --arch $DEB_ARCH first"; exit 1; }

clang_major=$(clang -dumpversion | cut -d. -f1)
if [[ $clang_major != "${LLVM_VERSION%%.*}" ]]; then
  log "warning: system clang is $(clang -dumpversion), runtimes are $LLVM_VERSION"
fi

mkdir -p "$DL"
if [[ ! -f $DL/$TARBALL ]] || [[ $(sha256sum "$DL/$TARBALL" | cut -d' ' -f1) != "$TARBALL_SHA256" ]]; then
  log "downloading $TARBALL"
  curl -fL --retry 3 -o "$DL/$TARBALL.part" "$URL/$TARBALL"
  mv "$DL/$TARBALL.part" "$DL/$TARBALL"
fi
got=$(sha256sum "$DL/$TARBALL" | cut -d' ' -f1)
[[ $got == "$TARBALL_SHA256" ]] || { log "SHA256 mismatch: $got"; exit 1; }
log "SHA256 ok"

# Signature: the pinned hash is the real check; the signature shows the hash
# was pinned from a tarball the release manager signed.
[[ -f $DL/$TARBALL.sig ]] || curl -fsSL --retry 3 -o "$DL/$TARBALL.sig" "$URL/$TARBALL.sig"
[[ -f $DL/release-keys.asc ]] || curl -fsSL --retry 3 -o "$DL/release-keys.asc" "$KEYS_URL"
gnupg=$DL/gnupg
mkdir -p -m 700 "$gnupg"
GNUPGHOME=$gnupg gpg --batch --quiet --dearmor < "$DL/release-keys.asc" > "$DL/release-keys.gpg"
if gpgv --status-fd 1 --keyring "$DL/release-keys.gpg" "$DL/$TARBALL.sig" "$DL/$TARBALL" 2>/dev/null \
    | grep -q "VALIDSIG .* $SIGNER_FPR\$"; then
  log "signature ok ($SIGNER_FPR)"
else
  log "signature check failed"; exit 1
fi

if [[ ! -f $SRC/.extracted-2 ]]; then
  log "extracting the runtimes subtree"
  rm -rf "$SRC"
  p=llvm-project-$LLVM_VERSION.src
  # libc: libc++'s from_chars uses LLVM libc's shared headers.
  tar -C "$DL" -xJf "$DL/$TARBALL" --no-same-owner \
    $p/runtimes $p/cmake $p/libcxx $p/libcxxabi $p/libunwind $p/libc $p/third-party \
    $p/compiler-rt $p/llvm/cmake $p/llvm/utils/lit $p/llvm/utils/llvm-lit
  touch "$SRC/.extracted-2"
fi

install_licenses() {
  local c
  for c in libcxx libcxxabi libunwind compiler-rt; do
    install -D -m 644 "$SRC/$c/LICENSE.TXT" "$PREFIX/share/licenses/$c/LICENSE.TXT"
  done
}
if [[ $LICENSES_ONLY == 1 ]]; then
  [[ -f $PREFIX/lib/libc++.a ]] || { log "no runtimes in $PREFIX; build them first"; exit 1; }
  install_licenses
  log "licence texts installed into $PREFIX/share/licenses"
  exit 0
fi

gcc_dir=$SYSROOT/usr/lib/gcc/$TRIPLE/$GCC_VERSION
# AOSP's runtime builds map the source root to out/llvm-project (visible in
# the reference library's assertion strings); do the same. The build and
# toolchain directories are mapped as well, so the debug info does not depend
# on where the checkout lives (clang applies the last matching map).
cflags="--sysroot=$SYSROOT --gcc-install-dir=$gcc_dir -ffile-prefix-map=$HERE=toolchain"
cflags+=" -ffile-prefix-map=$BUILD=out/runtimes -ffile-prefix-map=$SRC/=out/llvm-project/"
# -nostdlib++: the configure checks must not look for libstdc++ (or the
# libc++ being built), as in llvm_android's runtime builders.
ldflags="-fuse-ld=lld -nostdlib++ --sysroot=$SYSROOT --gcc-install-dir=$gcc_dir"

rm -rf "$BUILD"
mkdir -p "$BUILD"
cmake -S "$SRC/runtimes" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_ASM_COMPILER=clang \
  -DCMAKE_C_COMPILER_TARGET=$TRIPLE -DCMAKE_CXX_COMPILER_TARGET=$TRIPLE -DCMAKE_ASM_COMPILER_TARGET=$TRIPLE \
  -DCMAKE_C_FLAGS="$cflags" -DCMAKE_CXX_FLAGS="$cflags" -DCMAKE_ASM_FLAGS="$cflags" \
  -DCMAKE_EXE_LINKER_FLAGS="$ldflags" -DCMAKE_SHARED_LINKER_FLAGS="$ldflags" \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
  -DLLVM_ENABLE_RUNTIMES="libcxx;libcxxabi;libunwind;compiler-rt" \
  -DLLVM_ENABLE_PER_TARGET_RUNTIME_DIR=OFF \
  -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_DOCS=OFF \
  -DLIBCXX_INCLUDE_TESTS=OFF -DLIBCXX_INCLUDE_BENCHMARKS=OFF \
  -DLIBCXXABI_INCLUDE_TESTS=OFF -DLIBUNWIND_INCLUDE_TESTS=OFF \
  -DLIBCXX_ENABLE_SHARED=OFF -DLIBCXXABI_ENABLE_SHARED=OFF -DLIBUNWIND_ENABLE_SHARED=OFF \
  -DLIBCXXABI_USE_LLVM_UNWINDER=ON \
  -DLIBCXXABI_ENABLE_STATIC_UNWINDER=ON \
  -DLIBCXX_ENABLE_STATIC_ABI_LIBRARY=ON \
  -DLIBCXX_ENABLE_ABI_LINKER_SCRIPT=OFF \
  -DLIBCXX_HAS_ATOMIC_LIB=NO \
  -DLIBCXX_INSTALL_MODULES=OFF \
  -DCOMPILER_RT_DEFAULT_TARGET_ONLY=ON \
  -DCOMPILER_RT_BUILD_BUILTINS=OFF \
  -DCOMPILER_RT_BUILD_SANITIZERS=ON -DCOMPILER_RT_SANITIZERS_TO_BUILD=ubsan_minimal \
  -DCOMPILER_RT_BUILD_XRAY=OFF -DCOMPILER_RT_BUILD_LIBFUZZER=OFF -DCOMPILER_RT_BUILD_PROFILE=OFF \
  -DCOMPILER_RT_BUILD_MEMPROF=OFF -DCOMPILER_RT_BUILD_ORC=OFF -DCOMPILER_RT_BUILD_CTX_PROFILE=OFF \
  -DCOMPILER_RT_BUILD_GWP_ASAN=OFF -DCOMPILER_RT_INCLUDE_TESTS=OFF

log "building with -j$JOBS"
ninja -C "$BUILD" -j"$JOBS" install-cxx install-cxxabi install-unwind install-ubsan-minimal
[[ -f $PREFIX/lib/linux/libclang_rt.ubsan_minimal-$CPU.a ]] || { log "ubsan_minimal not installed"; exit 1; }
install_licenses
# Record what was built, for the toolchain file and the lock.
{
  echo "arch=$ARCH"
  echo "llvm_version=$LLVM_VERSION"
  echo "tarball_sha256=$TARBALL_SHA256"
  echo "clang=$(clang --version | head -1)"
  echo "sysroot=$(sha256sum "$SYSROOT/.ra64-sysroot.json" | cut -d' ' -f1)"
} > "$PREFIX/.ra64-runtimes"
log "installed into $PREFIX"
