#!/usr/bin/env python3
"""Check that the copyright holders named in linked sources appear in the NOTICE file.

AOSP's licence metadata works per project, so a third-party notice inside one
source file can be missing from a generated NOTICE file. This reads the source of
every archive member the linker took (lld --why-extract), collects its copyright
lines and looks for each holder in the NOTICE file. A holder that is
not found fails the check until someone reads the file and adds its notice, or a
[[note]] naming the holder, to config/notices-extra.toml.

Generated sources, headers and the library's own objects are not scanned.

Usage:
  check_notice_holders.py --src SRC --closure closure.json --module NAME \\
      --archives archives.tsv --why-extract why-extract.tsv --notice NOTICE [--list]

--list prints every holder that was not found, with the files naming it.
"""
import argparse
import json
import os
import re
import sys

COPYRIGHT = re.compile(r"copyright\s*(?:\(c\)|©|&copy;)?\s*:?\s*(.*)", re.I)
YEARS = re.compile(r"^[\s,\-–(c)©]*(?:\d{4}\s*[-–,]?\s*)+")
NOT_A_HOLDER = re.compile(r"^(notice|holder|owner|law|and |the above|the following|for |of |\(c\)|on |in |to |see |by |is |this |"
                          r"laws|statement|protection|license|licence|year|date|<|\[|\{|%|\"|'|\*|\\|$)", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def holder(line):
    """The holder named on a line with a copyright statement, or None."""
    m = COPYRIGHT.search(line)
    if not m:
        return None
    h = YEARS.sub("", m.group(1))
    if not re.search(r"\d{4}", m.group(1)):      # "copyright notice", "the copyright holders", ...
        return None
    h = re.sub(r"<[^>]*>|\([^)]*@[^)]*\)|\*+/|https?://\S+", " ", h).split('"')[0]
    h = re.split(r"\s+all rights reserved|,?\s+part of\b|\s+licensed\b", h, flags=re.I)[0]
    h = h.strip(" \t.,;:*/#-")
    if len(h) < 3 or NOT_A_HOLDER.match(h):
        return None
    return h


def linked_sources(a):
    closure = json.load(open(a.closure))
    arch = {}
    with open(a.archives, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                mod, path = line.rstrip("\n").split("\t")
                arch[os.path.basename(path)] = mod
    members = {}
    with open(a.why_extract, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            m = re.match(r"(.*)\((.*)\)$", parts[1]) if len(parts) > 1 else None
            if m and os.path.basename(m.group(1)) in arch:
                members.setdefault(arch[os.path.basename(m.group(1))], set()).add(m.group(2))
    # closure.json keeps a module's directory, not its source list: find each
    # member's source by name under that directory.
    out = set()
    for mod, objs in members.items():
        m = closure.get(mod)
        if not m:
            continue
        names = {re.sub(r"\.o$", "", o) for o in objs}
        top = os.path.join(a.src, m["dir"])
        for dirpath, _, files in os.walk(top):
            for fn in files:
                if fn in names:
                    out.add(os.path.relpath(os.path.join(dirpath, fn), a.src))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True)
    ap.add_argument("--closure", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--archives", required=True)
    ap.add_argument("--why-extract", required=True)
    ap.add_argument("--notice", required=True)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    notice = norm(open(a.notice, encoding="utf-8", errors="replace").read())

    sources = linked_sources(a)
    missing = {}
    scanned = 0
    for rel in sorted(sources):
        p = os.path.join(a.src, rel)
        if not os.path.isfile(p):
            continue
        scanned += 1
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "opyright" not in line and "OPYRIGHT" not in line:
                    continue
                h = holder(line)
                if not h:
                    continue
                # "A, B and C" counts as found when each name is.
                if all(norm(x) in notice for x in re.split(r",|\band\b", h)):
                    continue
                missing.setdefault(h, []).append(rel)
    print(f"check_notice_holders: {a.module}: {scanned} linked sources, {len(missing)} holders not in the NOTICE file")
    for h in sorted(missing):
        print(f"  {h}: {', '.join(sorted(set(missing[h]))[:3])}")
    if missing and not a.list:
        sys.exit(1)


if __name__ == "__main__":
    main()
