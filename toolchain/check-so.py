#!/usr/bin/env python3
"""Post-link checks for a shared library meant to run on old glibc distros.

Fails (exit status 1) when the library:
  * needs a GLIBC_* symbol version above the floor (default 2.31), or any
    GLIBC_PRIVATE or non-glibc version (GLIBCXX_*, CXXABI_*, GCC_*),
  * has a DT_NEEDED entry outside libc, libm, libdl, libpthread, librt and
    the dynamic loader of its architecture,
  * exports a symbol that the version script does not list as global,
  * has an executable stack (PT_GNU_STACK with PF_X, or no PT_GNU_STACK),
  * has text relocations, DT_RPATH/DT_RUNPATH, no GNU_RELRO or no BIND_NOW
    (each can be relaxed with an option, e.g. for the AOSP reference, which
    has a RUNPATH),
  * has a strong undefined symbol with no version (it could only be resolved
    by whatever happens to be loaded in the process); weak ones are fine.

The ELF reader is self-contained (ELF64 little-endian: aarch64, x86_64), so
no binutils are needed. Patterns inside `extern "C++"` blocks of a version
script are matched against demangled names, which needs llvm-cxxfilt or
c++filt.

Usage: check-so.py [--floor 2.31] [--version-script FILE] LIB.so
"""

import argparse
import fnmatch
import re
import shutil
import struct
import subprocess
import sys

EM_X86_64 = 62
EM_AARCH64 = 183
LOADERS = {EM_AARCH64: "ld-linux-aarch64.so.1", EM_X86_64: "ld-linux-x86-64.so.2"}
ALLOWED_NEEDED = {"libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1"}
GLIBC_LIBS = ALLOWED_NEEDED | set(LOADERS.values())

PT_GNU_STACK, PT_GNU_RELRO, PF_X = 0x6474E551, 0x6474E552, 1
SHT_DYNSYM, SHT_DYNAMIC = 11, 6
SHT_GNU_VERSYM, SHT_GNU_VERNEED, SHT_GNU_VERDEF = 0x6FFFFFFF, 0x6FFFFFFE, 0x6FFFFFFD
DT_NEEDED, DT_SONAME, DT_RPATH, DT_RUNPATH, DT_TEXTREL, DT_FLAGS, DT_FLAGS_1 = 1, 14, 15, 29, 22, 30, 0x6FFFFFFB
DF_TEXTREL, DF_BIND_NOW, DF_1_NOW = 0x4, 0x8, 0x1
STB_NAMES = {0: "LOCAL", 1: "GLOBAL", 2: "WEAK", 10: "UNIQUE"}


