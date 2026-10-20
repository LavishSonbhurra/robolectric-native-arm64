"""classify.py PATCHES: per commit, host-relevance signals in its diff."""
import re, sys
KEY = re.compile(r'__ANDROID__|__linux__|_WIN32|__APPLE__|__BIONIC__|LAYOUTLIB|[Ll]ayoutlib|[Rr]obolectric|RNG\b|[Rr]avenwood|HostRuntime|host_supported|\bhost\b|linux_glibc|\bdarwin\b|\bwindows\b|hostgraphics|_host\.cpp|platform/host')
cur = None; files = []; hits = {}
out = []
def flush():
    if cur: out.append((cur, files, hits))
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if line.startswith('@@COMMIT '):
        flush(); cur = line[9:].rstrip(); files = []; hits = {}; continue
    if line.startswith('diff --git '):
        f = line.split(' b/', 1)[1].strip(); files.append(f); fname = f; continue
    if line.startswith(('+++', '---')): continue
    if line[:1] in '+-' or line.startswith('@@ '):
        for m in KEY.findall(line):
            k = (fname, m); hits[k] = hits.get(k, 0) + 1
    if re.search(r'host|Host|platform/host', fname if files else '') and line[:1] in '+-':
        hits[(fname, '<hostfile>')] = hits.get((fname, '<hostfile>'), 0) + 1
flush()
for c, fs, h in out:
    if not h: continue
    # drop files that are huge generated or tests
    s = {}
    for (f, k), n in h.items():
        s.setdefault(f, []).append('%s:%d' % (k, n))
    print('##', c)
    for f, ks in s.items(): print('   ', f, ' '.join(ks[:8]))
