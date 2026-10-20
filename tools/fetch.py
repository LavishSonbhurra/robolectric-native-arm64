#!/usr/bin/env python3
"""Download the AOSP projects this build needs, at the pinned revision.

Reads config/aosp.toml (the pin) and config/projects.toml (which projects,
and optionally which sub-directories of them), resolves every project to a
commit through Gitiles, downloads per-project (or per-directory) tarballs,
extracts them under src/<path>, verifies them against config/sources.lock.json
and applies patches/<path>/*.patch in name order.

A project fetched in parts (`subdirs` or `files`) also gets the licence files
at its top level (NOTICE, LICENSE, COPYING, MODULE_LICENSE_*, METADATA, ...;
see LICENSE_FILE_PREFIXES), found by listing the project's root directory at
the pinned commit. They are recorded as `license_files` in the lock, so a
later run needs no listing. tools/gen_notices.py reads them.

Usage:
  tools/fetch.py              fetch what is missing or stale, verify the rest
  tools/fetch.py --update-lock   record new hashes instead of failing on change
  tools/fetch.py --only PATH  restrict to one project path (repeatable)

Only the Python standard library is used. Tarballs are cached in
src/.cache/tarballs and single files in src/.cache/files, so re-extracting
after a patch change is cheap and needs no network.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
CACHE = os.path.join(SRC, ".cache")
STAMPS = os.path.join(SRC, ".stamps")
LOCK = os.path.join(ROOT, "config", "sources.lock.json")


# Top-level files of a project that carry licence terms or licence metadata.
# Matched case-insensitively against the start of the file name.
LICENSE_FILE_PREFIXES = ("notice", "license", "licence", "copying", "copyright", "patents",
                         "module_license_", "metadata")


def is_license_file(name):
    n = name.lower()
    return any(n.startswith(p) for p in LICENSE_FILE_PREFIXES)


def load_toml(name):
    with open(os.path.join(ROOT, "config", name), "rb") as f:
        return tomllib.load(f)


def http_get(url, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "robolectric-native-arm64-fetch"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500:
                raise SystemExit(f"GET {url}: HTTP {e.code} (missing path or revision?)")
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def gitiles_json(url):
    data = http_get(url).decode()
    if data.startswith(")]}'"):
        data = data[4:]
    return json.loads(data)


def manifest(cfg):
    path = os.path.join(CACHE, f"manifest-{cfg['aosp']['tag']}.xml")
    if not os.path.exists(path):
        url = f"{cfg['aosp']['gitiles']}/platform/manifest/+/refs/tags/{cfg['aosp']['tag']}/default.xml?format=TEXT"
        os.makedirs(CACHE, exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(http_get(url)))
    root = ET.parse(path).getroot()
    default_rev = root.find("default").get("revision")
    projects = {}
    for p in root.iter("project"):
        projects[p.get("path", p.get("name"))] = (p.get("name"), p.get("revision", default_rev))
    return projects


def git_archive(url, commit, sub):
    """Gitiles refuses to build archives for some projects (HTTP 503, usually
    large test data). Fetch the single commit shallowly and let git build the
    same tarball instead. The temporary repository is removed afterwards.

    Gitiles ignores the export-ignore and export-subst attributes, git archive
    applies them. They are switched off in info/attributes (which overrides the
    project's .gitattributes), so both paths give the same tree and whichever
    one a run happens to take, the content hash is the same."""
    gd = os.path.join(CACHE, "git-tmp")
    shutil.rmtree(gd, ignore_errors=True)
    run = lambda *a, **kw: subprocess.run(["git", "-C", gd, *a], check=True, **kw)
    os.makedirs(gd)
    run("init", "-q", "--bare")
    os.makedirs(os.path.join(gd, "info"), exist_ok=True)
    with open(os.path.join(gd, "info", "attributes"), "w") as f:
        f.write("* -export-ignore -export-subst\n")
    run("fetch", "-q", "--depth", "1", url, commit)
    treeish = f"{commit}:{sub}" if sub else commit
    blob = run("archive", "--format=tar.gz", treeish, stdout=subprocess.PIPE).stdout
    shutil.rmtree(gd, ignore_errors=True)
    return blob


def gitiles_file(base, name, commit, fpath):
    """One file at a commit, cached under src/.cache/files."""
    cp = os.path.join(CACHE, "files", f"{name.replace('/', '__')}@{commit}", fpath)
    if not os.path.exists(cp):
        data = base64.b64decode(http_get(f"{base}/{name}/+/{commit}/{fpath}?format=TEXT"))
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp + ".tmp", "wb") as f:
            f.write(data)
        os.replace(cp + ".tmp", cp)
    with open(cp, "rb") as f:
        return f.read()


def top_level_license_files(base, name, commit):
    """[[file name, 'f' or 'l'], ...] for the licence files in the project's
    root directory ('l' for a symlink, whose content is the link target)."""
    tree = gitiles_json(f"{base}/{name}/+/{commit}/?format=JSON")
    out = []
    for e in tree.get("entries", []):
        if e.get("type") == "blob" and is_license_file(e["name"]):
            out.append([e["name"], "l" if e.get("mode") == 0o120000 else "f"])
    return sorted(out)


def tree_hash(top):
    """Content hash of an extracted tree: stable across tarball re-encoding."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames.sort()
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, top)
            if os.path.islink(p):
                h.update(b"L" + rel.encode() + b"\0" + os.readlink(p).encode() + b"\0")
                continue
            st = os.stat(p)
            with open(p, "rb") as f:
                fh = hashlib.sha256(f.read()).hexdigest()
            h.update(b"F" + rel.encode() + b"\0" + (b"x" if st.st_mode & 0o111 else b"-") + fh.encode() + b"\0")
    return h.hexdigest()


