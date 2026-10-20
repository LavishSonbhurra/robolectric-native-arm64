#!/usr/bin/env python3
"""Build a Debian 11 (bullseye) sysroot from official Debian packages.

--arch selects the Debian architecture: arm64 (default) or amd64. Each
architecture has its own lock file and output directory.

The sysroot holds what clang and lld need to compile and link against glibc
2.31: libc6, libc6-dev, linux-libc-dev, and the GCC 10 runtime pieces
(libgcc-10-dev for crtbegin*.o, libgcc.a, libgcc_eh.a; libgcc-s1). Nothing is
installed or executed from the packages; they are unpacked with
`dpkg-deb -x`, so no root and no chroot is needed.

Of the documentation only the licence texts are kept: the Debian copyright
files (usr/share/doc/<package>/copyright) and usr/share/common-licenses. The
library links glibc's libc_nonshared.a, crti.o and crtn.o and GCC's crt
objects (and libgcc.a) statically, so their licences (LGPL-2.1, GPL-3 with
the GCC Runtime Library Exception) ship with it; tools/gen_notices.py reads
them. The copyright files refer to usr/share/common-licenses for the full
texts. Two packages are unpacked for these files only (LICENCE_PACKAGES):
gcc-10-base, because the doc directories of libgcc-10-dev and libgcc-s1 are
symlinks to its directory, and base-files, which has common-licenses.

Trust chain:
  1. dists/bullseye/InRelease from snapshot.debian.org at a pinned timestamp,
     checked with gpgv against the Debian archive keyring. The keyring comes
     from /usr/share/keyrings if the debian-archive-keyring package is
     installed, otherwise from `apt-get download debian-archive-keyring`
     (authenticated by the host's own apt sources). At least one good
     signature must come from a pinned bullseye key fingerprint.
  2. main/binary-<arch>/Packages.xz, checked against the SHA256 in InRelease.
  3. Each .deb, checked against the SHA256 in Packages.
The lock file (toolchain/sysroot.lock.json for arm64,
toolchain/sysroot-<arch>.lock.json otherwise) records the snapshot, the hash
of InRelease and every package version and hash. With a lock file present,
all of these must match it; pass --update to re-resolve and rewrite it.

Run it with `python3 -I`, since it reads downloaded files.
"""

import argparse
import hashlib
import json
import lzma
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

SNAPSHOT = "20250901T000000Z"
SUITE = "bullseye"
PACKAGES = ["libc6", "libc6-dev", "linux-libc-dev", "libgcc-10-dev", "libgcc-s1"]
# Unpacked aside; only usr/share/doc and usr/share/common-licenses are taken.
LICENCE_PACKAGES = ["gcc-10-base", "base-files"]
GCC_VERSION = "10"
# Debian architecture -> GNU triple (the multiarch directory name).
TRIPLES = {"arm64": "aarch64-linux-gnu", "amd64": "x86_64-linux-gnu"}

# Primary key fingerprints accepted for InRelease. From the
# debian-archive-keyring package (debian-archive-bullseye-automatic and
# debian-archive-bullseye-stable).
TRUSTED_FPRS = {
    "1F89983E0081FDE018F3CC9673A4F27B8DD47936",  # Debian Archive Automatic Signing Key (11/bullseye)
    "A4285295FC7B1A81600062A9605C66F00D6C9793",  # Debian Stable Release Key (11/bullseye)
}

# Pruned after unpacking: documentation and programs, none of which a
# compile or link reads. usr/share is pruned by prune_share(), which keeps
# the licence texts.
def prune_list(triple):
    return ["usr/bin", "usr/sbin", "sbin", "bin", "etc", "var",
            f"usr/lib/{triple}/gconv", f"usr/lib/{triple}/audit", "usr/libexec"]


# Bumped when the set of files kept from the packages changes, so that an
# existing sysroot is unpacked again.
LAYOUT = 2


