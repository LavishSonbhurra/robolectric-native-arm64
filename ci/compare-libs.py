#!/usr/bin/env python3
"""Compare two builds of a shared library byte for byte.

Usage: compare-libs.py FIRST.so SECOND.so

Exit status:
  0  the files are identical
  3  the files differ only inside the .note.gnu.build-id section
  1  anything else (different size, or a difference outside the build-id)

Status 3 is a diagnosis: the build-id is a hash over the unstripped output including its
debug info, so a path that leaks into the debug info changes only the 20 build-id bytes of
the stripped file. The build maps the checkout and build directories out of the debug info
(see docs/reproducibility.md), so CI treats status 3 as a failure. Standard library only;
run with python3 -I.
"""
import struct
import sys


def build_id_range(d):
    if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
        raise SystemExit("not a little-endian ELF64 file")
    shoff = struct.unpack_from("<Q", d, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x3A)
    secs = [struct.unpack_from("<IIQQQQIIQQ", d, shoff + i * shentsize) for i in range(shnum)]
    stroff = secs[shstrndx][4]
    for nm, _ty, _fl, _addr, off, size, *_ in secs:
        end = d.index(b"\0", stroff + nm)
        if d[stroff + nm:end] == b".note.gnu.build-id":
            return off, off + size
    return None


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()
    if a == b:
        print("identical")
        return 0
    if len(a) != len(b):
        print(f"different sizes: {len(a)} and {len(b)} bytes")
        return 1
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    ra, rb = build_id_range(a), build_id_range(b)
    if ra and ra == rb and all(ra[0] <= i < ra[1] for i in diffs):
        print(f"identical except the build-id ({len(diffs)} bytes at offset {ra[0]:#x})")
        return 3
    print(f"{len(diffs)} differing bytes, first at offset {diffs[0]:#x}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