def patch_files(path):
    d = os.path.join(ROOT, "patches", path)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".patch")]


def file_sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def extract(blob, dest, final_dest):
    """Extract a Gitiles tarball. Member names may not escape `dest`; symlinks
    may point anywhere inside src/ (AOSP has relative links between projects)
    but links that would leave src/ are dropped."""
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        members = []
        for m in t.getmembers():
            if m.issym() or m.islnk():
                where = os.path.dirname(os.path.join(final_dest, m.name))
                target = os.path.normpath(os.path.join(where, m.linkname))
                if os.path.isabs(m.linkname) or not target.startswith(SRC + os.sep) or m.islnk():
                    print(f"  skip link {m.name} -> {m.linkname}")
                    continue
            members.append(m)
        t.extractall(dest, members=members, filter="tar")


def fetch_project(cfg, proj, mf, lock, update_lock):
    path = proj["path"]
    if path not in mf:
        raise SystemExit(f"{path}: not in the manifest for {cfg['aosp']['tag']}")
    name, rev = mf[path]
    base = cfg["aosp"]["gitiles"]
    subdirs = proj.get("subdirs", [])
    files = proj.get("files", [])
    entry = lock.get(path)

    commit = entry["commit"] if entry and entry.get("rev") == rev else None
    if commit is None:
        commit = gitiles_json(f"{base}/{name}/+/{rev}?format=JSON")["commit"]

    # Licence files at the top of a project fetched in parts. The whole-project
    # tarball has them already.
    license_files = []
    if subdirs or files:
        if entry and entry.get("commit") == commit and "license_files" in entry:
            license_files = entry["license_files"]
        else:
            license_files = top_level_license_files(base, name, commit)
        license_files = [x for x in license_files if x[0] not in files]

    patches = patch_files(path)
    want_stamp = {
        "commit": commit,
        "subdirs": subdirs,
        "files": files,
        "license_files": license_files,
        "patches": [[os.path.basename(p), file_sha(p)] for p in patches],
    }
    stamp_path = os.path.join(STAMPS, path.replace("/", "__") + ".json")
    dest = os.path.join(SRC, path)
    if os.path.exists(stamp_path) and os.path.isdir(dest):
        with open(stamp_path) as f:
            if json.load(f) == want_stamp and entry and entry.get("commit") == commit:
                return False

    print(f"fetch {path} ({name} @ {commit[:12]})", flush=True)
    tmp = dest + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    tdir = os.path.join(CACHE, "tarballs")
    os.makedirs(tdir, exist_ok=True)
    parts = subdirs or ([] if files else [""])
    tar_shas = {}
    for sub in parts:
        cache_name = f"{name.replace('/', '__')}@{commit}{('__' + sub.replace('/', '__')) if sub else ''}.tar.gz"
        cp = os.path.join(tdir, cache_name)
        if not os.path.exists(cp):
            url = f"{base}/{name}/+archive/{commit}{('/' + sub) if sub else ''}.tar.gz"
            try:
                blob = None if proj.get("method") == "git" else http_get(url, tries=2)
            except RuntimeError as e:
                print(f"  {e}; falling back to a shallow git fetch", flush=True)
                blob = None
            if blob is None:
                blob = git_archive(f"{base}/{name}", commit, sub)
            with open(cp + ".tmp", "wb") as f:
                f.write(blob)
            os.replace(cp + ".tmp", cp)
        with open(cp, "rb") as f:
            blob = f.read()
        tar_shas[sub or "."] = hashlib.sha256(blob).hexdigest()
        extract(blob, os.path.join(tmp, sub) if sub else tmp, os.path.join(dest, sub) if sub else dest)
    for fpath in files:
        data = gitiles_file(base, name, commit, fpath)
        out = os.path.join(tmp, fpath)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
    for fname, kind in license_files:
        data = gitiles_file(base, name, commit, fname)
        out = os.path.join(tmp, fname)
        if kind == "l":
            # Same rule as for links in tarballs: keep links that stay in src/.
            target = data.decode()
            if os.path.isabs(target) or not os.path.normpath(os.path.join(dest, target)).startswith(SRC + os.sep):
                print(f"  skip link {fname} -> {target}")
                continue
            os.symlink(target, out)
        else:
            with open(out, "wb") as f:
                f.write(data)

    th = tree_hash(tmp)
    new_entry = {"name": name, "rev": rev, "commit": commit, "subdirs": subdirs,
                 "files": files, "tree_sha256": th, "tarball_sha256": tar_shas}
    if subdirs or files:
        new_entry["license_files"] = license_files
    if entry and entry.get("commit") == commit and entry.get("subdirs") == subdirs \
            and entry.get("files", []) == files and entry.get("license_files", []) == license_files \
            and entry["tree_sha256"] != th and not update_lock:
        shutil.rmtree(tmp)
        raise SystemExit(f"{path}: content hash mismatch against the lock file "
                         f"(have {th}, lock {entry['tree_sha256']})")
    # Same content as recorded: keep the entry as it is. Gitiles' gzip output is
    # not byte-stable, so a new tarball hash alone is no reason to touch the lock.
    if not (entry and not update_lock and entry.get("tree_sha256") == th
            and {k: v for k, v in entry.items() if k != "tarball_sha256"}
            == {k: v for k, v in new_entry.items() if k != "tarball_sha256"}):
        lock[path] = new_entry

    for p in patches:
        print(f"  patch {os.path.relpath(p, ROOT)}", flush=True)
        subprocess.run(["patch", "-p1", "--forward", "--no-backup-if-mismatch", "-s", "-d", tmp, "-i", p],
                       check=True)

    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.rename(tmp, dest)
    os.makedirs(STAMPS, exist_ok=True)
    with open(stamp_path, "w") as f:
        json.dump(want_stamp, f, indent=1)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update-lock", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    cfg = load_toml("aosp.toml")
    projects = load_toml("projects.toml")["project"]
    mf = manifest(cfg)
    lock = {}
    if os.path.exists(LOCK):
        with open(LOCK) as f:
            lock = json.load(f)
        if lock.get("_tag") != cfg["aosp"]["tag"]:
            print(f"lock file is for {lock.get('_tag')}, re-resolving for {cfg['aosp']['tag']}")
            lock = {}
    lock["_tag"] = cfg["aosp"]["tag"]

    changed = 0
    try:
        for proj in projects:
            if args.only and proj["path"] not in args.only:
                continue
            if fetch_project(cfg, proj, mf, lock, args.update_lock):
                changed += 1
    finally:
        wanted = {p["path"] for p in projects}
        if not args.only:
            for k in [k for k in lock if not k.startswith("_") and k not in wanted]:
                del lock[k]
        with open(LOCK, "w") as f:
            json.dump(dict(sorted(lock.items())), f, indent=1)
            f.write("\n")
    print(f"{changed} project(s) fetched, {len([p for p in projects])} in config")


if __name__ == "__main__":
    main()