def prune_share(root):
    """Remove usr/share except usr/share/doc/<package>/copyright (and the
    symlinked doc directories that lead to one) and usr/share/common-licenses.
    Returns the kept copyright files."""
    share = os.path.join(root, "usr/share")
    doc = os.path.join(share, "doc")
    for name in os.listdir(share) if os.path.isdir(share) else []:
        if name not in ("doc", "common-licenses"):
            p = os.path.join(share, name)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.unlink(p)
    kept = []
    for pkg in sorted(os.listdir(doc)) if os.path.isdir(doc) else []:
        p = os.path.join(doc, pkg)
        if os.path.islink(p):
            continue  # gcc-10-base and friends; dangling ones are removed later
        for name in os.listdir(p):
            q = os.path.join(p, name)
            if name == "copyright" and os.path.isfile(q) and not os.path.islink(q):
                kept.append(f"usr/share/doc/{pkg}/copyright")
            elif os.path.isdir(q) and not os.path.islink(q):
                shutil.rmtree(q)
            else:
                os.unlink(q)
        if not os.listdir(p):
            os.rmdir(p)
    return kept


def log(msg):
    print(f"make-sysroot: {msg}", flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest, sha256=None):
    """Download url to dest (reusing a cached copy whose hash matches)."""
    if sha256 and os.path.exists(dest) and sha256_file(dest) == sha256:
        return dest
    tmp = dest + ".part"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "robolectric-native-arm64-sysroot/1"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            break
        except OSError as e:
            if attempt == 3:
                raise SystemExit(f"make-sysroot: download failed: {url}: {e}")
            log(f"retrying {url} ({e})")
            time.sleep(5 * (attempt + 1))
    if sha256:
        got = sha256_file(tmp)
        if got != sha256:
            os.unlink(tmp)
            raise SystemExit(f"make-sysroot: SHA256 mismatch for {url}: got {got}, want {sha256}")
    os.replace(tmp, dest)
    return dest


def find_keyring(dl):
    system = "/usr/share/keyrings/debian-archive-keyring.gpg"
    if os.path.exists(system):
        return system, {"source": "installed debian-archive-keyring package"}
    kdir = os.path.join(dl, "keyring")
    os.makedirs(kdir, exist_ok=True)
    debs = [f for f in os.listdir(kdir) if f.endswith(".deb")]
    if not debs:
        log("fetching debian-archive-keyring with apt-get download")
        subprocess.run(["apt-get", "download", "debian-archive-keyring"], cwd=kdir, check=True)
        debs = [f for f in os.listdir(kdir) if f.endswith(".deb")]
    deb = os.path.join(kdir, sorted(debs)[-1])
    x = os.path.join(kdir, "x")
    shutil.rmtree(x, ignore_errors=True)
    subprocess.run(["dpkg-deb", "-x", deb, x], check=True)
    return (os.path.join(x, "usr/share/keyrings/debian-archive-keyring.gpg"),
            {"source": "apt-get download debian-archive-keyring", "deb": os.path.basename(deb),
             "sha256": sha256_file(deb)})


def verify_inrelease(path, keyring):
    """Check the clearsigned InRelease and return its signed text."""
    r = subprocess.run(["gpgv", "--status-fd", "1", "--keyring", keyring, path],
                       capture_output=True, text=True)
    good = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "VALIDSIG":
            good.add(parts[-1].upper())  # primary key fingerprint
    if r.returncode != 0 and not good:
        raise SystemExit(f"make-sysroot: InRelease signature check failed:\n{r.stderr}")
    ok = good & TRUSTED_FPRS
    if not ok:
        raise SystemExit(f"make-sysroot: no good signature from a pinned bullseye key (got {sorted(good)})")
    # Use gpgv's output of the signed data so that nothing outside the
    # signature is parsed.
    out = path + ".verified"
    r = subprocess.run(["gpgv", "--keyring", keyring, "--output", out, path], capture_output=True)
    if not os.path.exists(out):
        raise SystemExit("make-sysroot: gpgv could not extract the signed text")
    with open(out, encoding="utf-8") as f:
        text = f.read()
    os.unlink(out)
    return text, sorted(ok)


