"""jnifn.py LIB NAME [SIG]: function addresses of JNI methods NAME (optionally SIG)."""
import sys
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import jni_tables as J
e = J.Elf(sys.argv[1])
for loc, rows in J.tables(e):
    for n, s, fn in rows:
        if n == sys.argv[2] and (len(sys.argv) < 4 or s == sys.argv[3]):
            print(hex(loc), n, s, hex(fn))
