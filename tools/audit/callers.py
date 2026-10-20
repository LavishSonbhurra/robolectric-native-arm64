"""callers.py LIB TARGET_HEX...: x86_64 direct call sites (e8) to the given addresses; caller symbol if .symtab."""
import struct, sys, bisect, collections
path = sys.argv[1]; tg = {int(x, 16) for x in sys.argv[2:]}
d = open(path, 'rb').read()
shoff = struct.unpack_from('<Q', d, 0x28)[0]; shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x3A)
secs = []
for i in range(shnum):
    nm, ty, fl, addr, off, size, link, info, al, es = struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize)
    secs.append(dict(nm=nm, ty=ty, addr=addr, off=off, size=size, link=link))
so = secs[shstrndx]['off']
for x in secs: x['name'] = d[so + x['nm']:d.index(b'\0', so + x['nm'])].decode()
by = {x['name']: x for x in secs}
syms = []
if '.symtab' in by:
    st = by['.symtab']; strt = secs[st['link']]
    for i in range(st['size'] // 24):
        nm, info, oth, shn, val, sz = struct.unpack_from('<IBBHQQ', d, st['off'] + i * 24)
        if info & 0xf == 2 and val: syms.append((val, sz, d[strt['off'] + nm:d.index(b'\0', strt['off'] + nm)].decode()))
syms.sort(); starts = [s[0] for s in syms]
def sym(a):
    i = bisect.bisect_right(starts, a) - 1
    return syms[i][2] if i >= 0 and syms[i][0] <= a < syms[i][0] + max(syms[i][1], 1) else '?'
t = by['.text']; text = d[t['off']:t['off'] + t['size']]
hits = []
for j in range(len(text) - 5):
    if text[j] == 0xe8 and t['addr'] + j + 5 + struct.unpack_from('<i', text, j + 1)[0] in tg: hits.append(t['addr'] + j)
print('call sites', len(hits))
if syms:
    c = collections.Counter(sym(h) for h in hits)
    for k, v in c.most_common(): print(v, k)
else:
    print(' '.join(hex(h) for h in hits[:200]))