class Elf:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = data = f.read()
        if data[:4] != b"\x7fELF":
            raise SystemExit(f"check-so: {path}: not an ELF file")
        if data[4] != 2 or data[5] != 1:
            raise SystemExit(f"check-so: {path}: only ELF64 little-endian is supported")
        (self.e_type, self.machine, _, _, phoff, shoff, _, _, phentsize, phnum, shentsize,
         shnum, _) = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
        self.phdrs = [struct.unpack_from("<IIQQQQQQ", data, phoff + i * phentsize) for i in range(phnum)]
        self.shdrs = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize) for i in range(shnum)]

    def section(self, sh_type):
        for s in self.shdrs:
            if s[1] == sh_type:
                return s
        return None

    def cstr(self, strtab, off):
        base = strtab[4] + off
        end = self.data.index(b"\0", base)
        return self.data[base:end].decode("utf-8", "replace")

    def dynamic(self):
        s = self.section(SHT_DYNAMIC)
        out = []
        if not s:
            return out
        strtab = self.shdrs[s[6]]
        for i in range(s[5] // 16):
            tag, val = struct.unpack_from("<qQ", self.data, s[4] + i * 16)
            if tag == 0:
                break
            if tag in (DT_NEEDED, DT_SONAME, DT_RPATH, DT_RUNPATH):
                val = self.cstr(strtab, val)
            out.append((tag, val))
        return out

    def dynsyms(self):
        """[(name, bind, type, shndx, visibility, version, version_file, hidden)]"""
        s = self.section(SHT_DYNSYM)
        if not s:
            return []
        strtab = self.shdrs[s[6]]
        n = s[5] // 24
        versym = self.section(SHT_GNU_VERSYM)
        vers = {}  # index -> (name, file or None)
        vn = self.section(SHT_GNU_VERNEED)
        if vn:
            vstr = self.shdrs[vn[6]]
            off = vn[4]
            while True:
                _, cnt, fileoff, aux, nxt = struct.unpack_from("<HHIII", self.data, off)
                fname = self.cstr(vstr, fileoff)
                a = off + aux
                for _ in range(cnt):
                    _, _, other, name, anext = struct.unpack_from("<IHHII", self.data, a)
                    vers[other] = (self.cstr(vstr, name), fname)
                    a += anext
                if not nxt:
                    break
                off += nxt
        self.verdef_names = set()
        vd = self.section(SHT_GNU_VERDEF)
        if vd:
            vstr = self.shdrs[vd[6]]
            off = vd[4]
            while True:
                _, flags, ndx, cnt, _, aux, nxt = struct.unpack_from("<HHHHIII", self.data, off)
                if cnt:
                    name = self.cstr(vstr, struct.unpack_from("<I", self.data, off + aux)[0])
                    vers[ndx] = (name, None)
                    self.verdef_names.add(name)
                if not nxt:
                    break
                off += nxt
        out = []
        for i in range(1, n):
            name, info, other, shndx, _, _ = struct.unpack_from("<IBBHQQ", self.data, s[4] + i * 24)
            vname, vfile, hidden = None, None, False
            if versym:
                v = struct.unpack_from("<H", self.data, versym[4] + i * 2)[0]
                hidden = bool(v & 0x8000)
                v &= 0x7FFF
                if v >= 2:
                    vname, vfile = vers.get(v, (f"#{v}", None))
            out.append((self.cstr(strtab, name), info >> 4, info & 0xF, shndx, other & 3, vname, vfile, hidden))
        return out


def parse_version_script(path):
    """Return (global C patterns, global C++ patterns, local patterns)."""
    text = open(path).read()
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"#[^\n]*", " ", text)
    glob_c, glob_cxx, local = [], [], []
    # Tokenize: words, quoted strings, braces, colons, semicolons.
    toks = re.findall(r'"[^"]*"|[{}:;]|[^\s{}:;"]+', text)
    scope = None
    lang = []  # stack of language per brace level
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("global", "local") and i + 1 < len(toks) and toks[i + 1] == ":":
            scope = t
            i += 2
            continue
        if t == "extern" and i + 2 < len(toks) and toks[i + 2] == "{":
            lang.append(toks[i + 1].strip('"'))
            i += 3
            continue
        if t == "{":
            lang.append(lang[-1] if lang else "C")
            scope = scope or "global"
        elif t == "}":
            if lang:
                lang.pop()
        elif t == ";":
            pass
        elif lang:
            pat = t.strip('"')
            if scope == "local":
                local.append(pat)
            elif lang[-1] == "C++":
                glob_cxx.append(pat)
            else:
                glob_c.append(pat)
        i += 1
    return glob_c, glob_cxx, local


def demangle(names):
    tool = shutil.which("llvm-cxxfilt") or shutil.which("c++filt")
    if not tool:
        raise SystemExit("check-so: the version script has extern \"C++\" patterns; need llvm-cxxfilt or c++filt")
    r = subprocess.run([tool], input="\n".join(names) + "\n", capture_output=True, text=True, check=True)
    return dict(zip(names, r.stdout.splitlines()))


