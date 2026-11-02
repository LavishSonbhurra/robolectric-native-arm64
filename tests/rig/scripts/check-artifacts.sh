#!/usr/bin/env bash
# Judges one rig run made with RIG_ARTIFACT_REPO: at least the expected number of tests in the JUnit
# XML (a run that stopped early has no failures either), the library came out of the right jar, and
# the images stay within the baseline for that SDK level.
#
# Usage: scripts/check-artifacts.sh <sdk> <output directory> [expected tests]
# PYTHON names an interpreter with Pillow (default python3).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
SDK=$1 OUT=$2 EXPECTED=${3:-33}
PYTHON=${PYTHON:-python3}

case $SDK in
  36)    golden=x86_64;         baseline=arm64.json;                  jar=sdk36 ;;
  35|37) golden=x86_64-sdk$SDK; baseline=arm64-sdk$SDK.json;          jar=sdk$SDK ;;
  *)     golden=x86_64-sdk$SDK; baseline=arm64-compat-native-sdk$SDK.json; jar=compat ;;
esac
case $jar in
  compat) resource=native/linux/aarch64/librobolectric-nativeruntime.so ;;
  *)      resource=native/linux/aarch64/$jar/libandroid_runtime.so ;;
esac

python3 -I - "$OUT/_junit" "$EXPECTED" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
tests = failed = skipped = 0
for f in glob.glob(sys.argv[1] + "/*.xml"):
    s = ET.parse(f).getroot()
    tests += int(s.get("tests"))
    failed += int(s.get("failures")) + int(s.get("errors"))
    skipped += int(s.get("skipped"))
print(f"junit: {tests} tests, {failed} failed, {skipped} skipped")
sys.exit(1 if failed or tests - skipped < int(sys.argv[2]) else 0)
PY

grep -q 'loader=robolectricarm64.LinuxArm64NativeRuntimeLoader' "$OUT/_loader.txt"
grep "^loadedFrom=" "$OUT/_loader.txt"
grep -q "^loadedFrom=classpath resource jar:file:.*/robolectric-nativeruntime-$jar-linux-aarch64-[^/]*\.jar!/$resource via " "$OUT/_loader.txt" \
  || { echo "the library did not come from the $jar jar" >&2; exit 1; }

"$PYTHON" "$ROOT/scripts/compare.py" "$ROOT/goldens/$golden" "$OUT" --diff-dir "$OUT/_diff" --json "$OUT/_report.json" > "$OUT/_compare.txt" || true
tail -3 "$OUT/_compare.txt"
python3 -I "$REPO/ci/check-baseline.py" "$OUT/_report.json" --baseline "$ROOT/baseline/$baseline"
