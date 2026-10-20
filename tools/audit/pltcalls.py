"""pltcalls.py LIB NAME...: call sites (e8 rel32 / jmp e9) of imported functions NAME via PLT, x86_64.
Prints count and, with .symtab, the calling functions."""
import re, struct, sys, bisect, subprocess
path, names = sys.argv[1], sys.argv[2:]
# use llvm-objdump to map plt stubs to names
out = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', '-j', '.plt', path], capture_output=True, text=True).stdout
plt = {}
for m in re.finditer(r'^([0-9a-f]+) <([^>]+)@plt>:', out, re.M):
    plt[int(m.group(1), 16)] = m.group(2)
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
        if info & 0xf == 2 and val:
            syms.append((val, sz, d[strt['off'] + nm:d.index(b'\0', strt['off'] + nm)].decode()))
syms.sort(); starts = [x[0] for x in syms]
def sym(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and syms[i][0] <= a < syms[i][0] + max(syms[i][1], 1): return syms[i][2]
    return '?'
t = by['.text']; text = d[t['off']:t['off'] + t['size']]
want = {a: n for a, n in plt.items() if n in names}
res = {n: [] for n in names}
for j in range(len(text) - 5):
    if text[j] in (0xe8, 0xe9):
        tgt = t['addr'] + j + 5 + struct.unpack_from('<i', text, j + 1)[0]
        if tgt in want: res[want[tgt]].append(t['addr'] + j)
for n in names:
    print(n, len(res[n]))
    if syms:
        import collections
        c = collections.Counter(sym(a) for a in res[n])
        for a in sorted(res[n]): print("   ", hex(a), sym(a)[:120])
    else:
        print('   ', ' '.join(hex(a) for a in res[n][:60]))
