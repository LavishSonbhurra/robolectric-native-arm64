#!/usr/bin/env python3
"""Summarise one results/<run>/junit tree, or compare the per-test outcomes of two.

usage: compare.py RUN
       compare.py A_RUN B_RUN [--only-common]
With one run, prints per-module counts and the failing tests. With two, prints per-module
counts for each run and every test whose outcome differs.
"""
import glob, os, sys, xml.etree.ElementTree as ET

def load(run):
    out = {}
    for f in glob.glob(os.path.join(run, "junit", "*", "*.xml")):
        mod = os.path.basename(os.path.dirname(f))
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as e:
            print(f"!! cannot parse {f}: {e}", file=sys.stderr); continue
        for c in root.iter("testcase"):
            key = (mod, c.get("classname"), c.get("name"))
            if c.find("failure") is not None: st = "FAIL"
            elif c.find("error") is not None: st = "ERROR"
            elif c.find("skipped") is not None: st = "SKIP"
            else: st = "PASS"
            msg = ""
            for t in ("failure", "error"):
                e = c.find(t)
                if e is not None:
                    msg = (e.get("message") or e.text or "").strip().splitlines()[0][:200] if (e.get("message") or e.text) else ""
            out[key] = (st, float(c.get("time") or 0), msg)
    return out

def counts(d, keys=None):
    res = {}
    for k, (st, t, _) in d.items():
        if keys is not None and k not in keys: continue
        m = res.setdefault(k[0], {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0, "time": 0.0})
        m[st] += 1; m["time"] += t
    return res

runs = [x for x in sys.argv[1:] if not x.startswith("--")]
if len(runs) == 1:
    A = load(runs[0])
    print(f"== {runs[0]}")
    for mod, m in sorted(counts(A).items()):
        print(f"  {mod:15s} pass={m['PASS']:5d} fail={m['FAIL']:4d} error={m['ERROR']:4d} skip={m['SKIP']:4d} test_time={m['time']:8.1f}s")
    for k, (st, _, msg) in sorted(A.items()):
        if st in ("FAIL", "ERROR"):
            print(f"  {st} {k[0]} {k[1]}.{k[2]}  {msg}")
    sys.exit(0)
if len(runs) != 2:
    sys.exit(__doc__)
a, b = runs
A, B = load(a), load(b)
only_common = "--only-common" in sys.argv
keys = set(A) & set(B) if only_common else None
for name, d in ((a, A), (b, B)):
    print(f"== {name}" + (" (tests present in both runs)" if only_common else ""))
    for mod, m in sorted(counts(d, keys).items()):
        print(f"  {mod:15s} pass={m['PASS']:5d} fail={m['FAIL']:4d} error={m['ERROR']:4d} skip={m['SKIP']:4d} test_time={m['time']:8.1f}s")
print("== outcome differences (A -> B)")
n = 0
for k in sorted(set(A) | set(B)):
    sa = A.get(k, ("MISSING", 0, ""))[0]; sb = B.get(k, ("MISSING", 0, ""))[0]
    if sa != sb and not (only_common and "MISSING" in (sa, sb)):
        n += 1
        msg = B.get(k, ("", 0, ""))[2] if sb in ("FAIL", "ERROR") else A.get(k, ("", 0, ""))[2]
        print(f"  {k[0]} {k[1]}.{k[2]}: {sa} -> {sb}  {msg}")
print(f"  {n} differences")
