"""inr1.py PATCHES ROOT: per commit and file, share of added lines present in ROOT/<file> (r1 tree)
and share of removed lines still present. Low 'add' = r1 lacks the change."""
import os, re, sys
root = sys.argv[2]
def norm(s): return re.sub(r'\s+', ' ', s.strip())
cur = None; per = {}; order = []
fname = None
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if line.startswith('@@COMMIT '):
        cur = line[9:].rstrip(); order.append(cur); per[cur] = {}; continue
    if line.startswith('diff --git '):
        fname = line.split(' b/', 1)[1].strip(); per[cur].setdefault(fname, ([], [])); continue
    if line.startswith(('+++', '---')) or fname is None: continue
    if line[:1] in '+-':
        s = norm(line[1:])
        if len(s) < 14 or s.startswith(('//', '/*', '*', '#include')) or s in ('};', '}', '#endif', '#else'): continue
        per[cur][fname][0 if line[0] == '+' else 1].append(s)
cache = {}
def text(f):
    if f not in cache:
        p = os.path.join(root, f)
        cache[f] = norm(open(p, encoding='utf-8', errors='replace').read().replace('\n', ' \n ')) if os.path.exists(p) else None
    return cache[f]
for c in order:
    rows = []
    for f, (a, r) in per[c].items():
        if f.endswith(('.bp', '.exp', '.java')) or 'RobolectricNativeRuntime' in f: continue
        t = text(f)
        if t is None: rows.append('    %-60s (not in r1 tree)' % f); continue
        ia = sum(1 for s in a if s in t); ir = sum(1 for s in r if s in t)
        rows.append('    %-60s add %d/%d  rem-still %d/%d' % (f, ia, len(a), ir, len(r)))
    if rows: print('##', c); print('\n'.join(rows))
