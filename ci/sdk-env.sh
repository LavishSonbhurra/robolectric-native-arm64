#!/usr/bin/env bash
# Prints what differs between the libandroid_runtime targets, as KEY=value lines. The workflows append
# it to $GITHUB_ENV; ci/build.sh sources it.
#
#   ci/sdk-env.sh 35|36|37
#
# MIN_TESTS is a little below the tests that ran, not skipped, through the published artifacts on
# 2026-11-02: 8,987 at SDK 35, 9,074 at SDK 36 and 8,984 at SDK 37.
set -euo pipefail

SDK=${1:?usage: ci/sdk-env.sh 35|36|37}
case $SDK in
  35)
    ANDROID_ALL_VERSION=15-robolectric-13954326-i7
    ANDROID_ALL_SHA256=06c4c8602d6db7486266a982bc55834ed6dfebd62a0b88daca204139ecf142cb
    TARGET=sdk35 BUILD_DIR=build/sdk35 SRC_DIR=src-sdk35 CONFIG_DIR=config/sdk35
    RUST_VERSION=1.78.0 RUST_DIR=rust/toolchain-1.78.0
    RIG_GOLDENS=x86_64-sdk35 RIG_BASELINE=arm64-sdk35.json
    EXPECTED_FAILURES=ci/upstream-expected-failures-sdk35.txt
    EXPECTED_JNI=ci/expected-jni-compare-sdk35.txt
    MIN_TESTS=8950 ESPRESSO=
    ;;
  36)
    ANDROID_ALL_VERSION=16-robolectric-13921718-i7
    ANDROID_ALL_SHA256=16f1f751643d1d3d5592008846bbdfc1e57cff15e6ec303d26584de3b6ac25ec
    TARGET=sdk36 BUILD_DIR=build/out SRC_DIR=src CONFIG_DIR=config
    RUST_VERSION=1.83.0 RUST_DIR=rust/toolchain
    RIG_GOLDENS=x86_64 RIG_BASELINE=arm64.json
    EXPECTED_FAILURES=ci/upstream-expected-failures.txt
    EXPECTED_JNI=ci/expected-jni-compare.txt
    MIN_TESTS=9050 ESPRESSO=
    ;;
  37)
    ANDROID_ALL_VERSION=17-robolectric-15733970-i7
    ANDROID_ALL_SHA256=30a15243ba9a6a016361876facc75432f4ec5db0f9e27d4984a4a6b167b432bd
    TARGET=sdk37 BUILD_DIR=build/sdk37 SRC_DIR=src-sdk37 CONFIG_DIR=config/sdk37
    RUST_VERSION=1.93.1 RUST_DIR=rust/toolchain-1.93.1
    RIG_GOLDENS=x86_64-sdk37 RIG_BASELINE=arm64-sdk37.json
    EXPECTED_FAILURES=ci/upstream-expected-failures-sdk37.txt
    EXPECTED_JNI=ci/expected-jni-compare-sdk37.txt
    # Espresso 3.7.0 calls InputManager.getInstance(), which SDK 37 removed.
    MIN_TESTS=8950 ESPRESSO=3.8.0-alpha03
    ;;
  *) echo "no libandroid_runtime target for SDK $SDK" >&2; exit 2 ;;
esac

for key in ANDROID_ALL_VERSION ANDROID_ALL_SHA256 TARGET BUILD_DIR SRC_DIR CONFIG_DIR RUST_VERSION \
           RUST_DIR RIG_GOLDENS RIG_BASELINE EXPECTED_FAILURES EXPECTED_JNI MIN_TESTS ESPRESSO; do
  echo "$key=${!key}"
done
