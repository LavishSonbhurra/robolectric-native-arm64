"""hunks.py PATCHES SHA...: print the hunks of commit SHA whose lines match the host keywords."""
import re, sys
KEY = re.compile(r'__ANDROID__|__linux__|_WIN32|__APPLE__|__BIONIC__|[Ll]ayoutlib|[Rr]obolectric|[Rr]avenwood|HostRuntime|\bhost\b|host_linux|linux_glibc|darwin|windows|hostgraphics')
want = set(sys.argv[2:]); cur = None; buf = []; fname = ''; out = []
def flush_hunk():
    global buf
    if buf and cur in want and (KEY.search(''.join(buf)) or 'hostgraphics' in fname):
        out.append('--- ' + fname + '\n' + ''.join(buf))
    buf = []
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if line.startswith('@@COMMIT '):
        flush_hunk()
        if cur in want: print('\n'.join(out)); out = []
        cur = line.split()[1]
        if cur in want: print('=' * 30, line.rstrip())
        continue
    if line.startswith('diff --git '):
        flush_hunk(); fname = line.split(' b/', 1)[1].strip(); continue
    if line.startswith('@@ '):
        flush_hunk(); buf = [line]; continue
    if buf: buf.append(line)
flush_hunk()
if cur in want: print('\n'.join(out))
