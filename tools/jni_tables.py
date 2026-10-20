#!/usr/bin/env python3
"""Extract and compare JNINativeMethod tables of libandroid_runtime builds.

A JNINativeMethod is {const char *name, const char *signature, void *fn}.
In a PIC shared library every such table is an array of pointers that the
dynamic linker relocates, so each entry shows up as three consecutive
R_*_RELATIVE relocations whose addends point at a Java identifier, a JNI
signature and code. This works the same for x86_64 (R_X86_64_RELATIVE) and
aarch64 (R_AARCH64_RELATIVE), so tables of the official x86_64 library and
of our arm64 build can be compared directly.

Usage:
  jni_tables.py dump LIB.so                 one line per method: table, name, sig, symbol
  jni_tables.py compare REF.so OURS.so      exit 0 if the tables match exactly
  jni_tables.py dynsym REF.so OURS.so       compare exported (defined) dynamic symbols

Tables are compared as a multiset of tables, each an ordered tuple of
(name, signature) pairs: registration order and grouping must match too.
Only the Python standard library is used; run with python3 -I.
"""

import collections
import re
import struct
import sys

RELATIVE = {62: 8, 183: 1027}  # e_machine -> R_*_RELATIVE
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
SIG = re.compile(r"^\([\[\]A-Za-z0-9_/;$]*\)[\[A-Za-z0-9_/;$]+$")