def release_sha256(text, name):
    in_sha = False
    for line in text.splitlines():
        if not line.startswith(" "):
            in_sha = line.startswith("SHA256:")
            continue
        if in_sha:
            h, size, fname = line.split()
            if fname == name:
                return h, int(size)
    raise SystemExit(f"make-sysroot: {name} not listed in InRelease")


def parse_packages(text, wanted):
    found = {}
    for stanza in text.split("\n\n"):
        fields = {}
        key = None
        for line in stanza.splitlines():
            if line.startswith((" ", "\t")):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                fields[key] = val.strip()
        name = fields.get("Package")
        if name in wanted:
            if name in found:
                raise SystemExit(f"make-sysroot: {name} listed twice in Packages")
            found[name] = {"version": fields["Version"], "filename": fields["Filename"],
                           "sha256": fields["SHA256"], "size": int(fields["Size"])}
    missing = set(wanted) - set(found)
    if missing:
        raise SystemExit(f"make-sysroot: not in Packages: {sorted(missing)}")
    return found


def fix_symlinks(root):
    """Rewrite absolute symlinks to point inside the sysroot (relatively)."""
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                continue
            t = os.readlink(p)
            if t.startswith("/"):
                rel = os.path.relpath(os.path.join(root, t.lstrip("/")), dirpath)
                os.unlink(p)
                os.symlink(rel, p)
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", choices=sorted(TRIPLES), default="arm64", help="Debian architecture")
    ap.add_argument("--out", help="default: toolchain/out/sysroot-bullseye-<arch>")
    ap.add_argument("--download-dir", default=os.path.join(HERE, "dl", "debian"))
    ap.add_argument("--lock", help="default: toolchain/sysroot.lock.json (arm64), sysroot-<arch>.lock.json")
    ap.add_argument("--update", action="store_true", help="re-resolve packages and rewrite the lock file")
    ap.add_argument("--snapshot", help=f"snapshot.debian.org timestamp (default {SNAPSHOT}, or the lock's)")
    args = ap.parse_args()
    arch = args.arch
    triple = TRIPLES[arch]
    if not args.out:
        args.out = os.path.join(HERE, "out", f"sysroot-bullseye-{arch}")
    if not args.lock:
        args.lock = os.path.join(HERE, "sysroot.lock.json" if arch == "arm64" else f"sysroot-{arch}.lock.json")

    lock = None
    if os.path.exists(args.lock) and not args.update:
        with open(args.lock) as f:
            lock = json.load(f)
        if lock.get("arch") != arch:
            raise SystemExit(f"make-sysroot: {args.lock} is for {lock.get('arch')}, not {arch}")
    snapshot = args.snapshot or (lock["snapshot"] if lock else SNAPSHOT)
    base = f"https://snapshot.debian.org/archive/debian/{snapshot}"

    dl = os.path.join(args.download_dir, snapshot)
    os.makedirs(dl, exist_ok=True)
    keyring, keyinfo = find_keyring(args.download_dir)

    inrel = os.path.join(dl, "InRelease")
    fetch(f"{base}/dists/{SUITE}/InRelease", inrel, lock["inrelease_sha256"] if lock else None)
    text, signers = verify_inrelease(inrel, keyring)
    log(f"InRelease signature good ({', '.join(signers)})")

    idx_name = f"main/binary-{arch}/Packages.xz"
    idx_sha, _ = release_sha256(text, idx_name)
    idx = fetch(f"{base}/dists/{SUITE}/{idx_name}", os.path.join(dl, f"Packages-{arch}.xz"), idx_sha)
    pkgs = parse_packages(lzma.decompress(open(idx, "rb").read()).decode("utf-8"),
                          PACKAGES + LICENCE_PACKAGES)

    if lock:
        for name, info in pkgs.items():
            want = lock["packages"].get(name)
            if want != info:
                raise SystemExit(f"make-sysroot: {name} differs from the lock file: {info} vs {want}")

    debs, licence_debs = [], []
    for name in PACKAGES + LICENCE_PACKAGES:
        info = pkgs[name]
        dest = os.path.join(dl, os.path.basename(info["filename"]))
        fetch(f"{base}/{info['filename']}", dest, info["sha256"])
        (debs if name in PACKAGES else licence_debs).append(dest)
        log(f"{name} {info['version']} ok")

    new_lock = {
        "snapshot": snapshot,
        "suite": SUITE,
        "arch": arch,
        "inrelease_sha256": sha256_file(inrel),
        "signed_by": signers,
        "packages_xz_sha256": idx_sha,
        "packages": {n: pkgs[n] for n in PACKAGES + LICENCE_PACKAGES},
        "keyring": keyinfo if "deb" in keyinfo else {"source": keyinfo["source"]},
        "gcc_version": GCC_VERSION,
    }
    stamp = {k: new_lock[k] for k in ("snapshot", "inrelease_sha256", "packages")}
    stamp["layout"] = LAYOUT
    stamp_text = json.dumps(stamp, sort_keys=True)

    stamp = os.path.join(args.out, ".ra64-sysroot.json")
    if os.path.exists(stamp) and open(stamp).read() == stamp_text:
        log(f"sysroot up to date: {args.out}")
    else:
        tmp = args.out + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        for deb in debs:
            subprocess.run(["dpkg-deb", "-x", deb, tmp], check=True)
        aside = tmp + ".licences"
        for deb in licence_debs:
            shutil.rmtree(aside, ignore_errors=True)
            subprocess.run(["dpkg-deb", "-x", deb, aside], check=True)
            for sub in ("usr/share/doc", "usr/share/common-licenses"):
                if os.path.isdir(os.path.join(aside, sub)):
                    shutil.copytree(os.path.join(aside, sub), os.path.join(tmp, sub),
                                    symlinks=True, dirs_exist_ok=True)
        shutil.rmtree(aside, ignore_errors=True)
        for p in prune_list(triple):
            path = os.path.join(tmp, p)
            if os.path.islink(path) or os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        kept = prune_share(tmp)
        n = fix_symlinks(tmp)
        # libgcc-10-dev ships libasan.so, libatomic.so, ... pointing at
        # packages we do not unpack. A dangling .so would shadow the .a next
        # to it at link time, so remove them.
        for dirpath, dirnames, filenames in os.walk(tmp):
            for name in filenames + dirnames:
                p = os.path.join(dirpath, name)
                if os.path.islink(p) and not os.path.exists(p):
                    os.unlink(p)
        gcc_dir = os.path.join(tmp, "usr/lib/gcc", triple, GCC_VERSION)
        for f in ("crtbeginS.o", "crtendS.o", "libgcc.a", "libgcc_eh.a"):
            if not os.path.exists(os.path.join(gcc_dir, f)):
                raise SystemExit(f"make-sysroot: {f} missing from {gcc_dir}")
        # The licence texts tools/gen_notices.py reads (config/notices-extra.toml).
        for f in ["usr/share/doc/libc6-dev/copyright", "usr/share/doc/libgcc-10-dev/copyright",
                  "usr/share/common-licenses/LGPL-2.1", "usr/share/common-licenses/GPL-3"]:
            if not os.path.isfile(os.path.join(tmp, f)):
                raise SystemExit(f"make-sysroot: {f} missing")
        log(f"kept {len(kept)} copyright files and usr/share/common-licenses")
        with open(os.path.join(tmp, ".ra64-sysroot.json"), "w") as f:
            f.write(stamp_text)
        shutil.rmtree(args.out, ignore_errors=True)
        os.replace(tmp, args.out)
        log(f"unpacked {len(debs)} packages into {args.out} ({n} absolute symlinks made relative)")

    if lock is None:
        with open(args.lock, "w") as f:
            json.dump(new_lock, f, indent=1, sort_keys=True)
            f.write("\n")
        log(f"wrote {args.lock}")


if __name__ == "__main__":
    sys.exit(main())
