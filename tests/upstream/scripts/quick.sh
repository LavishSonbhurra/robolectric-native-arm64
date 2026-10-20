#!/usr/bin/env bash
# Short arm64 run: the ctesque suite (about 430 tests) unless other Gradle arguments are given,
# then the summary and the library the probe test found mapped in the test JVM.
# Same environment variables as run.sh (ARM64_LIB, LOADER_JAR, JAVA_HOME, ANDROID_HOME, ...).
#
# Usage: scripts/quick.sh [name] [gradle tasks and args...]
#   scripts/quick.sh
#   scripts/quick.sh bitmap :nativegraphics:testDebugUnitTest --tests '*ShadowNativeBitmapTest'
set -uo pipefail
W="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${1:-quick}"; [ $# -gt 0 ] && shift
[ $# -gt 0 ] || set -- :ctesque:testDebugUnitTest
"$W/scripts/run.sh" arm64 "$NAME" "$@" > /dev/null
status=$?
cat "$W/results/$NAME/_run.txt" 2>/dev/null
[ -d "$W/results/$NAME/junit" ] && python3 -I "$W/scripts/compare.py" "$W/results/$NAME"
grep -rhoE 'PROBE [^<]*' "$W/results/$NAME/junit" 2>/dev/null | sort -u
exit $status
