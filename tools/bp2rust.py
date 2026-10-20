#!/usr/bin/env python3
"""Generate rustc invocations (a Ninja file) for the Rust part of a Soong
closure, from the Android.bp files, the way Soong's rust rules run rustc.

Reads rust/rustlibs.toml (roots and pruned dependencies), resolves the
host linux_glibc arm64 (or --arch x86_64) variant of every rust_library, rust_library_host,
rust_ffi_static and rust_proc_macro module reached from the roots through
`rustlibs` and `proc_macros` (with bp2cmake's Soong resolver: defaults,
target/arch blocks, select()), and writes into --out:

  build.ninja          rlibs, proc macros, librustlibs.a, cxx bridge code
  rustlibs-vars.cmake  outputs and interface data for rust/rustlibs.cmake
  crates.tsv           the crates built, with versions, editions, features

The Ninja file must be run with the AOSP source root as the working
directory (`ninja -C src -f OUT/build.ninja`), because Soong runs rustc from
the root with relative paths and `-Z remap-cwd-prefix=.`; that is what puts
`external/rust/...` file names into panic locations. All outputs, the Ninja
log and the deps log go to --out; nothing is written under src/.

Flag sources (build/soong at the pin):
  rust/config/global.go     GlobalRustFlags, RustDefaultVersion
  rust/config/lints.go      lints by directory
  rust/compiler.go          compilerFlags, cfgFlags, featureFlags, edition
  rust/library.go           -C metadata, cfgs (passed twice for libraries)
  rust/proc_macro.go        --extern proc_macro, -C metadata
  rust/builder.go           transformSrctoCrate, rustEnvVars,
                            TransformRlibstoStaticlib
  cc/builder.go             GenerateRustStaticlib (the librustlibs.rs stub)

Usage:
  tools/bp2rust.py --out DIR --rustc PATH --cxxbridge PATH [--host-cc clang]
                   [--arch arm64|x86_64] [--explain MODULE]

Proc macros, and the crates they depend on, are built for the build machine
(they are loaded by rustc); everything else for --arch. In a native build
both are the same triple.
"""

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bp2cmake  # noqa: E402  (Soong module index and variant resolver)

ROOT = bp2cmake.ROOT
SRC = bp2cmake.SRC

RUST_DEFAULT_VERSION = "1.83.0"  # rust/config/global.go RustDefaultVersion
DEFAULT_EDITION = "2021"         # rust/config/global.go DefaultEdition
# Soong's linux_glibc x86_64 triple is x86_64-unknown-linux-gnu.
RUST_TRIPLES = {"arm64": "aarch64-unknown-linux-gnu", "x86_64": "x86_64-unknown-linux-gnu"}
HOST_TRIPLE = {"aarch64": RUST_TRIPLES["arm64"], "x86_64": RUST_TRIPLES["x86_64"]}.get(platform.machine())

# rust/config/global.go GlobalRustFlags. The toolchain adds nothing for
# linux_glibc (LinuxRustFlags is empty).
GLOBAL_RUST_FLAGS = [
    "-Z unstable-options",
    "-Z stack-protector=strong",
    "-Z remap-cwd-prefix=.",
    "-C debuginfo=2",
    "-C opt-level=3",
    "-C relocation-model=pic",
    "-C overflow-checks=on",
    "-C force-unwind-tables=yes",
    "-C symbol-mangling-version=v0",
    "--color=always",
    "-Z dylib-lto",
    "-Z link-native-libraries=no",
    "--cfg soong",
]

# rust/config/lints.go
RUSTC_DEFAULT_LINTS = "-A deprecated -A unknown_lints -D missing-docs -D warnings -D unsafe_op_in_unsafe_fn"
RUSTC_VENDOR_LINTS = "-A deprecated -D warnings"
RUSTC_ALLOW_ALL = "--cap-lints allow"
LINT_SETS = {"android": RUSTC_DEFAULT_LINTS, "vendor": RUSTC_VENDOR_LINTS, "none": RUSTC_ALLOW_ALL}
LINT_SET_FOR_PATH = [("external", "none"), ("hardware", "vendor"), ("prebuilts", "none"),
                     ("vendor/google", "android"), ("vendor", "vendor")]

