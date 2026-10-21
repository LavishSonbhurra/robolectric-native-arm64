#!/usr/bin/env python3
"""Fail when the arm64 rig output is further from the x86_64 goldens than the baseline.

The arm64 library cannot match the x86_64 goldens bit for bit (Skia takes NEON paths
on arm64). What must not happen is that an image gets worse, or that an image that is
identical today starts to differ. The ceilings live in tests/rig/baseline/arm64.json.
A baseline may also list text outputs with the line numbers allowed to differ ("texts");
any other text difference fails.

Usage: check-baseline.py REPORT.json [--baseline tests/rig/baseline/arm64.json] [--update]
REPORT.json is the output of tests/rig/scripts/compare.py --json.
Exit status 1 on any violation. Standard library only; run with python3 -I.
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--baseline", default="tests/rig/baseline/arm64.json")
    ap.add_argument("--update", action="store_true", help="rewrite the baseline from this report")
    a = ap.parse_args()
    report = json.load(open(a.report))
    images = {k: v for k, v in report.items() if k.endswith(".png")}
    if a.update:
        base = {k: {"max_delta": v["max_delta"], "differing_pixels": v["differing_pixels"]}
                for k, v in sorted(images.items()) if "max_delta" in v}
        texts = {k: {"changed_lines": v.get("changed_lines", [])}
                 for k, v in sorted(report.items()) if k.endswith(".txt") and v.get("status") != "same"}
        old = json.load(open(a.baseline)) if a.baseline else {}
        out = {"_comment": old.get("_comment", ""), "images": base}
        if texts:
            out["texts"] = texts
        json.dump(out, open(a.baseline, "w"), indent=1)
        print(f"wrote {a.baseline}: {len(base)} images, {len(texts)} differing text files")
        return
    baseline = json.load(open(a.baseline))
    base = baseline["images"]
    allowed_text = baseline.get("texts", {})
    bad = []
    for name, ceil in sorted(base.items()):
        r = images.get(name)
        if r is None or "max_delta" not in r:
            bad.append(f"{name}: missing or size mismatch ({r and r.get('status')})")
            continue
        if r["max_delta"] > ceil["max_delta"]:
            bad.append(f"{name}: max delta {r['max_delta']} > {ceil['max_delta']}")
        if r["differing_pixels"] > ceil["differing_pixels"]:
            bad.append(f"{name}: {r['differing_pixels']} differing pixels > {ceil['differing_pixels']}")
    for name in sorted(set(images) - set(base)):
        bad.append(f"{name}: not in the baseline (new scene? run with --update)")
    for name, r in sorted(report.items()):
        if name.endswith(".txt") and r.get("status") != "same":
            lines = r.get("changed_lines", [])
            if name in allowed_text and set(lines) <= set(allowed_text[name]["changed_lines"]):
                continue
            bad.append(f"{name}: text output differs at lines {r.get('changed_lines', [])[:10]}")
    for b in bad:
        print("FAIL", b)
    print(f"{len(base)} images checked, {len(bad)} violations")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