class Elf:
    def __init__(self, path):
        self.d = d = open(path, "rb").read()
        if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
            raise SystemExit(f"{path}: not a little-endian ELF64 file")
        self.machine = struct.unpack_from("<H", d, 0x12)[0]
        if self.machine not in RELATIVE:
            raise SystemExit(f"{path}: unsupported e_machine {self.machine}")
        shoff = struct.unpack_from("<Q", d, 0x28)[0]
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x3A)
        self.secs = []
        for i in range(shnum):
            nm, ty, fl, addr, off, size, link, info, al, es = struct.unpack_from(
                "<IIQQQQIIQQ", d, shoff + i * shentsize)
            self.secs.append(dict(nm=nm, ty=ty, fl=fl, addr=addr, off=off, size=size, link=link, es=es))
        stro = self.secs[shstrndx]["off"]
        for s in self.secs:
            s["name"] = self._str(stro + s["nm"])
        self.by_name = {s["name"]: s for s in self.secs}

    def _str(self, o):
        e = self.d.index(b"\0", o)
        return self.d[o:e].decode("latin-1")

    def v2o(self, a):
        for s in self.secs:
            if s["addr"] and s["ty"] != 8 and s["addr"] <= a < s["addr"] + s["size"]:
                return s["off"] + a - s["addr"]
        return None

    def cstr(self, a):
        o = self.v2o(a)
        if o is None:
            return None
        e = self.d.find(b"\0", o)
        try:
            return self.d[o:e].decode("ascii")
        except UnicodeDecodeError:
            return None

    def relative_relocs(self):
        rtype = RELATIVE[self.machine]
        out = {}
        for s in self.secs:
            if s["ty"] != 4:  # SHT_RELA
                continue
            for i in range(s["size"] // 24):
                off, info, add = struct.unpack_from("<QQq", self.d, s["off"] + i * 24)
                if info & 0xFFFFFFFF == rtype:
                    out[off] = add
        return out

    def symbols(self, table=".symtab"):
        s = self.by_name.get(table)
        if not s:
            return []
        strtab = self.secs[s["link"]]["off"]
        out = []
        for i in range(s["size"] // 24):
            nm, info, other, shndx, value, size = struct.unpack_from("<IBBHQQ", self.d, s["off"] + i * 24)
            out.append((self._str(strtab + nm), info, other, shndx, value, size))
        return out


def tables(elf):
    """Runs of entries. Adjacent arrays are split where a symbol starts
    (arm64 builds keep .symtab; the stripped reference has gaps instead)."""
    # Object symbols, and aarch64 `$d` mapping symbols (one per input
    # section, so unnamed arrays in different files still split).
    starts = {v for n, info, other, shndx, v, sz in elf.symbols()
              if v and n and ((info & 0xF) == 1 or n == "$d")}
    ptr = elf.relative_relocs()
    locs = sorted(ptr)
    have = set(ptr)
    seen = set()
    out = []
    for loc in locs:
        if loc in seen:
            continue
        cur = loc
        rows = []
        while cur in have and cur + 8 in have and cur + 16 in have:
            n = elf.cstr(ptr[cur])
            s = elf.cstr(ptr[cur + 8])
            if n is None or s is None or not IDENT.match(n) or not SIG.match(s):
                break
            rows.append((n, s, ptr[cur + 16]))
            cur += 24
            if cur in starts:
                break
        if rows:
            for k in range(len(rows) * 3):
                seen.add(loc + 8 * k)
            out.append((loc, rows))
    return out


def symbolizer(elf):
    """address -> name of the symbol covering it (local symbols included)."""
    syms = sorted((v, sz, n) for n, info, other, shndx, v, sz in elf.symbols() if v and n)
    starts = [x[0] for x in syms]
    import bisect

    def f(a):
        i = bisect.bisect_right(starts, a) - 1
        if i >= 0 and syms[i][0] <= a < syms[i][0] + max(syms[i][1], 1):
            return syms[i][2]
        return "?"
    return f


def cmd_dump(path):
    elf = Elf(path)
    sym = symbolizer(elf)
    for loc, rows in tables(elf):
        for n, s, fn in rows:
            print(f"{sym(loc)}\t{n}\t{s}\t{sym(fn)}")


def table_set(path):
    elf = Elf(path)
    ts = tables(elf)
    sym = symbolizer(elf)
    return collections.Counter(tuple((n, s) for n, s, _ in rows) for _, rows in ts), ts, sym


def partition(run, pool):
    """Split `run` (a reference run of entries) into tables from `pool`
    (Counter of tables), consuming them. Returns the list or None."""
    if not run:
        return []
    for t in sorted(pool, key=len, reverse=True):
        if pool[t] and tuple(run[:len(t)]) == t:
            pool[t] -= 1
            rest = partition(run[len(t):], pool)
            if rest is not None:
                return [t] + rest
            pool[t] += 1
    return None


def cmd_compare(ref, ours):
    """The stripped reference has no symbols, so where two arrays are
    adjacent in memory they read as one run. Ours keeps .symtab, so its
    tables are exact. The libraries match when every reference run is a
    concatenation of our tables and every one of our tables is used exactly
    once: same tables, same entries, same order within each table."""
    a, ta, _ = table_set(ref)
    b, tb, symb = table_set(ours)
    ma = sum(len(t) * c for t, c in a.items())
    mb = sum(len(t) * c for t, c in b.items())
    print(f"reference: {sum(a.values())} runs, {ma} methods")
    print(f"ours:      {sum(b.values())} tables, {mb} methods")
    ra = collections.Counter(r for t, c in a.items() for r in t for _ in range(c))
    rb = collections.Counter(r for t, c in b.items() for r in t for _ in range(c))
    ok = True
    for name, d in (("method only in reference", ra - rb), ("method only in ours", rb - ra)):
        for (n, s), c in sorted(d.items()):
            print(f"{name}: {n} {s} x{c}")
            ok = False
    pool = collections.Counter(b)
    names = {tuple((n, s) for n, s, _ in rows): symb(loc) for loc, rows in tb}
    for t, c in sorted(a.items()):
        for _ in range(c):
            parts = partition(list(t), pool)
            if parts is None:
                ok = False
                # Same entries in another order? Find our tables that cover it as sets.
                print(f"reference run not made of our tables: {len(t)} methods, first {t[0][0]}{t[0][1]}")
                for i, (n, sg) in enumerate(t):
                    print(f"    ref[{i}] {n}{sg}")
    for t, c in sorted(pool.items()):
        if c:
            ok = False
            print(f"our table not in the reference (x{c}): {names.get(t, '?')}, {len(t)} methods")
            for i, (n, sg) in enumerate(t):
                print(f"    ours[{i}] {n}{sg}")
    if ok:
        print("JNI tables: identical (same tables, same methods, same order within each table)")
        return 0
    return 1


def dynsyms(path):
    elf = Elf(path)
    out = set()
    for n, info, other, shndx, v, sz in elf.symbols(".dynsym"):
        if n and shndx != 0 and (info >> 4) in (1, 2):  # GLOBAL/WEAK, defined
            out.add(n)
    return out


def normalize(sym):
    # va_list mangles as P13__va_list_tag on x86_64 and St9__va_list on aarch64.
    return sym.replace("P13__va_list_tag", "St9__va_list")


def cmd_dynsym(ref, ours):
    a = {normalize(s) for s in dynsyms(ref)}
    b = {normalize(s) for s in dynsyms(ours)}
    print(f"reference: {len(a)} exported symbols, ours: {len(b)}")
    for s in sorted(a - b):
        print(f"only in reference: {s}")
    for s in sorted(b - a):
        print(f"only in ours: {s}")
    return 0 if a == b else 1


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "dump":
        cmd_dump(sys.argv[2])
        return 0
    if cmd == "compare":
        return cmd_compare(sys.argv[2], sys.argv[3])
    if cmd == "dynsym":
        return cmd_dynsym(sys.argv[2], sys.argv[3])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
