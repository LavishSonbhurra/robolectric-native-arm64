"""Generated crates of the Rust closure, for tools/bp2rust.py.

Android 17's Rust closure has crates whose source is written at build time:

  rust_bindgen          bindgen over a C or C++ header (rust/bindgen.go)
  rust_aconfig_library  aconfig create-rust-lib (aconfig/codegen/rust_aconfig_library.go)
  AIDL Rust backend     aidl --lang=rust plus aidl_rust_glue.py
                        (system/tools/aidl/build/aidl_rust_source_provider.go)

Each one becomes a Ninja step that writes the crate root under
$odir/gen/<module>/. The crate itself then goes through the same rustc rule as
any other. A rust_library may also name a generated module in `srcs` and read
it from OUT_DIR (libbinder_ndk_sys does).
"""

import os
import shlex

import bp2cmake
import generators
import soong_flags
import target

SRC = target.SRC

# rust/bindgen.go defaultBindgenFlags.
DEFAULT_BINDGEN_FLAGS = ["--blocklist-type", "max_align_t"]


class Step:
    def __init__(self, outputs, rule_lines):
        self.outputs = outputs
        self.rule_lines = rule_lines


class Module:
    """What Closure.resolve() returns for a synthetic AIDL Rust module."""

    def __init__(self, name, mdir, bp):
        self.name = name
        self.dir = mdir
        self.bp = bp

    def where(self):
        return self.bp


