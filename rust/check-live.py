#!/usr/bin/env python3
"""Compare the Rust code present in two builds of libandroid_runtime.so (or
any binary that links librustlibs.a), by the strings Rust leaves behind.

Rust code that can panic carries a core::panic::Location with the source
file name, so the set of `.rs` paths in .rodata tells which crates (and
which files of them) are live after the link. Soong compiles from the
source root, so first-party and vendored crates appear as
`external/...`, `frameworks/...`, `system/...`; the standard library as
`/rustc/<commit>/library/...` (or short `std/src/...`) and its vendored
dependencies as `/rust/deps/<crate>-<version>/...`.

Usage:
  rust/check-live.py --ref REF.so --ours OURS.so [--markers]

Exits 1 if a non-std source file live in REF is missing from OURS. The
standard library is reported but not enforced: some of its files are
architecture specific (x86_64 reference, aarch64 here).
"""

import argparse
import re
import sys

# Rust strings are not NUL terminated, so file names often run into the
# preceding string ("...logger.rsexternal/rust/..."): the AOSP prefixes are
# matched anywhere, the short std ones at a word start or right after ".rs".
PATH_RE = re.compile(rb"(?:/rustc/[0-9a-f]{40}/library/|/rust/deps/|"
                     rb"(?:external|frameworks|system|packages)/rust|frameworks/minikin/rust/|"
                     rb"(?:(?<![A-Za-z0-9_./-])|(?<=\.rs))(?:std|core|alloc)/)[A-Za-z0-9_./-]+?\.rs")
COMMIT_RE = re.compile(rb"/rustc/([0-9a-f]{40})/")

# Strings without a file name that identify live code of a crate (seen in
# the reference library).
MARKERS = {
    "minikin": [b"Minikin", b"minikin::ffi::load_hyphenator", b"minikin::ffi::hyphenate"],
    "cxx": [b"panic in ffi function"],
    "env_logger": [b"RUST_LOG_STYLE", b"Builder::init should not be called after logger initialized"],
    "log": [b"SetLoggerError"],
}


def crate_of(path):
    p = path.decode()
    if p.startswith("/rustc/") or p.startswith(("std/", "core/", "alloc/")):
        return "std (" + (p.split("/library/", 1)[-1].split("/", 1)[0] if "/library/" in p else p.split("/")[0]) + ")"
    if p.startswith("/rust/deps/"):
        return "std dep " + p.split("/")[3]
    if p.startswith("external/rust/android-crates-io/crates/"):
        return p.split("/")[4]
    if p.startswith("external/rust/cxx/"):
        return "cxx"
    if p.startswith("frameworks/minikin/rust/"):
        return "minikin"
    if p.startswith("system/logging/rust/"):
        return "logger"
    return "other: " + "/".join(p.split("/")[:3])


def scan(path):
    with open(path, "rb") as f:
        data = f.read()
    paths = set(PATH_RE.findall(data))
    commits = set(COMMIT_RE.findall(data))
    return data, paths, commits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ours", required=True)
    args = ap.parse_args()

    rdata, rpaths, rcommits = scan(args.ref)
    odata, opaths, ocommits = scan(args.ours)
    print(f"rustc commit: ref {sorted(c.decode() for c in rcommits)}, ours {sorted(c.decode() for c in ocommits)}")
    if rcommits != ocommits:
        print("  MISMATCH: different Rust standard library")

    def norm(p):
        # std paths: compare without the /rustc/<commit>/library/ prefix.
        return re.sub(rb"^/rustc/[0-9a-f]{40}/library/", b"", p)

    rby, oby = {}, {}
    for p in rpaths:
        rby.setdefault(crate_of(p), set()).add(norm(p))
    for p in opaths:
        oby.setdefault(crate_of(p), set()).add(norm(p))

    failed = False
    print(f"\n{'crate':32} {'ref':>4} {'ours':>4}  missing from ours")
    for crate in sorted(set(rby) | set(oby)):
        r, o = rby.get(crate, set()), oby.get(crate, set())
        missing = sorted(x.decode() for x in r - o)
        enforce = not crate.startswith("std")
        tag = ""
        if missing and enforce:
            failed = True
            tag = "FAIL "
        print(f"{crate:32} {len(r):4} {len(o):4}  {tag}{', '.join(missing)}")
        extra = sorted(x.decode() for x in o - r)
        if extra and enforce:
            print(f"{'':32} {'':4} {'':4}  only in ours: {', '.join(extra)}")

    print("\nmarker strings (crate: present in ref / ours)")
    for crate, ms in MARKERS.items():
        for m in ms:
            inr, ino = m in rdata, m in odata
            if inr and not ino:
                failed = True
            print(f"  {crate:12} {m.decode()!r:70} {'yes' if inr else 'no ':3} / {'yes' if ino else 'no'}"
                  f"{'  FAIL' if inr and not ino else ''}")
    print("\nresult:", "FAIL" if failed else "OK: every non-std Rust source file and marker live in the reference is present")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
