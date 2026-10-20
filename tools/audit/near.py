"""near.py LIB ADDR [BACK FWD]: strings referenced by rip-relative lea in [ADDR-BACK, ADDR+FWD] (x86_64)."""
import re, struct, sys
path = sys.argv[1]; a = int(sys.argv[2], 16)
back = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x300; fwd = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x200
d = open(path, 'rb').read()
shoff = struct.unpack_from('<Q', d, 0x28)[0]; shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x3A)
secs = []
for i in range(shnum):
    nm, ty, fl, addr, off, size, link, info, al, es = struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize)
    secs.append(dict(nm=nm, ty=ty, addr=addr, off=off, size=size))
so = secs[shstrndx]['off']
for x in secs: x['name'] = d[so + x['nm']:d.index(b'\0', so + x['nm'])].decode()
by = {x['name']: x for x in secs}
t = by['.text']
def v2o(v):
    for x in secs:
        if x['ty'] != 8 and x['addr'] and x['addr'] <= v < x['addr'] + x['size']: return x['off'] + v - x['addr'], x['name']
    return None, None
lo = a - back - t['addr']; hi = a + fwd - t['addr']
text = d[t['off'] + lo:t['off'] + hi]
for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', text):
    j = m.start(); va = t['addr'] + lo + j + 7 + struct.unpack_from('<i', text, j + 3)[0]
    o, sn = v2o(va)
    if sn and 'rodata' in sn or sn == '.rodata.str1.1':
        e = d.find(b'\0', o); s = d[o:e]
        if 2 < len(s) < 200 and all(32 <= c < 127 for c in s):
            print(hex(t['addr'] + lo + j), repr(s.decode()))