RLIB_TYPES = {"rust_library", "rust_library_host", "rust_ffi_static", "rust_library_rlib",
              "rust_library_host_rlib", "rust_ffi_host_static"}
PROC_MACRO_TYPES = {"rust_proc_macro"}
HOST_ONLY = {"rust_library_host", "rust_library_host_rlib", "rust_ffi_host_static", "rust_proc_macro"}


class Error(Exception):
    pass


def rustc_lints(mdir, prop):
    if prop is not None:
        if prop in LINT_SETS:
            return LINT_SETS[prop]
        if prop != "default":
            raise Error(f"{mdir}: unknown lints value {prop}")
    for prefix, s in LINT_SET_FOR_PATH:
        if mdir.startswith(prefix):
            return LINT_SETS[s]
    return RUSTC_DEFAULT_LINTS


def third_party(mdir):
    # android.IsThirdPartyPath, as used by transformSrctoCrate for -Zallow-features.
    if mdir.startswith(("external/", "vendor/")):
        return True
    if mdir.startswith("hardware/"):
        return not mdir.startswith(("hardware/interfaces", "hardware/libhardware",
                                    "hardware/google", "hardware/ril"))
    return False


class Crate:
    def __init__(self, name, mtype, props, mdir):
        self.module = name
        self.type = mtype
        self.props = props
        self.dir = mdir
        self.crate_name = props["crate_name"]
        self.proc_macro = mtype in PROC_MACRO_TYPES
        root = props.get("crate_root") or (props.get("srcs") or [None])[0]
        if not root:
            raise Error(f"{name}: no crate_root or srcs")
        self.root = os.path.normpath(os.path.join(mdir, root))
        self.edition = props.get("edition", DEFAULT_EDITION)
        self.features = props.get("features", [])
        self.cfgs = props.get("cfgs", [])
        self.version = props.get("cargo_pkg_version", "")
        self.rustlibs = []
        self.proc_macros = []
        self.cc_deps = []
        self.triple = None  # set by Closure.build()
        ext = "so" if self.proc_macro else "rlib"
        self.out = f"$odir/crates/{name}.{ext}"

    # rust/builder.go rustEnvVars
    def env(self):
        env = ["OUT_DIR=out", f"ANDROID_RUST_VERSION={RUST_DEFAULT_VERSION}"]
        if self.props.get("cargo_env_compat"):
            env += [f"CARGO_CRATE_NAME={self.crate_name}", f"CARGO_PKG_NAME={self.crate_name}"]
            v = self.version
            if v:
                env.append(f"CARGO_PKG_VERSION={v}")
                if v.count(".") == 2:
                    a, b, c = v.split(".")
                    env += [f"CARGO_PKG_VERSION_MAJOR={a}", f"CARGO_PKG_VERSION_MINOR={b}",
                            f"CARGO_PKG_VERSION_PATCH={c}"]
        return env

    # rust.go: compilerFlags, then cfgFlags, then featureFlags; then
    # builder.go transformSrctoCrate appends crate type, name and target.
    def rustc_flags(self):
        f = list(GLOBAL_RUST_FLAGS)
        f.append(rustc_lints(self.dir, self.props.get("lints")))
        f += self.props.get("flags", [])
        f.append(f"--edition={self.edition}")
        if self.proc_macro:
            f.append("--extern proc_macro")
        f.append(f"-C metadata={self.module}")
        cfgs = [f"--cfg '{c}'" for c in self.cfgs]
        f += cfgs
        if not self.proc_macro:
            f += cfgs  # library.go cfgFlags appends the module cfgs a second time
        f += [f"--cfg 'feature=\"{x}\"'" for x in self.features]
        f.append("--crate-type=" + ("proc-macro" if self.proc_macro else "rlib"))
        f.append(f"--crate-name={self.crate_name}")
        f.append(f"--target={self.triple}")
        # --sysroot=/dev/null dropped: std comes from rust/toolchain's sysroot.
        f.append("-C codegen-units=1")
        if not third_party(self.dir):
            f.append("-Zallow-features=\"\"")
        return f


