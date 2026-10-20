#!/usr/bin/env bash
# Build libandroid_runtime.so for Linux arm64 from a clean checkout and write dist/.
#
# Used by .github/workflows/build.yml (jobs "build" and "reproduce"). It runs the same way on any
# Ubuntu 26.04 arm64 machine with the packages from docs/BUILDING.md (or the workflow's PACKAGES)
# installed.
#
#   ci/build.sh [-j N] [--out DIR]
#
# Steps: fetch pinned sources (verified against config/sources.lock.json), install the pinned Rust
# toolchain, build the Debian 11 sysroot and the static C++ runtimes, configure, build, run the
# static checks, strip, generate the third-party notices, write checksums.
# Everything is verified by the scripts it calls (content hashes, SHA-256 pins, signatures); the
# only thing checked here is that the fetch did not change the lock file.
set -euo pipefail

JOBS=$(nproc)
OUT=dist
while [ $# -gt 0 ]; do
  case $1 in
    -j) JOBS=$2; shift 2 ;;
    -j?*) JOBS=${1#-j}; shift ;;
    --out) OUT=$2; shift 2 ;;
    *) echo "usage: $0 [-j N] [--out DIR]" >&2; exit 2 ;;
  esac
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# Settings that keep the output independent of the machine (see docs/reproducibility.md).
export LC_ALL=C.UTF-8 TZ=UTC PYTHONHASHSEED=0
if [ -z "${SOURCE_DATE_EPOCH:-}" ]; then
  if [ -d .git ]; then SOURCE_DATE_EPOCH=$(git log -1 --format=%ct); else SOURCE_DATE_EPOCH=0; fi
  export SOURCE_DATE_EPOCH
fi

BUILD=build/out
LIB=$BUILD/lib/libandroid_runtime.so
VERSION_SCRIPT=src/frameworks/base/core/jni/platform/linux/libandroid_runtime_export.txt

group() { echo "::group::$*"; }
endgroup() { echo "::endgroup::"; }
t0=$(date +%s)
lap() { echo "== $1: $(( $(date +%s) - t0 )) s elapsed, $(df -h --output=avail . | tail -1 | tr -d ' ') free"; }

group "fetch sources"
python3 -I tools/fetch.py
if [ -d .git ]; then
  git diff --exit-code -- config/sources.lock.json \
    || { echo "fetch.py changed config/sources.lock.json: the pin and the lock disagree"; exit 1; }
fi
endgroup; lap fetch

group "toolchains"
rust/install-toolchain.sh
python3 -I toolchain/make-sysroot.py
toolchain/build-runtimes.sh -j"$JOBS"
endgroup; lap toolchains

group "configure"
cmake -S . -B "$BUILD" -G Ninja -DRA64_USE_SYSROOT=ON
endgroup; lap configure

group "build"
ninja -C "$BUILD" -j"$JOBS"
endgroup; lap build

group "checks"
# The link already runs check-so.py; running it again here makes the CI log self-contained.
python3 -I toolchain/check-so.py --floor 2.31 --version-script "$VERSION_SCRIPT" "$LIB"
endgroup

group "dist"
rm -rf "$OUT"; mkdir -p "$OUT"
# Same layout as the official library: stripped, dynamic symbols kept. The unstripped file is kept
# as a separate debug artifact.
llvm-objcopy --only-keep-debug "$LIB" "$OUT/libandroid_runtime.so.debug"
llvm-strip --strip-all -o "$OUT/libandroid_runtime.so" "$LIB"
# The link writes lib/NOTICE (and fails on a linked part without a license entry).
cp "$BUILD/lib/NOTICE" "$OUT/THIRD_PARTY_NOTICES"
cp "$BUILD/notices/libandroid_runtime/notices.json" "$OUT/"
{
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "source_date_epoch=$SOURCE_DATE_EPOCH"
  echo "aosp_tag=$(sed -n 's/^tag *= *"\(.*\)"/\1/p' config/aosp.toml)"
  echo "sources_lock_sha256=$(sha256sum config/sources.lock.json | cut -d' ' -f1)"
  echo "clang=$(clang --version | head -1)"
  echo "lld=$(ld.lld --version | head -1)"
  echo "rustc_staticlib=$(rust/toolchain/bin/rustc --version)"
  echo "cmake=$(cmake --version | head -1)"
  echo "ninja=$(ninja --version)"
  echo "build_id=$(readelf -n "$OUT/libandroid_runtime.so" | sed -n 's/.*Build ID: //p')"
  echo "jobs=$JOBS"
} > "$OUT/build-info.txt"
( cd "$OUT" && sha256sum libandroid_runtime.so libandroid_runtime.so.debug THIRD_PARTY_NOTICES notices.json > SHA256SUMS )
cat "$OUT/build-info.txt" "$OUT/SHA256SUMS"
endgroup; lap done