class RustGen:
    def __init__(self, closure, args):
        self.closure = closure
        self.args = args
        self.cfg = closure.cfg
        bdir = os.path.abspath(args.binary_dir)
        self.cfg.vars = {"binary_dir": bdir, "cmake": "cmake", "protoc": "protoc", "bison": "bison",
                         "flex": "flex", "yasm": "yasm"}
        self.gen = bp2cmake.Generator(self.cfg, os.path.join(bdir, "rustlibs"))
        self.gen.gen_root_abs = os.path.join(bdir, "gen")
        self.gen.bin_dir = os.path.join(bdir, "bin")
        self.gen.lib_dir = os.path.join(bdir, "lib")
        self.gen.roots = []
        self.gen.builtin_include = None
        self.steps = []
        self.cc_gen_deps = []

    # ----- AIDL Rust modules ------------------------------------------------

    def is_aidl_rust(self, name):
        return name.endswith("-rust") and name[:-len("-rust")] in self.gen.aidl_ifaces

    def aidl_module(self, name):
        it = self.gen.aidl_ifaces[name[:-len("-rust")]]
        # aidl_rust_source_provider.go SourceProviderDeps.
        props = {"crate_name": it.name.replace("-", "_").replace(".", "_"), "host_supported": True,
                 "rustlibs": ["libbinder_rs", "libstatic_assertions", "libzerocopy"],
                 "proc_macros": ["libasync_trait"], "features": ["std"]}
        return Module(name, it.dir, f"aidl_interface {it.name}"), "aidl_rust", props

    # ----- per crate --------------------------------------------------------

    def setup(self, c):
        if c.type == "rust_bindgen":
            self.bindgen(c)
        elif c.type == "rust_aconfig_library":
            self.aconfig(c)
        elif c.type == "aidl_rust":
            self.aidl(c)
            c.out = f"$odir/crates/lib{c.crate_name}.rlib"  # rustc wants lib*.rlib
        if c.gen:
            # rust/source_provider.go: no lints on generated code.
            c.props["lints"] = "none"
        for s in c.props.get("srcs", []):
            if s.startswith(":"):
                self.source_module(c, s[1:])

    def source_module(self, c, name):
        """A `srcs: [":module"]` entry: the crate includes the file through
        OUT_DIR, so it only has to exist and OUT_DIR has to point at it."""
        m, mtype, props = self.closure.resolve(name)
        if mtype == "genrule" and props.get("cmd") == "cp $(in) $(genDir)":
            # cargo_embargo's copy of checked-in build script output.
            # Absolute: include! resolves a relative path from the source file.
            c.out_dir = os.path.dirname(os.path.normpath(os.path.join(SRC, m.dir, props["srcs"][0])))
            return
        if mtype not in ("rust_bindgen",):
            raise ValueError(f"{c.module}: source module {name} has unsupported type {mtype}")
        dep = self.closure.crate_class(name, mtype, props, m.dir)
        self.setup(dep)
        c.gen_srcs.append(dep.gen)
        c.out_dir = os.path.dirname(dep.gen.outputs[0])

    def gdir(self, c):
        return f"$odir/gen/{c.module}"

    def bindgen(self, c):
        p = c.props
        stem = p.get("source_stem", c.module)
        out = f"{self.gdir(c)}/{stem}.rs"
        c.root = out
        wrapper = os.path.normpath(os.path.join(c.dir, p["wrapper_src"]))
        cflags = list(soong_flags.COMMON_GLOBAL_CFLAGS) + soong_flags.debug_flags()
        tc = soong_flags.toolchain(self.cfg.arch)
        cflags += ["-target", tc["triple"]]
        cflags += soong_flags.LINUX_CFLAGS + tc["cflags"] + tc["toolchain_cflags"]
        cflags += shlex.split(self.args.bindgen_cflags or "")
        inc = []
        sysinc = []
        for k in ("static_libs", "shared_libs", "header_libs"):
            for lib in p.get(k, []):
                if lib in bp2cmake.SKIP_SHARED:
                    continue
                i, si, g = self.gen.exports(lib)
                inc += i
                sysinc += si
                self.cc_gen_deps += g
        cflags += ["-I" + d for d in bp2cmake._uniq(inc)]
        for d in bp2cmake._uniq(sysinc):
            cflags += ["-isystem", d]
        cflags += soong_flags.shell_args(list(p.get("cflags", [])))
        cflags += ["-I" + os.path.normpath(os.path.join(SRC, c.dir, d)) for d in p.get("local_include_dirs", [])]
        cpp = wrapper.endswith((".hpp", ".hh")) or p.get("cpp_std") is not None
        if cpp:
            cflags.append("-std=" + (p.get("cpp_std") or soong_flags.CPP_STD))
            cflags += ["-x", "c++"]
            cflags += soong_flags.shell_args(list(p.get("cppflags", [])))
            cflags += soong_flags.STL_CPPFLAGS
        else:
            cflags.append("-std=" + (p.get("c_std") or soong_flags.C_STD))
            cflags += ["-x", "c"]
        cflags += ["-Wno-unused-command-line-argument", "-Wno-unknown-warning-option",
                   "-Wno-pragma-once-outside-header"]
        # The compiler is ours, not the one bindgen's cflags were written for.
        cflags += ["-Wno-everything"]
        flags = DEFAULT_BINDGEN_FLAGS + ["--rust-target", self.closure.rust_version, "--formatter", "none"]
        flags += list(p.get("bindgen_flags", []))
        ffiles = [os.path.normpath(os.path.join(c.dir, f)) for f in p.get("bindgen_flag_files", [])]
        cmd = ["mkdir -p", shlex.quote(self.gdir(c)).replace("'", ""), "&&",
               f"LIBCLANG_PATH={self.args.libclang_dir}", self.args.bindgen]
        cmd += [shlex.quote(f) for f in flags]
        if ffiles:
            cmd.append("$$(cat " + " ".join(ffiles) + ")")
        cmd += [wrapper, "-o", out, "--"]
        cmd += [shlex.quote(f) for f in soong_flags.absolutize(cflags, SRC)]
        c.gen = Step([out], [f"build {out}: genrule {wrapper} {' '.join(ffiles)}",
                             f"  name = bindgen_{c.module}",
                             "  cmd = " + " ".join(cmd).replace("$$(", "\0").replace("$", "$$").replace("\0", "$$(")
                             .replace("$$odir", "$odir"),
                             ""])
        self.steps.append(c.gen)

    def aconfig(self, c):
        p = c.props
        decl = p["aconfig_declarations"]
        dm = self.gen.index.get(decl)
        _, dprops = self.gen.res.resolve(decl)
        package = dprops["package"]
        decls = bp2cmake.expand_globs(dm.dir, dprops.get("srcs", []), [], decl)
        values = generators.aconfig_value_files(self.gen, package)
        rel = self.cfg.release
        d = self.gdir(c)
        cache = f"{d}/intermediate.pb"
        out = f"{d}/src/lib.rs"
        c.root = out
        tool = self.args.aconfig
        cmd = [tool, "create-cache", "--package", package]
        if dprops.get("container"):
            cmd += ["--container", dprops["container"]]
        for f in decls:
            cmd += ["--declarations", f]
        for f in values:
            cmd += ["--values", f]
        perm = rel.flag("RELEASE_ACONFIG_FLAG_DEFAULT_PERMISSION") or ""
        if perm:
            cmd += ["--default-permission", perm]
        ro = rel.flag("RELEASE_ACONFIG_REQUIRE_ALL_READ_ONLY")
        if ro is not None:
            cmd += ["--allow-read-write", "true" if ro == "" else "false"]
        cmd += ["--cache", cache]
        mode = p.get("mode", "production")
        full = (f"rm -rf {d} && mkdir -p {d} && " + " ".join(cmd) +
                f" && {tool} create-rust-lib --mode {mode} --cache {cache} --out {d}")
        # A crate that rustlibs.toml prunes can still be named by a `use` line
        # of the template. The compile proves the crate is otherwise unused.
        pr = self.closure.prune.get(c.module, {})
        for line in pr.get("strip_lines", []):
            full += f" && sed -i '/^{line}/d' {out}"
        # aconfig_codegen rust_aconfig_library.go SourceProviderDeps.
        p.setdefault("rustlibs", [])
        p["rustlibs"] = ["libaconfig_storage_read_api", "liblazy_static", "liblogger", "liblog_rust"] + p["rustlibs"]
        c.gen = Step([out], [f"build {out}: genrule {' '.join(decls + values)} | {tool}",
                             f"  name = aconfig_{c.module}", f"  cmd = {full}", ""])
        self.steps.append(c.gen)

    def aidl(self, c):
        it = self.gen.aidl_ifaces[c.module[:-len("-rust")]]
        srcs, root = generators._aidl_srcs(self.gen, it, "")
        d = self.gdir(c)
        out = f"{d}/{c.crate_name}.rs"
        c.root = out
        glue = "system/tools/aidl/build/aidl_rust_glue.py"
        tool = self.args.aidl
        rs = [f"{d}/src/{os.path.splitext(rel)[0]}.rs" for _, rel in srcs]
        imports = bp2cmake._uniq([os.path.normpath(f[: len(f) - len(r)].rstrip("/")) for f, r in srcs])
        cmds = [f"rm -rf {d} && mkdir -p {d}/src"]
        for f, _ in srcs:
            cmds.append(f"{tool} --lang=rust --min_sdk_version current -o {d}/src "
                        + " ".join("-I" + os.path.relpath(i, SRC) for i in imports) + " "
                        + os.path.relpath(f, SRC))
        cmds.append(f"python3 -I {glue} {out} {d}/src {' '.join(rs)}")
        ins = " ".join(os.path.relpath(f, SRC) for f, _ in srcs)
        c.gen = Step([out], [f"build {out}: genrule {ins} {glue} | {tool}",
                             f"  name = aidl_{c.module}", "  cmd = " + " && ".join(cmds), ""])
        self.steps.append(c.gen)

    # ----- Ninja text -------------------------------------------------------

    def ninja_rules(self):
        return []

    def ninja_steps(self):
        out = []
        for s in self.steps:
            out += s.rule_lines
        return out

    def cmake_deps(self):
        """CMake targets the Rust Ninja file needs first."""
        deps = ["bindgen_tool", "aconfig_tool", "m_aidl"]
        deps += [bp2cmake.gtid(g) for g in bp2cmake._uniq(self.cc_gen_deps)]
        return deps