class Closure:
    def __init__(self, conf, arch=None):
        self.conf = conf
        self.cfg = bp2cmake.Config(arch)
        self.target_triple = RUST_TRIPLES[self.cfg.arch]
        self.index = bp2cmake.Index(self.cfg)
        self.res = bp2cmake.Resolver(self.cfg, self.index)
        self.crates = {}
        self.order = []
        self.prune = conf.get("prune", {})

    def resolve(self, name):
        m = self.index.get(name)
        if m is None:
            raise Error(f"module {name} not found (is its project in config/projects.toml?)")
        mtype, props = self.res.resolve(name)
        return m, mtype, props

    def visit(self, name, stack=()):
        if name in self.crates:
            return self.crates[name]
        if name in stack:
            raise Error(f"dependency cycle: {' -> '.join(stack + (name,))}")
        m, mtype, props = self.resolve(name)
        if mtype not in RLIB_TYPES | PROC_MACRO_TYPES:
            raise Error(f"{name} ({m.where()}): unsupported module type {mtype}")
        if mtype not in HOST_ONLY and not props.get("host_supported"):
            raise Error(f"{name} ({m.where()}): not host_supported")
        if props.get("enabled") is False:
            raise Error(f"{name} ({m.where()}): disabled on host")
        c = Crate(name, mtype, props, m.dir)
        c.bp = m.where()
        pr = self.prune.get(name, {})
        c.pruned = {k: v for k, v in pr.items() if k != "reason"}
        for k, v in c.pruned.items():
            missing = [d for d in v if d not in props.get(k, [])]
            if missing:
                raise Error(f"rustlibs.toml prunes {missing} from {name}.{k}, but Android.bp does not list them")
        self.crates[name] = c
        for dep in props.get("rustlibs", []):
            if dep not in pr.get("rustlibs", []):
                c.rustlibs.append(self.visit(dep, stack + (name,)))
        for dep in props.get("proc_macros", []):
            if dep not in pr.get("proc_macros", []):
                c.proc_macros.append(self.visit(dep, stack + (name,)))
        for k in ("whole_static_libs", "static_libs"):
            for dep in props.get(k, []):
                if dep not in pr.get(k, []):
                    c.cc_deps.append(dep)
        self.order.append(c)  # post-order: dependencies first
        return c

    def build(self):
        for r in self.conf["staticlib"]["roots"]:
            self.visit(r)
        # Rlibs in the staticlib (Soong: RustRlibDeps of the cc module, i.e.
        # every rlib reached through rlibs, not through proc macros).
        self.staticlib_crates = []
        seen = set()

        def walk(c):
            if c.module in seen or c.proc_macro:
                return
            seen.add(c.module)
            self.staticlib_crates.append(c)
            for d in c.rustlibs:
                walk(d)

        for r in self.conf["staticlib"]["roots"]:
            walk(self.crates[r])

        # Proc macros and everything they use run inside rustc on the build
        # machine; the rest is target code.
        host = set()

        def walk_host(c):
            if c.module in host:
                return
            host.add(c.module)
            for d in c.rustlibs + c.proc_macros:
                walk_host(d)

        for c in self.order:
            if c.proc_macro:
                walk_host(c)
        target = {c.module for c in self.order if c.module not in host}
        for c in self.order:
            if c.module in host:
                if not HOST_TRIPLE:
                    raise Error(f"no Rust triple for build machine {platform.machine()}")
                c.triple = HOST_TRIPLE
            else:
                c.triple = self.target_triple
        both = {c.module for c in self.order if c.module in host and any(
            c in t.rustlibs for t in self.order if t.module in target)}
        if both and HOST_TRIPLE != self.target_triple:
            raise Error(f"crates needed both by proc macros and by target code: {sorted(both)} "
                        "(a cross build would have to compile them twice)")

    def cxxbridge_genrules(self):
        """Genrules running cxxbridge that the C++ halves of the live crates
        (their whole_static_libs/static_libs) use."""
        out = []
        cc = []
        for c in self.order:
            for d in c.cc_deps:
                if d not in cc:
                    cc.append(d)
        self.cc_deps = cc
        for d in cc:
            _, _, props = self.resolve(d)
            for g in props.get("generated_headers", []) + props.get("generated_sources", []):
                gm, gtype, gprops = self.resolve(g)
                if gtype != "genrule" or "cxxbridge" not in gprops.get("tools", []):
                    raise Error(f"{d}: generated {g} is not a cxxbridge genrule")
                if g not in [x[0] for x in out]:
                    out.append((g, gm, gprops))
        return out


