"""strdiff.py A B: C strings (>=6 printable chars, NUL-terminated) in A's .rodata not in B (whole file)."""
import re, struct, sys
def rodata(p):
    d = open(p, 'rb').read()
    shoff = struct.unpack_from('<Q', d, 0x28)[0]; es, n, si = struct.unpack_from('<HHH', d, 0x3A)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * es) for i in range(n)]
    so = secs[si][4]
    out = {}
    for s in secs:
        nm = d[so + s[0]:d.index(b'\0', so + s[0])].decode()
        out[nm] = d[s[4]:s[4] + s[5]]
    return d, out
def cstrs(b): return set(m.group(1) for m in re.finditer(rb'([\x20-\x7e]{6,})\x00', b))
da, sa = rodata(sys.argv[1]); db, sb = rodata(sys.argv[2])
A = cstrs(sa['.rodata']); Ball = cstrs(db)
miss = sorted(s for s in A if s not in Ball and s not in db)
for s in miss: print(s.decode())
