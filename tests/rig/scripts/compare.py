#!/usr/bin/env python3
"""Pixel-diffs two rig output directories.

For every PNG in either directory it reports the largest per-channel difference (0-255 over
R, G, B, A, after decoding, so different PNG encoders do not matter), the number of pixels that
differ at all, and the number above the tolerance. For images that differ it writes a diff
image: the reference faded to grey, with differing pixels in red (brighter = larger delta).
Text outputs (*.txt, metrics) are compared line by line. Files starting with "_" are run
metadata and are only printed.

Usage: compare.py REFERENCE CANDIDATE [--diff-dir DIR] [--tolerance N] [--json FILE]
Exit status: 0 if every image is within the tolerance and every text file matches, 1 otherwise.
Needs Pillow (no numpy).
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageChops


def per_pixel_max(diff):
    """Single-band image: max channel delta for each pixel."""
    bands = diff.split()
    m = bands[0]
    for b in bands[1:]:
        m = ImageChops.lighter(m, b)
    return m


def compare_png(ref_path, cand_path, tolerance, diff_path):
    a = Image.open(ref_path).convert("RGBA")
    b = Image.open(cand_path).convert("RGBA")
    if a.size != b.size:
        return {"status": "size", "ref_size": a.size, "cand_size": b.size}
    diff = ImageChops.difference(a, b)
    channel_max = [hi for _, hi in diff.getextrema()]
    pp = per_pixel_max(diff)
    hist = pp.histogram()
    total = a.size[0] * a.size[1]
    differing = total - hist[0]
    over = sum(hist[tolerance + 1:])
    result = {
        "status": "same" if differing == 0 else ("within" if over == 0 else "differs"),
        "size": a.size,
        "max_delta": max(channel_max),
        "max_delta_rgba": channel_max,
        "differing_pixels": differing,
        "over_tolerance": over,
        "differing_percent": round(100.0 * differing / total, 4),
    }
    if differing and diff_path:
        grey = a.convert("L").point(lambda v: 160 + v * 95 // 255).convert("RGB")
        # Any delta is at least 64 bright, so single-step differences are still visible.
        red = pp.point(lambda v: 0 if v == 0 else min(255, 64 + v * 4))
        mask = pp.point(lambda v: 255 if v else 0)
        overlay = Image.merge("RGB", (red, Image.new("L", a.size, 0), Image.new("L", a.size, 0)))
        grey.paste(overlay, (0, 0), mask)
        # Reference | candidate | diff, side by side.
        sheet = Image.new("RGB", (a.size[0] * 3, a.size[1]), "white")
        sheet.paste(a.convert("RGB"), (0, 0))
        sheet.paste(b.convert("RGB"), (a.size[0], 0))
        sheet.paste(grey, (a.size[0] * 2, 0))
        sheet.save(diff_path)
        result["diff_image"] = diff_path
    return result


def compare_text(ref_path, cand_path):
    with open(ref_path, encoding="utf-8") as f:
        ra = f.read().splitlines()
    with open(cand_path, encoding="utf-8") as f:
        rb = f.read().splitlines()
    changed = [i + 1 for i in range(max(len(ra), len(rb)))
               if (ra[i] if i < len(ra) else None) != (rb[i] if i < len(rb) else None)]
    return {"status": "same" if not changed else "differs", "changed_lines": changed}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("candidate")
    ap.add_argument("--diff-dir", help="where to write diff images (default: CANDIDATE/_diff)")
    ap.add_argument("--tolerance", type=int, default=0, help="max channel delta still counted as a match")
    ap.add_argument("--json", help="also write the full report as JSON here")
    args = ap.parse_args()

    diff_dir = args.diff_dir or os.path.join(args.candidate, "_diff")
    os.makedirs(diff_dir, exist_ok=True)

    def listing(d):
        return {n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))}

    ra, rb = listing(args.reference), listing(args.candidate)
    for meta in sorted(n for n in ra | rb if n.startswith("_") and n.endswith(".txt") and n != "_timing.txt"):
        for label, d, names in (("ref ", args.reference, ra), ("cand", args.candidate, rb)):
            if meta in names:
                with open(os.path.join(d, meta), encoding="utf-8") as f:
                    print(f"[{label}] {meta}: " + " | ".join(f.read().split("\n")).strip(" |"))

    report, ok = {}, True
    names = sorted(n for n in ra | rb if not n.startswith("_") and n.endswith((".png", ".txt")))
    print(f"\n{'file':44} {'status':8} {'max':>4} {'diff px':>9} {'>tol':>9} {'%':>8}")
    for n in names:
        if n not in ra or n not in rb:
            r = {"status": "missing in " + ("reference" if n not in ra else "candidate")}
        elif n.endswith(".png"):
            r = compare_png(os.path.join(args.reference, n), os.path.join(args.candidate, n), args.tolerance,
                            os.path.join(diff_dir, n[:-4] + "-diff.png"))
        else:
            r = compare_text(os.path.join(args.reference, n), os.path.join(args.candidate, n))
        report[n] = r
        if r["status"] not in ("same", "within"):
            ok = False
        if "max_delta" in r:
            print(f"{n:44} {r['status']:8} {r['max_delta']:>4} {r['differing_pixels']:>9} {r['over_tolerance']:>9} {r['differing_percent']:>8}")
        elif "changed_lines" in r:
            print(f"{n:44} {r['status']:8} lines changed: {r['changed_lines'][:12]}")
        else:
            print(f"{n:44} {r['status']}")
    pngs = [r for n, r in report.items() if n.endswith(".png") and "max_delta" in r]
    same = sum(1 for r in pngs if r["status"] == "same")
    print(f"\n{same}/{len(pngs)} images identical, worst max delta {max([r['max_delta'] for r in pngs], default=0)}, "
          f"result: {'PASS' if ok else 'FAIL'} (tolerance {args.tolerance})")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, default=list)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
