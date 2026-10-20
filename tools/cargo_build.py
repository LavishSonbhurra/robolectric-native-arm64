#!/usr/bin/env python3
"""Build Rust host tools and libraries from the fetched AOSP sources with
cargo, out of tree.

The crates are copied (mtime-preserving) from src/ into a staging tree under
the build directory with the same relative layout, so build scripts that
locate files relative to the AOSP root (aconfig's does) still work, and
nothing is written into src/. A workspace manifest and a Cargo.lock from
tools/cargo/ are dropped into the staged workspace root.

Usage:
  cargo_build.py --stage DIR --workspace REL --manifest FILE --lock FILE
                 [--copy REL ...] [--link REL ...] -- <cargo args>
"""

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")


def sync_tree(src, dst):
    """Mirror src into dst, keeping mtimes (so cargo does not rebuild) and
    relative symlinks."""
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        ddir = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(ddir, exist_ok=True)
        for name in dirnames + filenames:
            sp = os.path.join(dirpath, name)
            dp = os.path.join(ddir, name)
            if os.path.islink(sp):
                target = os.readlink(sp)
                if os.path.islink(dp) and os.readlink(dp) == target:
                    continue
                if os.path.lexists(dp):
                    if os.path.isdir(dp) and not os.path.islink(dp):
                        shutil.rmtree(dp)
                    else:
                        os.unlink(dp)
                os.symlink(target, dp)
                if name in dirnames:
                    dirnames.remove(name)
            elif name in filenames:
                st = os.stat(sp)
                if os.path.exists(dp) and not os.path.islink(dp):
                    dt = os.stat(dp)
                    if dt.st_size == st.st_size and int(dt.st_mtime) == int(st.st_mtime):
                        continue
                shutil.copy2(sp, dp)


def main():
    argv = sys.argv[1:]
    if "--" not in argv:
        sys.exit("cargo_build.py: missing -- before cargo arguments")
    i = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--workspace", required=True, help="workspace dir, relative to the AOSP root")
    ap.add_argument("--manifest", help="Cargo.toml to use as the workspace manifest")
    ap.add_argument("--lock", help="Cargo.lock to use (updated in place when it changes)")
    ap.add_argument("--copy", action="append", default=[], help="dir to stage, relative to the AOSP root")
    ap.add_argument("--link", action="append", default=[], help="dir to symlink into the stage")
    ap.add_argument("--target-dir", required=True)
    args = ap.parse_args(argv[:i])
    cargo_args = argv[i + 1:]

    for rel in args.copy:
        sync_tree(os.path.join(SRC, rel), os.path.join(args.stage, rel))
    for rel in args.link:
        dst = os.path.join(args.stage, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.islink(dst):
            os.symlink(os.path.join(SRC, rel), dst)
    ws = os.path.join(args.stage, args.workspace)
    if args.manifest:
        dst = os.path.join(ws, "Cargo.toml")
        with open(args.manifest) as f:
            text = f.read()
        if not os.path.exists(dst) or open(dst).read() != text:
            with open(dst, "w") as f:
                f.write(text)
    if args.lock and os.path.exists(args.lock):
        shutil.copy2(args.lock, os.path.join(ws, "Cargo.lock"))
    # C/C++ compiled by build scripts (cc crate, e.g. cxx's src/cxx.cc) must
    # use clang and libc++ like the rest of the build.
    env = dict(os.environ, CARGO_TARGET_DIR=os.path.abspath(args.target_dir),
               CC="clang", CXX="clang++", CXXFLAGS="-stdlib=libc++")
    r = subprocess.run(["cargo", *cargo_args], cwd=ws, env=env)
    if r.returncode == 0 and args.lock:
        new = os.path.join(ws, "Cargo.lock")
        if not os.path.exists(args.lock) or open(new).read() != open(args.lock).read():
            shutil.copy2(new, args.lock)
            print(f"cargo_build.py: updated {os.path.relpath(args.lock, ROOT)}")
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
