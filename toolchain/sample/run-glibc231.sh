#!/bin/bash
# Run a program with the sysroot's own glibc 2.31 loader and libraries, to
# check that a library really loads on Debian 11.
#   toolchain/sample/run-glibc231.sh toolchain/build/sample/sample_main toolchain/build/sample/libsample.so
set -euo pipefail
S=$(cd "$(dirname "$0")/../out/sysroot-bullseye-arm64" && pwd)
exec "$S/lib/aarch64-linux-gnu/ld-2.31.so" \
  --library-path "$S/lib/aarch64-linux-gnu:$S/usr/lib/aarch64-linux-gnu" "$@"