def check_versions(crates):
    """Android.bp cargo_pkg_version against the crate's Cargo.toml and
    against external/rust/android-crates-io/pseudo_crate/Cargo.lock."""
    lockp = os.path.join(SRC, "external/rust/android-crates-io/pseudo_crate/Cargo.lock")
    with open(lockp, "rb") as f:
        lock = tomllib.load(f)
    locked = {}
    for p in lock.get("package", []):
        locked.setdefault(p["name"], set()).add(p["version"])
    report = []
    for c in crates:
        tomlp = os.path.join(SRC, c.dir, "Cargo.toml")
        if not c.version:
            if os.path.exists(tomlp):
                with open(tomlp, "rb") as f:
                    v = tomllib.load(f).get("package", {}).get("version", "-")
                report.append((c, v, "no cargo_pkg_version; version from Cargo.toml"))
            else:
                report.append((c, "-", "first-party, no Cargo.toml"))
            continue
        pkg = None
        if os.path.exists(tomlp):
            with open(tomlp, "rb") as f:
                pkg = tomllib.load(f).get("package", {})
            if pkg.get("version") != c.version:
                raise Error(f"{c.module}: Android.bp says {c.version}, {tomlp} says {pkg.get('version')}")
        name = (pkg or {}).get("name") or os.path.basename(c.dir)
        if c.dir.startswith("external/rust/android-crates-io/"):
            if c.version not in locked.get(name, set()):
                raise Error(f"{c.module}: {name} {c.version} not in pseudo_crate/Cargo.lock "
                            f"(has {sorted(locked.get(name, []))})")
            report.append((c, c.version, f"{name}: Android.bp, Cargo.toml and pseudo_crate/Cargo.lock agree"))
        else:
            report.append((c, c.version, "Android.bp and Cargo.toml agree"))
    return report


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return
    with open(path + ".tmp", "w") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def ninja_escape(s):
    return s.replace("$", "$$").replace(":", "$:").replace(" ", "$ ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=os.path.join(ROOT, "rust", "rustlibs.toml"))
    ap.add_argument("--rustc", required=True)
    ap.add_argument("--cxxbridge", required=True)
    ap.add_argument("--host-cc", default="clang", help="linker driver for proc macros (host .so)")
    ap.add_argument("--arch", choices=sorted(RUST_TRIPLES), help="default: config/aosp.toml [variant] arch")
    ap.add_argument("--explain", action="append", default=[])
    args = ap.parse_args()

    with open(args.config, "rb") as f:
        conf = tomllib.load(f)
    out = os.path.abspath(args.out)
    rustc = os.path.abspath(args.rustc)
    cxxbridge = os.path.abspath(args.cxxbridge)

    try:
        cl = Closure(conf, args.arch)
        cl.build()
        genrules = cl.cxxbridge_genrules()
        versions = check_versions(cl.order)
    except (Error, bp2cmake.GenError) as e:
        sys.exit(f"bp2rust: error: {e}")

    vv = subprocess.run([rustc, "-vV"], capture_output=True, text=True, check=True).stdout
    if f"release: {RUST_DEFAULT_VERSION}" not in vv:
        sys.exit(f"bp2rust: error: {rustc} is not rustc {RUST_DEFAULT_VERSION} (RustDefaultVersion)")
    # The C++ half of every bridge must come from the same cxx release as
    # the Rust half (the cxxbridge_macro proc macro). Checked at build time,
    # because cxxbridge may itself be built by the same build.
    want = cl.crates["libcxxbridge_macro"].version if "libcxxbridge_macro" in cl.crates else ""

    os.makedirs(out, exist_ok=True)
    meta = conf["staticlib"]
    lines = [
        "# Generated by tools/bp2rust.py. Run as: ninja -C <src> -f <this file>",
        "ninja_required_version = 1.10",
        f"builddir = {ninja_escape(out)}",
        f"odir = {ninja_escape(out)}",
        f"rustc = {rustc}",
        f"cxxbridge = {cxxbridge}",
        "",
        "rule rustc",
        "  command = env RUSTC_BOOTSTRAP=1 $env $rustc --emit link -o $out "
        "--emit dep-info=$out.d.raw $in $libflags $flags && grep ^$out: $out.d.raw > $out.d",
        "  depfile = $out.d",
        "  deps = gcc",
        "  description = rustc $in",
        "",
        "rule cxxbridge_check",
        "  command = v=$$($cxxbridge --version) && [ \"$$v\" = \"cxxbridge $want\" ] && echo \"$$v\" > $out "
        "|| { echo \"$cxxbridge is '$$v', need cxxbridge $want\" >&2; exit 1; }",
        "  description = check cxxbridge version",
        "",
        f"want = {want}",
        "build $odir/cxxbridge.version: cxxbridge_check | $cxxbridge",
        "",
        "rule genrule",
        "  command = $cmd",
        "  description = genrule $name",
        "",
    ]
    proc_link = [f"-C linker={args.host_cc}", "-C link-arg=-fuse-ld=lld"]

    def crate_build(c):
        libflags = []
        implicit = []
        for d in c.rustlibs + c.proc_macros:
            libflags.append(f"--extern {d.crate_name}={d.out}")
            implicit.append(d.out)
        libflags.append("-L dependency=$odir/crates")
        flags = c.rustc_flags() + (proc_link if c.proc_macro else [])
        o = c.out
        return [
            f"build {o}: rustc {ninja_escape(c.root)} | {' '.join(implicit)} $rustc",
                        f"  env = {' '.join(shlex.quote(e) for e in c.env())}",
            f"  libflags = {' '.join(libflags)}",
            f"  flags = {' '.join(flags).replace('$', '$$')}",
            "",
        ]

    for c in cl.order:
        lines += crate_build(c)
        if c.module in args.explain:
            print(json.dumps({"module": c.module, "bp": c.bp, "type": c.type, "root": c.root,
                              "env": c.env(), "flags": c.rustc_flags(),
                              "rustlibs": [d.module for d in c.rustlibs],
                              "proc_macros": [d.module for d in c.proc_macros],
                              "cc_deps": c.cc_deps, "pruned": c.pruned}, indent=1))

    # cc/builder.go genRustStaticlibSrcFile, rust/builder.go TransformRlibstoStaticlib.
    names = []
    for c in cl.staticlib_crates:
        if c.crate_name not in names:
            names.append(c.crate_name)
    stub = "\n".join(["// @Soong generated Source", "#![no_std]"] + [f"extern crate {n};" for n in names])
    stub_path = "$odir/librustlibs.rs"
    write_if_changed(os.path.join(out, "librustlibs.rs"), stub)
    sflags = list(GLOBAL_RUST_FLAGS) + [f"-C metadata={meta['for_module']}", "-C lto=thin",
                                        "--crate-type=staticlib", "--crate-name=generated_rust_staticlib",
                                        f"--target={cl.target_triple}", "-C codegen-units=1"]
    if not third_party(meta["for_module_dir"]):
        sflags.append("-Zallow-features=\"\"")
    slib = "$odir/librustlibs.a"
    lines += [
        f"build {slib}: rustc {stub_path} | {' '.join(c.out for c in cl.staticlib_crates)} $rustc",
                f"  env = OUT_DIR=out ANDROID_RUST_VERSION={RUST_DEFAULT_VERSION}",
        "  libflags = " + " ".join(f"--extern {c.crate_name}={c.out}" for c in cl.staticlib_crates)
        + " -L dependency=$odir/crates",
        f"  flags = {' '.join(sflags).replace('$', '$$')}",
        "",
    ]

    # cxxbridge genrules (Soong genrule: cmd run from the source root).
    gen_outs, gen_srcs, gen_incs = [], [], []
    for g, gm, gp in genrules:
        gdir = f"$odir/gen/{g}"
        ins = [os.path.normpath(os.path.join(gm.dir, s)) for s in gp.get("srcs", [])]
        outs = [f"{gdir}/{o}" for o in gp["out"]]
        cmd = gp["cmd"]
        cmd = cmd.replace("$(location cxxbridge)", "$cxxbridge").replace("$(location)", "$cxxbridge")
        cmd = cmd.replace("$(in)", " ".join(ins)).replace("$(out)", " ".join(outs))
        cmd = cmd.replace("$(genDir)", gdir)
        mk = " && ".join(f"mkdir -p {os.path.dirname(o)} && rm -f {o}" for o in outs)
        lines += [f"build {' '.join(outs)}: genrule {' '.join(ins)} | $cxxbridge $odir/cxxbridge.version",
                  f"  name = {g}",
                  f"  cmd = {mk} && {cmd}",
                  ""]
        gen_outs += outs
        if g in sum((cl.resolve(d)[2].get("generated_headers", []) for d in cl.cc_deps), []):
            if gdir not in gen_incs:
                gen_incs.append(gdir)
        else:
            gen_srcs += outs
    lines += [f"build all: phony {slib} {' '.join(gen_outs)}", "default all", ""]

    with open(os.path.join(out, "build.ninja.tmp"), "w") as f:
        f.write("\n".join(lines))
    os.replace(os.path.join(out, "build.ninja.tmp"), os.path.join(out, "build.ninja"))

    def cm(paths):
        return " ".join(f'"{p.replace("$odir", out)}"' for p in paths)

    bps = sorted({os.path.join(SRC, c.bp.rsplit(":", 1)[0]) for c in cl.order}
                 | {os.path.join(SRC, gm.dir, "Android.bp") for _, gm, _ in genrules})
    with open(os.path.join(out, "rustlibs-vars.cmake"), "w") as f:
        f.write("# Generated by tools/bp2rust.py\n")
        f.write(f'set(RUSTLIBS_ARCHIVE "{out}/librustlibs.a")\n')
        f.write(f"set(RUSTLIBS_GEN_INCLUDE_DIRS {cm(gen_incs)})\n")
        f.write(f"set(RUSTLIBS_GEN_SOURCES {cm(gen_srcs)})\n")
        f.write(f"set(RUSTLIBS_GEN_OUTPUTS {cm(gen_outs)})\n")
        f.write(f"set(RUSTLIBS_CC_DEPS {' '.join(cl.cc_deps)})\n")
        f.write(f"set(RUSTLIBS_CRATES {' '.join(c.module for c in cl.order)})\n")
        f.write(f"set(RUSTLIBS_CONFIGURE_DEPENDS {cm(bps + [os.path.abspath(args.config)])})\n")

    with open(os.path.join(out, "crates.tsv"), "w") as f:
        f.write("module\tcrate\tversion\tedition\tkind\tin_staticlib\tdir\tfeatures\tcfgs\tversion_check\n")
        insl = {c.module for c in cl.staticlib_crates}
        for c, ver, note in versions:
            f.write("\t".join([c.module, c.crate_name, ver, c.edition,
                               "proc-macro" if c.proc_macro else "rlib", "yes" if c.module in insl else "no",
                               c.dir, ",".join(c.features), ",".join(c.cfgs), note]) + "\n")
    print(f"bp2rust: {cl.target_triple}: {len(cl.order)} crates ({len(cl.staticlib_crates)} in librustlibs.a), "
          f"{len(genrules)} cxxbridge genrules, C++ deps: {' '.join(cl.cc_deps)}")


if __name__ == "__main__":
    main()
