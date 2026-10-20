#!/usr/bin/env bash
# Runs the fidelity rig in one of three modes and writes the PNGs to out/<mode>/.
#
#   golden-x86      x86_64 JDK 21 under qemu-user, stock Robolectric loader, official
#                   x86_64 libandroid_runtime from android-all. This is the baseline.
#   x86-via-loader  same JVM, but the arm64 loader plugin is on the classpath and forced to
#                   load the official x86_64 library from a file. Proves the injection path
#                   renders exactly like the stock loader. With RIG_X86_LIB it loads that
#                   x86_64 library instead (for example a source build of it).
#   arm64           native aarch64 JDK 21 with the arm64 loader plugin. The library comes
#                   from RIG_ARM64_LIB (a file), from the jar in RIG_LOADER_JAR, or from
#                   RA64_NATIVE_LIB (bundled into the loader project's jar for this run).
#
# Usage: scripts/run.sh <mode> [gradle args, e.g. --tests 'rig.fidelity.CanvasScenesTest']
#
# Environment (all optional):
#   RIG_ARM64_JDK, RIG_X64_JDK  Java 21 homes for the test JVM (default .work/jdk/aarch64 and
#                               .work/jdk/x64 under tests/rig)
#   RIG_ARM64_LIB               arm64 mode: load this libandroid_runtime.so through
#                               -Drobolectric.arm64.nativeLibrary
#   RIG_LOADER_JAR              arm64 mode: put this prebuilt loader jar on the test classpath
#                               instead of the :loader project (tests the release artifact)
#   RA64_NATIVE_LIB             read by the :loader project: bundle this library into its jar
#   RIG_X86_LIB                 x86-via-loader: x86_64 library to load (default: the official
#                               one, unpacked from android-all in the local Maven repository)
#   RIG_M2_REPO                 local Maven repository Robolectric downloads android-all into
#                               (default $HOME/.m2/repository)
#   RIG_OUT_NAME                output directory name under out/ (default: the mode)
#   GRADLE                      Gradle command (default: the repository's gradlew)
#   GRADLE_JAVA_HOME            JDK that runs Gradle itself (default: JAVA_HOME as set)
#   ANDROID_HOME                Android SDK (or ANDROID_SDK_ROOT, or sdk.dir in local.properties)
#   QEMU_LD_PREFIX              x86_64 sysroot for qemu-user; needed on arm64 hosts for aapt2
#                               and for the x86 modes, unless binfmt finds x86_64 libraries itself
#   RIG_LOCK_FILE               take an flock on this file around the Gradle run (default: none)
#   RIG_MIN_MEM_MB              wait until MemAvailable is at least this many MB (default 0: off)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
MODE="${1:-}"; shift || true
X64_JDK="${RIG_X64_JDK:-$ROOT/.work/jdk/x64}"
ARM64_JDK="${RIG_ARM64_JDK:-$ROOT/.work/jdk/aarch64}"
MIN_MEM_MB="${RIG_MIN_MEM_MB:-0}"
M2_REPO="${RIG_M2_REPO:-$HOME/.m2/repository}"
OUT="$ROOT/out/${RIG_OUT_NAME:-$MODE}"
GRADLE="${GRADLE:-$REPO/gradlew}"

[ -n "${GRADLE_JAVA_HOME:-}" ] && export JAVA_HOME="$GRADLE_JAVA_HOME"
[ -z "${ANDROID_HOME:-}" ] && [ -n "${ANDROID_SDK_ROOT:-}" ] && export ANDROID_HOME="$ANDROID_SDK_ROOT"
if [ -z "${ANDROID_HOME:-}" ] && ! grep -qs '^sdk.dir=' "$ROOT/local.properties"; then
  echo "no Android SDK: set ANDROID_HOME (or sdk.dir in tests/rig/local.properties)" >&2; exit 2
fi

# The official x86_64 library, unpacked once from android-all (needed by x86-via-loader).
x86_lib() {
  local dir="$ROOT/.work/x86lib" jar
  if [ ! -f "$dir/libandroid_runtime.so" ]; then
    jar=$(ls "$M2_REPO"/org/robolectric/android-all-instrumented/16-robolectric-13921718-i7/*.jar 2>/dev/null | head -1)
    [ -n "$jar" ] || { echo "android-all 16 not in $M2_REPO yet: run golden-x86 first" >&2; exit 2; }
    mkdir -p "$dir"
    unzip -qo -j "$jar" native/linux/x86_64/libandroid_runtime.so -d "$dir"
  fi
  echo "$dir/libandroid_runtime.so"
}

args=()
case "$MODE" in
  golden-x86)     java="$X64_JDK/bin/java"; args+=(-Prig.stock) ;;
  x86-via-loader) java="$X64_JDK/bin/java"; args+=("-Prig.nativeLib=${RIG_X86_LIB:-$(x86_lib)}") ;;
  arm64)          java="$ARM64_JDK/bin/java"
                  [ -n "${RIG_ARM64_LIB:-}" ] && args+=("-Prig.nativeLib=$RIG_ARM64_LIB")
                  [ -n "${RIG_LOADER_JAR:-}" ] && args+=("-Prig.loaderJar=$(realpath "$RIG_LOADER_JAR")") ;;
  *) echo "usage: scripts/run.sh golden-x86|x86-via-loader|arm64 [gradle args]" >&2; exit 2 ;;
esac
[ -x "$java" ] || { echo "missing Java 21 at $java (set RIG_ARM64_JDK or RIG_X64_JDK)" >&2; exit 2; }

# Optional: on a small machine, do not start while memory is short.
while [ "$MIN_MEM_MB" -gt 0 ]; do
  avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  [ "$avail" -ge "$MIN_MEM_MB" ] && break
  echo ">> MemAvailable ${avail} MB < ${MIN_MEM_MB} MB, waiting"
  sleep 30
done

rm -rf "$OUT"; mkdir -p "$OUT"
# Optional: a lock shared with other builds on the machine, so two Gradle builds never overlap.
if [ -n "${RIG_LOCK_FILE:-}" ]; then
  exec 9>"$RIG_LOCK_FILE"
  flock 9
fi

start=$(date +%s)
"$GRADLE" --no-daemon -p "$ROOT" :app:testDebugUnitTest \
  "-Prig.java=$java" "-Prig.out=$OUT" "${args[@]}" "$@"
status=$?
end=$(date +%s)

results="$ROOT/app/build/test-results/testDebugUnitTest"
mkdir -p "$OUT/_junit"; cp "$results"/*.xml "$OUT/_junit/" 2>/dev/null || true
{
  echo "mode=$MODE"
  echo "java=$java"
  echo "gradle_exit=$status"
  echo "wall_seconds=$((end - start))"
  python3 -I - "$OUT/_junit" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
total = 0.0
for f in sorted(glob.glob(sys.argv[1] + "/*.xml")):
    s = ET.parse(f).getroot()
    t = float(s.get("time", 0)); total += t
    print(f"suite {s.get('name')} tests={s.get('tests')} failures={s.get('failures')} errors={s.get('errors')} seconds={t:.1f}")
    for c in s.findall("testcase"):
        bad = "FAIL" if c.find("failure") is not None or c.find("error") is not None else "ok"
        print(f"  {c.get('name')} {float(c.get('time', 0)):.1f}s {bad}")
print(f"test_seconds_total={total:.1f}")
PY
} > "$OUT/_timing.txt"
cat "$OUT/_timing.txt"
echo ">> $(ls "$OUT"/*.png 2>/dev/null | wc -l) PNGs in $OUT"
exit $status
