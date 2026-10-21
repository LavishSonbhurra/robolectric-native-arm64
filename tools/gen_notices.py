#!/usr/bin/env python3
"""Write the NOTICE file of a linked library and check that it covers everything in it.

The inputs are the ones the build used, so the notices cannot drift from what
is linked:

  * the closure written by bp2cmake (cmake-gen/closure.json): the library
    module, the static libraries on its link line (`link.static_libs`), the
    header-only modules (listed too, since their inline code is compiled into
    the others) and the source directory of every module;
  * the licence metadata of the fetched AOSP sources, resolved the way Soong
    does it: a module's `licenses` property, otherwise the
    `default_applicable_licenses` of the nearest enclosing Android.bp with a
    `package` module; each `license` module gives the licence kinds and the
    licence text files;
  * the crates in librustlibs.a (rustlibs/crates.tsv from bp2rust,
    `in_staticlib` = yes), resolved the same way from their directories;
  * config/notices-extra.toml for what Android.bp does not describe: the C++
    runtime, compiler-rt, libgcc and glibc objects from the sysroot, the Rust
    standard library, extra texts for some AOSP components and the
    attribution sentences some licences require;
  * config/notices-policy.toml: the licence kinds that may appear, and a
    written reason for every component AOSP marks "by exception only".

Two ways to run it:

  Link line only (before the link): every module on the link line, the Rust
  crates and every extra component are listed.

  After the link, with --why-extract (lld's --why-extract output) and
  optionally --link-deps (the link's dependency file): only what the linker
  took. A module archive counts if at least one member was extracted, the
  library's own objects always count, an extra component counts if one of its
  `archives` had a member extracted or one of its `objects` was an input. An
  extracted archive or a linked object that maps to nothing is a problem.

With --check the exit status is 1 when there is any problem: a module without
licence metadata, a missing licence text, a licence kind outside the policy,
an unacknowledged "by exception only" licence, an unmapped linked input, or a
placeholder in notices-extra.toml without a --var.

Paths in notices-extra.toml may use {name} placeholders, set with
--var name=path (sysroot, runtimes, rust_toolchain, rustlibs). The NOTICE file
shows them as <name>, so it holds no build machine paths.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blueprint as bp  # noqa: E402


class NoSelect(bp.SelectContext):
    def condition(self, func, args):
        return None


class Reader:
    """Android.bp licence metadata of the source tree, with every file read recorded."""

    def __init__(self, src):
        self.src = src
        self.cache = {}
        self.read = set()
        self.licenses = None

    def load(self, path):
        if path not in self.cache:
            try:
                mods, _ = bp.parse_file(path, NoSelect())
            except bp.BlueprintError as e:
                print(f"gen_notices: warning: cannot parse {path}: {e}", file=sys.stderr)
                mods = []
            self.cache[path] = mods
            self.read.add(path)
        return self.cache[path]

    def license_modules(self):
        """name -> (dir, kinds, texts) for every license module in the tree."""
        if self.licenses is None:
            self.licenses = {}
            for dirpath, dirnames, filenames in os.walk(self.src):
                dirnames[:] = sorted(x for x in dirnames if x not in (".cache", ".stamps"))
                if "Android.bp" not in filenames:
                    continue
                rel = os.path.relpath(dirpath, self.src)
                rel = "" if rel == "." else rel
                for mtype, props, _ in self.load(os.path.join(dirpath, "Android.bp")):
                    if mtype == "license" and props.get("name"):
                        self.licenses[props["name"]] = (rel, props.get("license_kinds", []),
                                                        props.get("license_text", []))
        return self.licenses

    def module_licenses(self, name, rel):
        """Licence module names that apply to module `name` defined in directory `rel`."""
        path = os.path.join(self.src, rel, "Android.bp")
        if os.path.exists(path):
            for _, props, _ in self.load(path):
                if props.get("name") == name and props.get("licenses"):
                    return list(props["licenses"])
        d = rel
        while True:
            path = os.path.join(self.src, d, "Android.bp")
            if os.path.exists(path):
                for mtype, props, _ in self.load(path):
                    if mtype == "package" and props.get("default_applicable_licenses"):
                        return list(props["default_applicable_licenses"])
            if not d:
                return []
            d = os.path.dirname(d)


def read_text(path):
    # A symlink whose target was not fetched is not a file.
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def expand(pattern, vars_, problems, where):
    """(absolute path or glob, display path) for a notices-extra.toml path."""
    missing = [v for v in PLACEHOLDER.findall(pattern) if v not in vars_]
    if missing:
        problems.append(f"{where}: {pattern} needs --var {missing[0]}=...")
        return None, None
    full = PLACEHOLDER.sub(lambda m: vars_[m.group(1)], pattern)
    shown = PLACEHOLDER.sub(lambda m: f"<{m.group(1)}>", pattern)
    return os.path.normpath(full), shown


def parse_why_extract(path, build_dir):
    """Archives with at least one extracted member (lld --why-extract)."""
    out = set()
    with open(path, encoding="utf-8") as f:
        next(f, None)  # header: reference, extracted, symbol
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            m = re.match(r"(.*)\((.*)\)$", parts[1])
            if m:
                out.add(os.path.realpath(os.path.join(build_dir, m.group(1))))
    return out


def parse_depfile(path, build_dir):
    """Input files of the link from its Make-style dependency file."""
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\\\n", " ")
    files = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        deps = line.split(":", 1)[1]  # "target: deps"; the phony "dep:" lines have none
        for tok in re.findall(r"(?:\\ |[^ ])+", deps):
            files.append(os.path.realpath(os.path.join(build_dir, tok.replace("\\ ", " "))))
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="fetched AOSP tree")
    ap.add_argument("--closure", required=True, help="cmake-gen/closure.json")
    ap.add_argument("--module", default="libandroid_runtime", help="the linked library's module")
    ap.add_argument("--rust-crates", help="rustlibs/crates.tsv (bp2rust)")
    ap.add_argument("--extra", required=True, action="append",
                    help="notices-extra.toml (repeatable; the tables are concatenated)")
    ap.add_argument("--policy", required=True)
    ap.add_argument("--var", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--archives", help="TSV: module, archive path, for the module archives on the link line")
    ap.add_argument("--own-objects", action="append", default=[], metavar="DIR",
                    help="directory of the library's own object files")
    ap.add_argument("--why-extract", help="lld --why-extract output of the link")
    ap.add_argument("--link-deps", help="dependency file of the link (optional even with --why-extract)")
    ap.add_argument("--build-dir", default=".", help="directory the link ran in")
    ap.add_argument("--notice", required=True, help="NOTICE file to write")
    ap.add_argument("--json", help="inventory to write (components, files, hashes, problems)")
    ap.add_argument("--depfile", help="Make-style dependency file of the NOTICE file")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    vars_ = {}
    for v in a.var:
        k, _, p = v.partition("=")
        if p:
            vars_[k] = os.path.abspath(p)
    problems = []
    read_files = {os.path.abspath(x) for x in (a.closure, a.policy, a.rust_crates, a.archives, *a.extra) if x}

    closure = json.load(open(a.closure))
    root = closure.get(a.module)
    if root is None:
        sys.exit(f"gen_notices: {a.module} is not in {a.closure}")
    link = root.get("link") or {}
    line_modules = [a.module] + list(link.get("static_libs", []))
    extra_cfg = {}
    for e in a.extra:
        for k, v in tomllib.load(open(e, "rb")).items():
            extra_cfg.setdefault(k, []).extend(v)
    policy = tomllib.load(open(a.policy, "rb"))
    allowed = set(policy.get("allowed_kinds", []))
    acked = {x["id"]: x["reason"] for x in policy.get("acknowledged", [])}

    # What the linker took, if we know it.
    linked_archives = None
    linked_objects = None
    if a.why_extract:
        bdir = os.path.abspath(a.build_dir)
        linked_archives = parse_why_extract(a.why_extract, bdir)
        read_files.add(os.path.abspath(a.why_extract))
        if a.link_deps and os.path.exists(a.link_deps):
            linked_objects = [p for p in parse_depfile(a.link_deps, bdir) if p.endswith(".o")]
            read_files.add(os.path.abspath(a.link_deps))
    archive_of = {}
    if a.archives:
        with open(a.archives, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mod, path = line.rstrip("\n").split("\t")
                    archive_of[mod] = os.path.realpath(path)
    elif linked_archives is not None:
        sys.exit("gen_notices: --why-extract needs --archives")

    # Modules to cover.
    modules = []
    skipped = []
    for name in line_modules:
        m = closure.get(name)
        if m is None:
            problems.append(f"{name}: on the link line but not in {os.path.basename(a.closure)}")
            continue
        if m.get("headers_only") or not m.get("srcs"):
            continue
        if linked_archives is not None and name != a.module:
            if name not in archive_of:
                problems.append(f"{name}: no archive path in {a.archives}")
                continue
            if archive_of[name] not in linked_archives:
                skipped.append(name)
                continue
        modules.append(name)

    rust_archive = vars_.get("rustlibs")
    rust_linked = bool(link.get("rust")) and (
        linked_archives is None or (rust_archive and os.path.realpath(rust_archive) in linked_archives))
    crates = []
    if rust_linked:
        if not a.rust_crates:
            problems.append(f"{a.module} links Rust modules, but no --rust-crates list was given")
        else:
            with open(a.rust_crates, encoding="utf-8") as f:
                rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]
            head = rows[0]
            for r in rows[1:]:
                row = dict(zip(head, r))
                if row.get("in_staticlib") == "yes":
                    crates.append(row)

    # AOSP components: one per licence module.
    rd = Reader(a.src)
    lic = rd.license_modules()
    comps = {}

    def attach(what, mod_name, rel, nsrcs):
        names = rd.module_licenses(mod_name, rel)
        if not names:
            problems.append(f"{what}: no licence metadata for {rel}")
            return
        for ln in names:
            ln = ln.split(":")[-1]
            if ln not in lic:
                problems.append(f"{what}: licence module {ln} not found (fetch the Android.bp that defines it)")
                continue
            ldir, kinds, texts = lic[ln]
            c = comps.setdefault(ln, {"id": ln, "dir": ldir, "kinds": list(kinds), "texts": list(texts),
                                      "modules": [], "sources_compiled": 0})
            c["modules"].append(what)
            c["sources_compiled"] += nsrcs

    for name in modules:
        m = closure[name]
        attach(name, name, m["dir"], m["srcs"])
    # Header libraries put inline code and templates into the objects of the
    # modules that include them. List every header-only module reachable from
    # the link line, but not ones only the host tools (aidl, aprotoc, ...)
    # use, which share closure.json when they are built in the same tree.
    reach = set()
    todo = [a.module] + list(line_modules)
    while todo:
        name = todo.pop()
        if name in reach or name not in closure:
            continue
        reach.add(name)
        m = closure[name]
        for k in ("header_libs", "whole_static_libs", "static_libs", "shared_libs"):
            todo.extend(m.get(k, []))
    for name, m in sorted(closure.items()):
        if name in reach and (m.get("headers_only") or not m.get("srcs")):
            attach(f"{name} (headers)", name, m["dir"], 0)
    for row in crates:
        attach(f"{row['module']} (Rust crate {row['crate']} {row['version']})".replace(" -)", ")"),
               row["module"], row["dir"], 0)

    supplements = {}
    for s in extra_cfg.get("supplement", []):
        supplements.setdefault(s["license"], []).append(s)

    entries = []
    for c in sorted(comps.values(), key=lambda c: (c["dir"], c["id"])):
        files = []
        paths = [os.path.join(c["dir"], t) for t in c["texts"]]
        for s in supplements.get(c["id"], []):
            paths += s["files"]
        for rel in paths:
            p = os.path.join(a.src, rel)
            body = read_text(p)
            if body is None:
                problems.append(f"{c['id']}: licence text {rel} is missing")
                continue
            read_files.add(os.path.abspath(p))
            files.append({"path": rel, "sha256": sha(body), "text": body})
        if not files:
            problems.append(f"{c['id']}: no licence text")
        for k in c["kinds"]:
            if k not in allowed and c["id"] not in acked:
                problems.append(f"{c['id']}: licence kind {k} is not in the policy's allowed_kinds")
        if any("exception" in k for k in c["kinds"]) and c["id"] not in acked:
            problems.append(f"{c['id']}: 'by exception only' licence needs an [[acknowledged]] entry in the policy")
        entries.append({"id": c["id"], "title": c["id"], "source": c["dir"], "licenses": c["kinds"], "covers": c["modules"],
                        "sources_compiled": c["sources_compiled"], "files": files,
                        "note": acked.get(c["id"])})

    # Extra components (toolchain and sysroot parts).
    matched_archives = set()
    matched_objects = set()
    for x in extra_cfg.get("component", []):
        where = x["id"]
        arch_pats = [p for p in (expand(q, vars_, problems, where)[0] for q in x.get("archives", [])) if p]
        obj_pats = [p for p in (expand(q, vars_, problems, where)[0] for q in x.get("objects", [])) if p]
        if linked_archives is not None:
            hits = {f for f in linked_archives if any(fnmatch.fnmatchcase(f, os.path.realpath(p)) or
                                                     fnmatch.fnmatchcase(f, p) for p in arch_pats)}
            ohits = set()
            if linked_objects is not None:
                ohits = {f for f in linked_objects if any(fnmatch.fnmatchcase(f, os.path.realpath(p)) or
                                                         fnmatch.fnmatchcase(f, p) for p in obj_pats)}
            matched_archives |= hits
            matched_objects |= ohits
            # Without the dependency file, components that contribute objects
            # directly are kept: their inclusion cannot be checked.
            # `headers = true`: header-only code compiled into the library's
            # own objects (no archive of its own); listed whenever configured.
            used = hits or ohits or (linked_objects is None and obj_pats) or x.get("headers")
            if not used:
                skipped.append(x["id"])
                continue
        files = []
        for t in x.get("files", []):
            full, shown = expand(t, vars_, problems, where)
            if full is None:
                continue
            body = read_text(full)
            if body is None:
                problems.append(f"{where}: licence text {shown} not found")
                continue
            read_files.add(full)
            files.append({"path": shown, "sha256": sha(body), "text": body})
        if not files:
            problems.append(f"{where}: no licence text")
        entries.append({"id": x["id"], "title": x["name"], "source": x.get("origin", ""), "licenses": x.get("spdx", []),
                        "covers": [x.get("what", "")], "sources_compiled": 0, "files": files,
                        "note": x.get("note")})

    # Every linked input must be covered.
    if linked_archives is not None:
        known = set(archive_of.values()) | matched_archives
        if rust_archive:
            known.add(os.path.realpath(rust_archive))
        for f in sorted(linked_archives - known):
            problems.append(f"linked archive {f} has no licence entry (add it to config/notices-extra.toml)")
        if linked_objects is not None:
            own = [os.path.realpath(d) + os.sep for d in a.own_objects]
            for f in sorted(set(linked_objects)):
                if f in matched_objects or any(f.startswith(d) for d in own):
                    continue
                problems.append(f"linked object {f} has no licence entry (add it to config/notices-extra.toml)")

    # Attribution sentences of the components that are in.
    ids = {e["id"] for e in entries}
    extra_ids = {x["id"] for x in extra_cfg.get("component", [])}
    attributions = []
    for x in extra_cfg.get("attribution", []):
        if x["license"] in ids:
            attributions.append(x["text"])
        elif x["license"] not in lic and x["license"] not in extra_ids:
            problems.append(f"attribution for unknown licence {x['license']}")

    # NOTICE: summary of components, then each distinct text once.
    out = []
    w = out.append
    w(f"Notices for {a.module}.so\n\n")
    w("This library is built from the Android Open Source Project and the other\n"
      "software listed below. Each entry names a component, the licences that apply\n"
      "to it (SPDX identifiers or AOSP licence kinds), what it covers and the files\n"
      "whose text follows in the second part. Identical texts are printed once.\n\n")
    if attributions:
        for t in attributions:
            w(t.strip() + "\n")
        w("\n")
    first = {}
    for e in entries:
        w("=" * 78 + "\n")
        w(f"{e['title']}\n")
        if e["source"]:
            w(f"  source:   {e['source']}\n")
        w(f"  licences: {', '.join(e['licenses']) or 'see text'}\n")
        w(f"  covers:   {', '.join(e['covers'])}\n")
        if e["note"]:
            w("  note:     " + " ".join(e["note"].split()) + "\n")
        for fl in e["files"]:
            if fl["sha256"] in first:
                w(f"  text:     {fl['path']} (same as {first[fl['sha256']]})\n")
            else:
                first[fl["sha256"]] = fl["path"]
                w(f"  text:     {fl['path']}\n")
        w("\n")
    w("=" * 78 + "\nLicence texts\n" + "=" * 78 + "\n\n")
    done = set()
    for e in entries:
        for fl in e["files"]:
            if first.get(fl["sha256"]) == fl["path"] and fl["sha256"] not in done:
                done.add(fl["sha256"])
                w("-" * 78 + f"\n{fl['path']}\n" + "-" * 78 + "\n")
                w(fl["text"].rstrip() + "\n\n")
    os.makedirs(os.path.dirname(os.path.abspath(a.notice)), exist_ok=True)
    with open(a.notice + ".tmp", "w", encoding="utf-8") as f:
        f.write("".join(out))
    os.replace(a.notice + ".tmp", a.notice)

    if a.json:
        inv = {"module": a.module,
               "mode": "link" if linked_archives is not None else "link-line",
               "components": [{k: (v if k != "files" else [{"path": x["path"], "sha256": x["sha256"]} for x in v])
                               for k, v in e.items()} for e in entries],
               "not_linked": sorted(skipped),
               "problems": problems}
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(inv, f, indent=1)
            f.write("\n")
    if a.depfile:
        deps = sorted(read_files | {os.path.abspath(p) for p in rd.read})
        with open(a.depfile, "w", encoding="utf-8") as f:
            f.write(a.notice.replace(" ", "\\ ") + ": \\\n")
            f.write(" \\\n".join("  " + d.replace(" ", "\\ ") for d in deps) + "\n")

    mode = "linked inputs" if linked_archives is not None else "link line"
    print(f"gen_notices: {a.module} ({mode}): {len(entries)} components, {len(first)} distinct texts, "
          f"{len(skipped)} on the link line but not linked, {len(problems)} problems -> {a.notice}", flush=True)
    for p in problems:
        print(f"gen_notices: problem: {p}", file=sys.stderr)
    if a.check and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
