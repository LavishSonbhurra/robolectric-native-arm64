"""xref.py LIB STRING [--dis N]: find C-string STRING in LIB (x86_64 ELF), every rip-relative
reference to it in .text, the containing symbol when .symtab exists, optional disassembly."""
import re, struct, subprocess, sys, bisect
path, s = sys.argv[1], sys.argv[2]
dis = int(sys.argv[sys.argv.index('--dis') + 1]) if '--dis' in sys.argv else 0
d = open(path, 'rb').read()
shoff = struct.unpack_from('<Q', d, 0x28)[0]; shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x3A)
secs = []
for i in range(shnum):
    nm, ty, fl, addr, off, size, link, info, al, es = struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * shentsize)
    secs.append(dict(nm=nm, ty=ty, addr=addr, off=off, size=size, link=link, es=es))
so = secs[shstrndx]['off']
for x in secs: x['name'] = d[so + x['nm']:d.index(b'\0', so + x['nm'])].decode()
by = {x['name']: x for x in secs}
def o2v(o):
    for x in secs:
        if x['ty'] != 8 and x['addr'] and x['off'] <= o < x['off'] + x['size']: return x['addr'] + o - x['off']
syms = []
if '.symtab' in by:
    st = by['.symtab']; strt = secs[st['link']]
    for i in range(st['size'] // 24):
        nm, info, oth, shn, val, sz = struct.unpack_from('<IBBHQQ', d, st['off'] + i * 24)
        if info & 0xf == 2 and val:
            syms.append((val, sz, d[strt['off'] + nm:d.index(b'\0', strt['off'] + nm)].decode()))
syms.sort(); starts = [x[0] for x in syms]
def sym(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and syms[i][0] <= a < syms[i][0] + max(syms[i][1], 1): return syms[i][2]
    return '?'
needle = s.encode() + b'\0'
targets = []
i = d.find(needle)
while i >= 0:
    if i == 0 or d[i - 1] == 0 or True:
        targets.append(o2v(i))
    i = d.find(needle, i + 1)
# suffix-merged strings: also accept matches not at string start
print('string at', [hex(t) for t in targets if t])
t = by['.text']; text = d[t['off']:t['off'] + t['size']]
tset = set(x for x in targets if x)
hits = []
for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', text):
    j = m.start(); disp = struct.unpack_from('<i', text, j + 3)[0]
    va = t['addr'] + j + 7 + disp
    if va in tset: hits.append(t['addr'] + j)
for h in hits:
    print('ref at', hex(h), sym(h))
    if dis:
        r = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', '--start-address=%d' % (h - dis), '--stop-address=%d' % (h + dis), path], capture_output=True, text=True).stdout
        print('\n'.join(r.split('\n')[6:]))
