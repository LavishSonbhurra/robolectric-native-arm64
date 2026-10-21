#!/usr/bin/env bash
# Build librobolectric-nativeruntime.so (the SDK <= 34 library, android12-hostruntime-dev) for
# Linux arm64 from a clean checkout and write dist-compat/. Next to ci/build.sh (which builds
# the SDK 36 library); used by .github/workflows/build-compat.yml. --pixels x86 builds the
# x86 pixel mode (docs/COMPAT.md), published as the -x86pixels artifact; native is the default
# artifact. Each mode has its own build directory (build/compat, build/compat-x86).
#
#   ci/build-compat.sh [-j N] [--out DIR] [--pixels native|x86]
#
# Same steps as ci/build.sh with RA64_TARGET=compat: fetch the pinned sources (verified against
# config/compat/sources.lock.json), build the Debian 11 sysroot and the UBSan runtime, configure,
# build, check, strip, notices, checksums. No Rust toolchain: the compat closure has no Rust.
#
# Strip policy: like the official library, keep .symtab and drop the debug info (it goes to
# librobolectric-nativeruntime.so.debug, linked by .gnu_debuglink, as the official file is).
set -euo pipefail

JOBS=$(nproc)
OUT=dist-compat
PIXELS=native
while [ $# -gt 0 ]; do
  case $1 in
    -j) JOBS=$2; shift 2 ;;
    -j?*) JOBS=${1#-j}; shift ;;
    --out) OUT=$2; shift 2 ;;
    --pixels) PIXELS=$2; shift 2 ;;
    *) echo "usage: $0 [-j N] [--out DIR] [--pixels native|x86]" >&2; exit 2 ;;
  esac
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
export RA64_TARGET=compat
export LC_ALL=C.UTF-8 TZ=UTC PYTHONHASHSEED=0
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
  if [ -d .git ]; then SOURCE_DATE_EPOCH=$(git log -1 --format=%ct); else SOURCE_DATE_EPOCH=0; fi
  export SOURCE_DATE_EPOCH
fi

BUILD=build/compat
[ "$PIXELS" = x86 ] && BUILD=build/compat-x86
case $PIXELS in native|x86) ;; *) echo "--pixels must be native or x86" >&2; exit 2 ;; esac
NAME=librobolectric-nativeruntime.so
LIB=$BUILD/lib/$NAME

group() { echo "::group::$*"; }
endgroup() { echo "::endgroup::"; }
t0=$(date +%s)
lap() { echo "== $1: $(( $(date +%s) - t0 )) s elapsed, $(df -h --output=avail . | tail -1 | tr -d ' ') free"; }

group "fetch sources"
python3 -I tools/fetch.py
if [ -d .git ]; then
  git diff --exit-code -- config/compat/sources.lock.json \
    || { echo "fetch.py changed config/compat/sources.lock.json: the pin and the lock disagree"; exit 1; }
fi
endgroup; lap fetch

group "toolchains"
python3 -I toolchain/make-sysroot.py
toolchain/build-runtimes.sh -j"$JOBS"
endgroup; lap toolchains

group "configure"
cmake -S . -B "$BUILD" -G Ninja -DRA64_TARGET=compat -DRA64_USE_SYSROOT=ON -DRA64_PIXELS="$PIXELS"
endgroup; lap configure

group "build"
ninja -C "$BUILD" -j"$JOBS" m_librobolectric-nativeruntime
endgroup; lap build

group "checks"
# No version script: the official library exports everything (13,610 symbols). The floor is the
# sysroot's glibc; the official library needs GLIBC_2.14 at most, ours 2.29.
python3 -I toolchain/check-so.py --floor 2.31 "$LIB"
endgroup

group "dist"
rm -rf "$OUT"; mkdir -p "$OUT"
llvm-objcopy --only-keep-debug "$LIB" "$OUT/$NAME.debug"
llvm-strip --strip-debug -o "$OUT/$NAME" "$LIB"
llvm-objcopy --add-gnu-debuglink="$OUT/$NAME.debug" "$OUT/$NAME"
cp "$BUILD/lib/NOTICE" "$OUT/THIRD_PARTY_NOTICES"
cp "$BUILD/notices/librobolectric-nativeruntime/notices.json" "$OUT/"
{
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "target=compat"
  echo "pixels=$PIXELS"
  echo "source_date_epoch=$SOURCE_DATE_EPOCH"
  echo "aosp_manifest=$(sed -n 's/^manifest *= *"\(.*\)"/\1/p' config/compat/aosp.toml)"
  echo "aosp_superproject=$(sed -n 's/^superproject *= *"\(.*\)"/\1/p' config/compat/aosp.toml)"
  echo "sources_lock_sha256=$(sha256sum config/compat/sources.lock.json | cut -d' ' -f1)"
  echo "clang=$(clang --version | head -1)"
  echo "lld=$(ld.lld --version | head -1)"
  echo "cmake=$(cmake --version | head -1)"
  echo "ninja=$(ninja --version)"
  echo "build_id=$(readelf -n "$OUT/$NAME" | sed -n 's/.*Build ID: //p')"
  echo "jobs=$JOBS"
} > "$OUT/build-info.txt"
( cd "$OUT" && sha256sum "$NAME" "$NAME.debug" THIRD_PARTY_NOTICES notices.json > SHA256SUMS )
cat "$OUT/build-info.txt" "$OUT/SHA256SUMS"
endgroup; lap done