def vtuple(s):
    return tuple(int(x) for x in s.split("."))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lib")
    ap.add_argument("--floor", default="2.31", help="highest allowed GLIBC_ version (default 2.31)")
    ap.add_argument("--version-script", help="version script the library was linked with")
    ap.add_argument("--allow-needed", action="append", default=[], help="extra allowed DT_NEEDED entry")
    ap.add_argument("--allow-undefined", action="append", default=[],
                    help="glob of strong unversioned undefined symbols to accept")
    ap.add_argument("--allow-runpath", action="store_true", help="accept DT_RPATH/DT_RUNPATH")
    ap.add_argument("--no-require-now", action="store_true", help="do not require BIND_NOW")
    ap.add_argument("--no-require-relro", action="store_true", help="do not require PT_GNU_RELRO")
    ap.add_argument("-v", "--verbose", action="store_true", help="also list what passed")
    args = ap.parse_args()

    elf = Elf(args.lib)
    errors = []
    info = []
    floor = vtuple(args.floor)

    loader = LOADERS.get(elf.machine)
    if loader is None:
        errors.append(f"unsupported machine {elf.machine}")
    allowed = ALLOWED_NEEDED | {loader} | set(args.allow_needed)

    dyn = elf.dynamic()
    needed = [v for t, v in dyn if t == DT_NEEDED]
    for n in needed:
        if n not in allowed:
            errors.append(f"unexpected DT_NEEDED {n}")
    info.append(f"NEEDED: {', '.join(needed) or '(none)'}")
    for t, v in dyn:
        if t in (DT_RPATH, DT_RUNPATH) and not args.allow_runpath:
            errors.append(f"{'RPATH' if t == DT_RPATH else 'RUNPATH'} is set: {v}")
    flags = sum(v for t, v in dyn if t == DT_FLAGS)
    flags1 = sum(v for t, v in dyn if t == DT_FLAGS_1)
    if any(t == DT_TEXTREL for t, _ in dyn) or flags & DF_TEXTREL:
        errors.append("has text relocations (DT_TEXTREL)")
    if not (flags & DF_BIND_NOW or flags1 & DF_1_NOW) and not args.no_require_now:
        errors.append("not linked with -z now (no BIND_NOW)")

    stack = [p for p in elf.phdrs if p[0] == PT_GNU_STACK]
    if not stack:
        errors.append("no PT_GNU_STACK: the stack would be executable")
    elif stack[0][1] & PF_X:
        errors.append("executable stack (PT_GNU_STACK has PF_X)")
    if not any(p[0] == PT_GNU_RELRO for p in elf.phdrs) and not args.no_require_relro:
        errors.append("no PT_GNU_RELRO (not linked with -z relro)")

    syms = elf.dynsyms()
    # Symbol versions this library needs.
    by_version = {}
    for name, bind, typ, shndx, vis, vname, vfile, hidden in syms:
        if shndx == 0 and vname:
            by_version.setdefault((vfile, vname), []).append(name)
    max_glibc = None
    for (vfile, vname), names in sorted(by_version.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
        sample = ", ".join(sorted(names)[:6]) + (" ..." if len(names) > 6 else "")
        m = re.fullmatch(r"GLIBC_(\d+(?:\.\d+)*)", vname)
        if m and vfile in GLIBC_LIBS:
            v = vtuple(m.group(1))
            max_glibc = max(max_glibc or v, v)
            if v > floor:
                errors.append(f"{vfile} {vname} is above the floor GLIBC_{args.floor}: {sample}")
        else:
            errors.append(f"{vfile} {vname} is not an allowed glibc version: {sample}")
    if max_glibc:
        info.append(f"highest GLIBC version needed: GLIBC_{'.'.join(map(str, max_glibc))} "
                    f"(floor {args.floor})")

    # Undefined symbols with no version.
    for name, bind, typ, shndx, vis, vname, vfile, hidden in syms:
        if shndx == 0 and not vname and name and bind != 2:
            if not any(fnmatch.fnmatchcase(name, p) for p in args.allow_undefined):
                errors.append(f"strong undefined symbol with no version: {name}")

    # Exports against the version script.
    exported = [s for s in syms if s[3] != 0 and s[1] in (1, 2, 10) and s[4] in (0, 3) and s[0]
                and s[0] not in elf.verdef_names]
    info.append(f"exported symbols: {len(exported)}")
    if args.version_script:
        glob_c, glob_cxx, _ = parse_version_script(args.version_script)
        names = [s[0] for s in exported]
        dem = demangle(names) if glob_cxx else {}
        bad = []
        for n in names:
            if any(fnmatch.fnmatchcase(n, p) for p in glob_c):
                continue
            if glob_cxx and any(fnmatch.fnmatchcase(dem.get(n, n), p) for p in glob_cxx):
                continue
            bad.append(n)
        for n in bad[:50]:
            errors.append(f"exported but not global in the version script: {n}")
        if len(bad) > 50:
            errors.append(f"... and {len(bad) - 50} more exports outside the version script")
    else:
        info.append("no --version-script given: exports not checked")

    for line in info:
        print(f"check-so: {line}")
    for e in errors:
        print(f"check-so: FAIL: {e}")
    print(f"check-so: {args.lib}: {'FAIL' if errors else 'OK'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
