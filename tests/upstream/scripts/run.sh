#!/usr/bin/env bash
# Runs Robolectric 4.17's own test suites (harness/) in one mode, at SDK 36 or (SDKS) at SDK 26 to 34.
#   arm64  aarch64 JDK 21, the loader plugin (injected by an init script) and the arm64 library
#   x86    x86_64 JDK 21 (under qemu-user on an arm64 host), the stock loader and the official
#          library from android-all, as the reference
#   none   the harness as is: stock loader on the test JVM, nothing injected
#
# Usage: scripts/run.sh <mode> <name> <gradle tasks and args...>
# Results go to results/<name>/: gradle.log, _run.txt and junit/<module>/*.xml.
#
# Environment (all optional unless noted):
#   ARM64_LIB        library under test (default <repo>/build/out/lib/libandroid_runtime.so, or
#                    <repo>/build/compat/lib/librobolectric-nativeruntime.so when SDKS are all < 35)
#   SDKS             SDK levels to run, comma separated (default 36). Levels 26 to 34 use the
#                    SDK <= 34 library; do not mix them with 35+ in one run
#   LOADER_JAR       loader plugin jar (default: built with ./gradlew :loader:jar at the repo root)
#   JAVA_HOME        JDK 21 that runs Gradle; also the test JVM in arm64 mode unless SUITE_JAVA is set
#   SUITE_JAVA       java executable for the test JVM
#   X86_JAVA         x86_64 JDK 21 java executable (required for mode x86)
#   QEMU_LD_PREFIX   x86_64 sysroot for qemu-user (mode x86), passed through to the test JVM
#   ANDROID_HOME     Android SDK with platforms;android-36 (or sdk.dir in harness/local.properties)
#   GRADLE           Gradle 8.13 command (default: the repository's gradlew, else gradle on PATH)
#   ROBOLECTRIC_REF  tag cloned into src/ when src/ is missing (default robolectric-4.17)
#   BUILD_LOCK       file to hold an flock on for the whole run, to serialise with other builds
#   MIN_MEM_MB       wait until MemAvailable reaches this many MB before starting
set -uo pipefail
W="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$W/../.." && pwd)"
[ $# -ge 2 ] || { echo "usage: $0 arm64|x86|none <name> <gradle args...>" >&2; exit 2; }
MODE="$1"; NAME="$2"; shift 2
OUT="$W/results/$NAME"
REF="${ROBOLECTRIC_REF:-robolectric-4.17}"

if [ -n "${BUILD_LOCK:-}" ]; then
  mkdir -p "$(dirname "$BUILD_LOCK")"
  exec 9>"$BUILD_LOCK"; flock 9
fi

if [ -z "${GRADLE:-}" ]; then
  if [ -x "$REPO/gradlew" ]; then GRADLE="$REPO/gradlew"; else GRADLE=gradle; fi
fi
if [ -z "${SUITE_JAVA:-}" ] && [ -n "${JAVA_HOME:-}" ]; then SUITE_JAVA="$JAVA_HOME/bin/java"; fi

# Upstream test sources: a shallow clone of robolectric at the tag, used unmodified.
if [ ! -d "$W/src/.git" ]; then
  echo ">> cloning robolectric $REF into src/"
  git -c advice.detachedHead=false clone -q --depth 1 --branch "$REF" https://github.com/robolectric/robolectric.git "$W/src" || exit 1
elif [ "$(git -C "$W/src" rev-parse HEAD)" != "$(git -C "$W/src" rev-parse -q --verify "refs/tags/$REF^{commit}")" ]; then
  echo ">> warning: src/ is not at tag $REF" >&2
fi

args=(--no-daemon -p "$W/harness" --max-workers=1 --continue "-Psuite.sdks=${SDKS:-36}")
# SDK levels below 35 use the SDK <= 34 library (librobolectric-nativeruntime.so): ARM64_LIB
# names that file and the loader is told so (robolectric.arm64.nativeLibrarySdk).
compat=1
for s in ${SDKS//,/ }; do [ "$s" -ge 35 ] && compat=0; done
[ -z "${SDKS:-}" ] && compat=0
case "$MODE" in
  arm64)
    if [ "$compat" = 1 ]; then deflib="$REPO/build/compat/lib/librobolectric-nativeruntime.so"
    else deflib="$REPO/build/out/lib/libandroid_runtime.so"; fi
    lib="${ARM64_LIB:-$deflib}"
    [ -f "$lib" ] || { echo "no library at $lib (set ARM64_LIB)" >&2; exit 1; }
    jar="${LOADER_JAR:-}"
    if [ -z "$jar" ]; then
      "$GRADLE" --no-daemon -q -p "$REPO" :loader:jar || exit 1
      jar="$(ls "$REPO"/loader/build/libs/*.jar 2>/dev/null | grep -vE -- '-(sources|javadoc)\.jar$' | head -n 1)"
      [ -n "$jar" ] || { echo "no jar in $REPO/loader/build/libs" >&2; exit 1; }
    fi
    args+=(-I "$W/scripts/arm64.init.gradle.kts"
           "-Parm64.loaderJar=$(cd "$(dirname "$jar")" && pwd)/$(basename "$jar")"
           "-Parm64.nativeLibrary=$(cd "$(dirname "$lib")" && pwd)/$(basename "$lib")")
    [ "$compat" = 1 ] && args+=("-Parm64.nativeLibrarySdk=34")
    [ -n "${SUITE_JAVA:-}" ] && args+=("-Psuite.java=$SUITE_JAVA") ;;
  x86)
    [ -n "${X86_JAVA:-}" ] || { echo "mode x86 needs X86_JAVA (an x86_64 JDK 21 java)" >&2; exit 2; }
    args+=("-Psuite.java=$X86_JAVA") ;;
  none)
    [ -n "${SUITE_JAVA:-}" ] && args+=("-Psuite.java=$SUITE_JAVA") ;;
  *) echo "mode: arm64|x86|none" >&2; exit 2 ;;
esac

if [ -n "${MIN_MEM_MB:-}" ]; then
  while :; do
    avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
    [ "$avail" -ge "$MIN_MEM_MB" ] && break
    echo ">> MemAvailable ${avail} MB, waiting"; sleep 30
  done
fi

rm -rf "$OUT" "$W"/harness/*/build/test-results
mkdir -p "$OUT" "$W/harness/.work/hs_err"; touch "$OUT/.start"
start=$(date +%s)
"$GRADLE" "${args[@]}" "$@" 2>&1 | tee "$OUT/gradle.log"
status=${PIPESTATUS[0]}
end=$(date +%s)
for m in robotests nativegraphics ctesque; do
  for d in "$W/harness/$m/build/test-results"/*; do
    [ -d "$d" ] && mkdir -p "$OUT/junit/$m" && cp "$d"/*.xml "$OUT/junit/$m/" 2>/dev/null
  done
done
find "$W/harness/.work/hs_err" -newer "$OUT/.start" -name "hs_err*" -exec cp {} "$OUT/" \;
echo "mode=$MODE status=$status wall_seconds=$((end-start)) args=$*" > "$OUT/_run.txt"
cat "$OUT/_run.txt"
[ -d "$OUT/junit" ] && python3 -I "$W/scripts/compare.py" "$OUT"
exit $status
