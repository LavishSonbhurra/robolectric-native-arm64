#!/usr/bin/env python3
"""Generate CMake for a closure of Soong modules from AOSP Android.bp files.

The variant evaluated is Soong's host variant for os=linux_glibc, arch=arm64
(or x86_64 with --arch; lib64), with static linkage. See docs/NOTES.md for how each
Soong rule is mirrored and where we deviate.

Usage:
  tools/bp2cmake.py --out DIR [--arch arm64|x86_64] [--host-tools-dir DIR]
                    [--root MODULE ...] [--explain MODULE]

--host-tools-dir: for cross builds. The cc_binary_host tools that generators
run (aidl, aidl-cpp, aprotoc, sysprop_cpp) are taken from DIR (the bin/
directory of a native build of the same tree) instead of being built.

Inputs: src/ (fetched by tools/fetch.py), config/aosp.toml,
overrides/overrides.toml. Output: DIR/modules.cmake plus one response file
per (module, language) under DIR/rsp/, holding the exact compiler flags in
Soong's order (response files keep CMake from de-duplicating or reordering
them).
"""

import argparse
import copy
import glob as globmod
import json
import os
import re
import shutil
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blueprint as bp  # noqa: E402
import release_config  # noqa: E402
import soong_flags  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")


class GenError(Exception):
    pass


# ---------------------------------------------------------------------------
# Configuration


def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


ARCHES = ("arm64", "x86_64")


class Config:
    def __init__(self, arch=None):
        self.aosp = load_toml(os.path.join(ROOT, "config", "aosp.toml"))
        self.ov = load_toml(os.path.join(ROOT, "overrides", "overrides.toml"))
        self.os = self.aosp["variant"]["os"]
        # config/aosp.toml holds the default; RA64_ARCH (CMake) overrides it.
        self.arch = arch or self.aosp["variant"]["arch"]
        if self.arch not in ARCHES:
            raise GenError(f"unsupported arch {self.arch} (have {', '.join(ARCHES)})")
        self.host_tools_dir = None
        self.release = release_config.ReleaseConfig(
            os.path.join(SRC, "build", "release"), self.aosp["release"]["config"],
            self.aosp["release"].get("variant", ""))
        self.warned = set()

    def warn(self, msg):
        if msg not in self.warned:
            self.warned.add(msg)
            print(f"bp2cmake: warning: {msg}", file=sys.stderr)

    def _resolve_value(self, v):
        """Override values may refer to release flags: "release_flag:NAME"."""
        if isinstance(v, str) and v.startswith("release_flag:"):
            fv = self.release.flag(v.split(":", 1)[1])
            if fv is None:
                raise GenError(f"unknown release flag in overrides: {v}")
            return fv
        return v

    def soong_config(self, ns, var):
        tbl = self.ov.get("soong_config", {}).get(ns, {})
        if var not in tbl:
            self.warn(f"soong config variable {ns}.{var} not set in overrides; treating as unset")
            return None
        return self._resolve_value(tbl[var])

    def product_variable(self, name):
        tbl = self.ov.get("product_variables", {})
        if name not in tbl:
            self.warn(f"product variable {name} not set in overrides; treating as unset")
            return None
        return self._resolve_value(tbl[name])

    def module_override(self, name):
        return self.ov.get("module", {}).get(name, {})


class SelectCtx(bp.SelectContext):
    def __init__(self, cfg):
        self.cfg = cfg

    def condition(self, func, args):
        c = self.cfg
        if func == "arch":
            return c.arch
        if func == "os":
            return c.os
        if func == "release_flag":
            v = c.release.flag(args[0])
            if v is None:
                c.warn(f"select on undeclared release flag {args[0]}")
                return None
            # Soong exposes bool flags as booleans to select(); string flags as strings.
            decl = c.release.decls.get(args[0], {})
            if v in ("true", ""):
                return v == "true"
            return v
        if func == "soong_config_variable":
            v = c.soong_config(args[0], args[1])
            if isinstance(v, str) and v in ("true", "false"):
                return v == "true"
            return v
        if func == "product_variable":
            return c.product_variable(args[0])
        if func == "variant":
            return None
        raise bp.BlueprintError(f"unsupported select condition {func}({args})")


# ---------------------------------------------------------------------------
# Module index


class Module:
    __slots__ = ("type", "props", "dir", "file", "line", "name")

    def __init__(self, mtype, props, d, f, line):
        self.type = mtype
        self.props = props
        self.dir = d  # relative to SRC
        self.file = f
        self.line = line
        self.name = props.get("name")

    def where(self):
        return f"{os.path.relpath(self.file, SRC)}:{self.line}"


class Index:
    def __init__(self, cfg):
        self.cfg = cfg
        self.modules = {}
        self.soong_config_types = {}
        self.by_dir = {}
        ctx = SelectCtx(cfg)
        scopes = {}
        skip = {".cache", ".stamps"}
        for dirpath, dirnames, filenames in os.walk(SRC):
            rel = os.path.relpath(dirpath, SRC)
            if rel == ".":
                dirnames[:] = [d for d in dirnames if d not in skip]
                rel = ""
            dirnames.sort()
            parent = os.path.dirname(rel)
            pscope = None
            p = rel
            while p:
                p = os.path.dirname(p)
                if p in scopes:
                    pscope = scopes[p]
                    break
            if "Android.bp" not in filenames:
                continue
            path = os.path.join(dirpath, "Android.bp")
            try:
                mods, scope = bp.parse_file(path, ctx, pscope)
            except bp.BlueprintError as e:
                cfg.warn(f"skipping {os.path.relpath(path, SRC)}: {e}")
                continue
            scopes[rel] = scope
            # `build = [...]` lists more Blueprint files in the same directory
            # (frameworks/base/AconfigFlags.bp). Blueprint parses them with
            # the listing file's scope as parent.
            files = [(path, mods)]
            for extra in scope.get("build", []) if isinstance(scope.get("build"), list) else []:
                epath = os.path.join(dirpath, extra)
                if not os.path.exists(epath):
                    continue
                try:
                    emods, _ = bp.parse_file(epath, ctx, scope)
                except bp.BlueprintError as e:
                    cfg.warn(f"skipping {os.path.relpath(epath, SRC)}: {e}")
                    continue
                files.append((epath, emods))
            for path, mods in files:
                for mtype, props, line in mods:
                    m = Module(mtype, props, rel, path, line)
                    if mtype == "soong_config_module_type":
                        self.soong_config_types[props["name"]] = props
                        continue
                    if not m.name:
                        continue
                    if mtype in ("ndk_library", "llndk_library"):
                        # Soong registers these as <name>.ndk / <name>.llndk.
                        m.name = m.name + "." + mtype.split("_")[0]
                    self.by_dir.setdefault(rel, []).append(m)
                    if m.name in self.modules:
                        old = self.modules[m.name]
                        # Soong namespaces can make duplicates legal; keep the first.
                        cfg.warn(f"duplicate module {m.name} at {m.where()} (keeping {old.where()})")
                        continue
                    self.modules[m.name] = m

    def get(self, name):
        return self.modules.get(name)


# ---------------------------------------------------------------------------
# Property merging (proptools semantics)

# Properties tagged `android:"variant_prepend"` in Soong's cc structs: the
# arch/os-specific value goes before the generic one.
VARIANT_PREPEND = {
    "include_dirs", "local_include_dirs", "generated_headers", "export_include_dirs",
    "export_system_include_dirs", "whole_static_libs", "static_libs", "header_libs",
    "export_header_lib_headers", "device_first_generated_headers",
}


def prepend_props(dst, src):
    """proptools.PrependProperties: lists src+dst, scalars keep dst if set."""
    for k, v in src.items():
        if k in ("name", "defaults"):
            continue
        if k not in dst:
            dst[k] = copy.deepcopy(v)
        elif isinstance(v, list):
            dst[k] = copy.deepcopy(v) + dst[k]
        elif isinstance(v, dict):
            prepend_props(dst[k], v)


def append_props(dst, src, prepend_keys=VARIANT_PREPEND):
    """proptools.ExtendMatchingProperties with Append order (Prepend for
    variant_prepend fields): lists dst+src, scalars from src win."""
    for k, v in src.items():
        if k not in dst:
            dst[k] = copy.deepcopy(v)
        elif isinstance(v, list):
            dst[k] = (copy.deepcopy(v) + dst[k]) if k in prepend_keys else dst[k] + copy.deepcopy(v)
        elif isinstance(v, dict):
            append_props(dst[k], v, prepend_keys)
        else:
            dst[k] = copy.deepcopy(v)


# ---------------------------------------------------------------------------
# Variant resolution


HOST_ONLY_TYPES = {"cc_library_host_static", "cc_library_host_shared", "cc_binary_host",
                   "cc_test_host", "cc_object_host", "rust_binary_host", "rust_library_host",
                   "rust_ffi_host_static", "cc_genrule_host"}


class Resolver:
    def __init__(self, cfg, index):
        self.cfg = cfg
        self.index = index
        self.cache = {}

    def base_props(self, m):
        """Module properties after load hooks (soong_config_module_type)."""
        props = copy.deepcopy(m.props)
        mtype = m.type
        sct = self.index.soong_config_types.get(mtype)
        if sct:
            mtype = sct["module_type"]
            ns = sct["config_namespace"]
            scv = props.pop("soong_config_variables", {})
            bool_vars = set(sct.get("bool_variables", []))
            value_vars = set(sct.get("value_variables", []))
            for var, block in scv.items():
                block = dict(block)
                cdef = block.pop("conditions_default", None)
                val = self.cfg.soong_config(ns, var)
                chosen = None
                if var in bool_vars:
                    on = val in (True, "true") or (isinstance(val, str) and val not in ("", "false"))
                    chosen = block if on else cdef
                elif var in value_vars:
                    if val is not None and val != "":
                        chosen = _printf_props(block, val)
                    else:
                        chosen = cdef
                else:  # string variable
                    if val is not None and val in block:
                        chosen = block[val]
                    else:
                        chosen = cdef
                if chosen:
                    append_props(props, chosen, prepend_keys=set())
        return mtype, props

    def defaults_list(self, m):
        out = []
        seen = set()

        def walk(names):
            for n in names:
                d = self.index.get(n)
                if d is None:
                    raise GenError(f"{m.where()}: defaults module {n} not found")
                if n in seen:
                    continue
                seen.add(n)
                out.append(d)
                walk(d.props.get("defaults", []))

        walk(m.props.get("defaults", []))
        return out

    def resolve(self, name):
        """Returns (type, props) of the host linux_glibc arm64 variant."""
        if name in self.cache:
            return self.cache[name]
        m = self.index.get(name)
        if m is None:
            raise GenError(f"module {name} not found (is its project in config/projects.toml?)")
        mtype, props = self.base_props(m)
        for d in self.defaults_list(m):
            _, dprops = self.base_props(d)
            prepend_props(props, dprops)
        apply_variant(props, self.cfg)
        self.cache[name] = (mtype, props)
        return mtype, props


def _printf_props(block, val):
    def sub(x):
        if isinstance(x, str):
            return x.replace("%s", str(val)).replace("%d", str(val))
        if isinstance(x, list):
            return [sub(i) for i in x]
        if isinstance(x, dict):
            return {k: sub(v) for k, v in x.items()}
        return x
    return sub(block)


# Order of target/arch property structs Soong squashes into the module for a
# host linux_glibc arm64 variant (android/arch.go setOSProperties then
# setArchProperties). Each is merged with Append order (Prepend for
# variant_prepend fields).
def variant_blocks(props, cfg):
    target = props.get("target", {})
    arch = props.get("arch", {})
    multilib = props.get("multilib", {})
    a = cfg.arch
    seq = []
    # setOSProperties
    for k in ("host", "linux", "host_linux", "glibc", cfg.os, "not_windows"):
        if k in target:
            seq.append(("target." + k, target[k]))
    # setArchProperties
    if a in arch:
        seq.append(("arch." + a, {k: v for k, v in arch[a].items() if not isinstance(v, dict)
                                  or k in ("static", "shared", "target", "sanitize", "lto", "pgo")}))
    if "lib64" in multilib:
        seq.append(("multilib.lib64", multilib["lib64"]))
    for k in ("linux_" + a, cfg.os + "_" + a, "glibc_" + a):
        if k in target:
            seq.append(("target." + k, target[k]))
    return seq


def apply_variant(props, cfg):
    for _, block in variant_blocks(props, cfg):
        append_props(props, block)
    platform_cflags = props.get("target", {}).get("platform", {}).get("cflags", [])
    for k in ("target", "arch", "multilib", "codegen"):
        props.pop(k, None)
    # target.platform.cflags is applied by compilerFlags when !useSdk (true on host).
    if platform_cflags:
        props["_platform_cflags"] = platform_cflags
    pv = props.pop("product_variables", {})
    for var, block in pv.items():
        val = cfg.product_variable(var)
        if val is None or val is False or val == "" or val == "false":
            continue
        if val is True or val == "true":
            append_props(props, block)
        else:
            append_props(props, _printf_props(block, val))


def host_enabled(mtype, props):
    if props.get("enabled") is False:
        return False
    if mtype in HOST_ONLY_TYPES:
        return True
    return bool(props.get("host_supported"))


# ---------------------------------------------------------------------------
# Paths and globs


def src_path(rel):
    return os.path.normpath(os.path.join(SRC, rel))


def mod_path(mdir, rel):
    return os.path.normpath(os.path.join(SRC, mdir, rel))


def expand_globs(mdir, patterns, excludes, what):
    """Soong path globs, relative to the module directory."""
    base = os.path.join(SRC, mdir)

    def one(p):
        if any(ch in p for ch in "*?["):
            hits = globmod.glob(os.path.join(base, p), recursive=True, include_hidden=False)
            return sorted(h for h in hits if os.path.isfile(h))
        return [os.path.normpath(os.path.join(base, p))]

    exc = set()
    for e in excludes:
        if e.startswith(":"):
            continue
        exc.update(one(e))
    out = []
    for p in patterns:
        for h in one(p):
            if h not in exc:
                out.append(h)
    return out


# ---------------------------------------------------------------------------
# cc modules

CC_TYPES = {
    "cc_library": "library", "cc_library_static": "static", "cc_library_shared": "shared",
    "cc_library_host_static": "static", "cc_library_host_shared": "shared",
    "cc_library_headers": "headers", "cc_binary": "binary", "cc_binary_host": "binary",
    "cc_object": "object", "cc_aconfig_library": "library", "cc_test_library": "library",
}

SKIP_SHARED = {"libc", "libm", "libdl", "libpthread", "librt", "libc++", "libc++_static",
               "libc++demangle", "libdl_android", "libc_musl"}


def is_third_party(mdir):
    if not mdir.startswith(("external/", "vendor/", "hardware/")):
        return False
    for rx in (r"^vendor/[^/]*google[^/]*/", r"^hardware/google/", r"^hardware/interfaces/",
               r"^hardware/libhardware[^/]*/", r"^hardware/ril/"):
        if re.match(rx, mdir + "/"):
            return False
    return True


class Gen:
    """A code generation step: one custom command."""

    def __init__(self, name, kind):
        self.name = name
        self.kind = kind
        self.outputs = []   # absolute paths
        self.sources = []   # generated compilable sources (subset of outputs)
        self.headers = []
        self.include_dirs = []  # exported include dirs
        self.inputs = []
        self.commands = []  # list of argv lists (or shell strings)
        self.tools = []     # CMake targets/executables it needs
        self.depends = []   # file deps
        self.workdir = None
        self.gen_deps = []  # other generators that must run first


class CcModule:
    def __init__(self, name):
        self.name = name


class Generator:
    def __init__(self, cfg, out_dir):
        self.cfg = cfg
        self.index = Index(cfg)
        self.res = Resolver(cfg, self.index)
        self.out = os.path.abspath(out_dir)
        self.gen_root = "${CMAKE_BINARY_DIR}/gen"  # in CMake text
        self.gen_root_abs = None  # set by caller (absolute build dir path)
        self.cc = {}
        self.gens = {}
        self.errors = []
        self.headers_only = set(cfg.ov.get("closure", {}).get("headers_only", []))
        self.src_rel = {}       # absolute source path -> Soong Path.Rel()
        self.aidl_cc_inputs = {}  # aidl_cc generator name -> [(file, rel)]
        self.rust_seen = {}     # rust module -> type, for the closure report
        self.rust_missing = set()
        self.tools_needed = set()
        self.tools_external = set()  # host tools taken from --host-tools-dir
        import aidl_interface
        aidl_interface.expand(self)

    # ----- helpers -----

    def gendir(self, name):
        return os.path.join(self.gen_root_abs, name)

    def err(self, msg):
        self.errors.append(msg)

    # ----- generators -----

    def genrule_for(self, name):
        """genrule / aconfig / sysprop / aidl / filegroup producing files."""
        if name in self.gens:
            return self.gens[name]
        import generators
        g = generators.make(self, name)
        self.gens[name] = g
        return g

    def filegroup_srcs(self, name):
        mtype, props = self.res.resolve(name)
        m = self.index.get(name)
        out = []
        # Path.Rel() of filegroup files: relative to the filegroup's `path`
        # (default: its directory). Used for .aidl package paths.
        base = os.path.normpath(os.path.join(SRC, m.dir, props.get("path", "")))
        for s in props.get("srcs", []):
            if s.startswith(":"):
                out.extend(self.module_ref(s[1:], m.dir))
            else:
                for f in expand_globs(m.dir, [s], props.get("exclude_srcs", []), name):
                    self.src_rel.setdefault(f, os.path.relpath(f, base))
                    out.append(f)
        return out

    def module_ref(self, ref, from_dir):
        """`:name` or `:name{tag}` in srcs. Returns files (absolute paths)."""
        tag = None
        if "{" in ref:
            ref, tag = ref.split("{", 1)
            tag = tag.rstrip("}")
        m = self.index.get(ref)
        if m is None:
            raise GenError(f"source reference :{ref} not found (from {from_dir})")
        mtype = self.res.resolve(ref)[0]
        if mtype == "filegroup":
            return self.filegroup_srcs(ref)
        g = self.genrule_for(ref)
        if tag:
            return [o for o in g.outputs if o.endswith(tag.lstrip("."))] if tag.startswith(".") else g.outputs
        return g.outputs

    # ----- cc -----

    def cc_module(self, name):
        if name in self.cc:
            return self.cc[name]
        mtype, props = self.res.resolve(name)
        m = self.index.get(name)
        kind = CC_TYPES.get(mtype)
        if kind is None:
            raise GenError(f"{name} ({m.where()}): module type {mtype} is not a cc library")
        if not host_enabled(mtype, props):
            self.err(f"{name} ({m.where()}): not enabled for the host variant")
        c = CcModule(name)
        c.mtype = mtype
        c.kind = kind
        c.dir = m.dir
        c.where = m.where()
        ov = self.cfg.module_override(name)
        if ov.get("props"):
            append_props(props, ov["props"], prepend_keys=set())
        c.headers_only = name in self.headers_only or kind == "headers"
        # link_only: none of the module's own sources or generated code is
        # built; its exported include dirs are used and its whole_static_libs
        # are compiled and linked (overrides.toml says why per module).
        c.link_only = bool(ov.get("link_only"))
        if c.link_only:
            c.headers_only = True
            for k in ("generated_headers", "generated_sources", "export_generated_headers", "srcs"):
                props.pop(k, None)
        # cc_library builds both variants; we use the static one. Shared-only
        # libraries are also built as archives (libandroid_runtime links them
        # statically), with their `shared` properties.
        if kind in ("library", "static"):
            append_props(props, props.get("static", {}))
        elif kind == "shared":
            append_props(props, props.get("shared", {}))
        props.pop("static", None)
        props.pop("shared", None)
        c.props = props

        def L(k):
            return list(props.get(k, []))

        excl_static = set(L("exclude_static_libs"))
        excl_shared = set(L("exclude_shared_libs"))
        excl_header = set(L("exclude_header_libs"))
        c.header_libs = [x for x in L("header_libs") if x not in excl_header]
        c.whole_static_libs = L("whole_static_libs")
        c.static_libs = [x for x in L("static_libs") if x not in excl_static]
        c.shared_libs = [x for x in L("shared_libs") if x not in excl_shared and x not in SKIP_SHARED]
        if mtype == "cc_aconfig_library" and props.get("mode", "production") != "force-read-only":
            # Added by CcAconfigLibraryCallbacks.GeneratorDeps.
            c.shared_libs += ["libaconfig_storage_read_api_cc", "libbase", "liblog"]
        c.export_header = set(L("export_header_lib_headers"))
        c.export_static = set(L("export_static_lib_headers"))
        c.export_shared = set(L("export_shared_lib_headers"))
        c.generated_headers = L("generated_headers")
        c.export_generated = set(L("export_generated_headers"))
        c.generated_sources = [x for x in L("generated_sources") if x not in set(L("exclude_generated_sources"))]
        c.export_include_dirs = [mod_path(m.dir, d) for d in L("export_include_dirs")]
        c.export_system_include_dirs = [mod_path(m.dir, d) for d in L("export_system_include_dirs")]
        c.local_include_dirs = [mod_path(m.dir, d) for d in L("local_include_dirs")]
        c.include_dirs = [src_path(d) for d in L("include_dirs")]
        c.cflags = L("cflags")
        c.cppflags = L("cppflags")
        c.conlyflags = L("conlyflags")
        c.asflags = L("asflags")
        c.platform_cflags = L("_platform_cflags")
        c.c_std = props.get("c_std")
        c.cpp_std = props.get("cpp_std")
        c.gnu_extensions = props.get("gnu_extensions")
        c.rtti = props.get("rtti", False)
        c.include_build_directory = props.get("include_build_directory", True)
        c.host_ldlibs = L("host_ldlibs")
        c.ldflags = L("ldflags")
        c.stl = props.get("stl")
        c.aconfig = props.get("aconfig_declarations") if mtype == "cc_aconfig_library" else None

        # Sources
        srcs = []
        gen_srcs = []
        c.gen_deps = []      # generator names this module's compile depends on
        c.sysprop = []
        c.yacc_dirs = []
        c.proto = []
        c.aidl_dirs = []
        c.export_aidl = False
        aidl_files = []
        src_list = [] if c.headers_only else L("srcs")
        gsrc_list = [] if c.headers_only else c.generated_sources
        for s in src_list:
            if s.startswith(":"):
                ref = s[1:].split("{")[0]
                files = self.module_ref(s[1:], m.dir)
                if self.res.resolve(ref)[0] != "filegroup":
                    c.gen_deps.append(ref)
                srcs.extend(files)
            else:
                for f in expand_globs(m.dir, [s], L("exclude_srcs"), name):
                    self.src_rel.setdefault(f, os.path.relpath(f, os.path.join(SRC, m.dir)))
                    srcs.append(f)
        exc = set(expand_globs(m.dir, [e for e in L("exclude_srcs") if not e.startswith(":")], [], name))
        srcs = [s for s in srcs if s not in exc]
        for gname in gsrc_list:
            g = self.genrule_for(gname)
            c.gen_deps.append(gname)
            gen_srcs.extend(g.sources)
        for gname in c.generated_headers:
            self.genrule_for(gname)
            c.gen_deps.append(gname)
        if c.aconfig:
            gname = name + "{aconfig}"
            g = self.genrule_for(gname)
            c.gen_deps.append(gname)
            gen_srcs.extend(g.sources)
        # Per-extension processing (cc/gen.go genSources)
        final = []
        for s in srcs + gen_srcs:
            ext = os.path.splitext(s)[1]
            if ext == ".sysprop":
                gname = name + "{sysprop:" + os.path.relpath(s, os.path.join(SRC, m.dir)) + "}"
                g = self.genrule_for(gname)
                c.gen_deps.append(gname)
                c.sysprop.append(g)
                final.extend(g.sources)
            elif ext == ".aidl":
                # cc/gen.go genAidl: one aidl-cpp run per file, all into gen/aidl.
                rel = self.src_rel.get(s)
                if rel is None:
                    self.err(f"{name}: cannot tell the package path of {s}")
                    continue
                aidl_files.append((s, rel))
                final.append(("aidl", s))
            elif ext == ".proto":
                gname = name + "{proto:" + os.path.relpath(s, SRC) + "}"
                g = self.genrule_for(gname)
                c.gen_deps.append(gname)
                c.proto.append(g)
                final.extend(g.sources)
            elif ext in (".yy", ".y", ".ll", ".l"):
                gname = name + "{yacc_lex:" + os.path.relpath(s, os.path.join(SRC, m.dir)) + "}"
                g = self.genrule_for(gname)
                c.gen_deps.append(gname)
                final.extend(g.sources)
                if ext in (".yy", ".y"):
                    c.yacc_dirs = [os.path.join(self.gendir(name), "yacc", m.dir)]
            elif ext == ".asm":
                final.extend(self.yasm(c, s))
            elif ext in (".h", ".hpp", ".inc", ".rs", ".o", ".def", ".txt", ".map"):
                continue
            else:
                final.append(s)
        if aidl_files:
            gname = name + "{aidl_cc}"
            self.aidl_cc_inputs[gname] = aidl_files
            g = self.genrule_for(gname)
            c.gen_deps.append(gname)
            cpp = dict(zip([f for f, _ in aidl_files], g.sources))
            final = [cpp[x[1]] if isinstance(x, tuple) else x for x in final]
            c.aidl_dirs = list(g.include_dirs)
            c.export_aidl = bool(props.get("aidl", {}).get("export_aidl_headers"))
        c.srcs = final
        for f in srcs:
            if f.startswith(SRC + "/") and not os.path.exists(f):
                self.err(f"{name} ({m.where()}): source {os.path.relpath(f, SRC)} does not exist")
        if c.proto:
            # cc/proto.go protoDeps / protoFlags
            ptype = props.get("proto", {}).get("type", "lite")
            lib = {"full": "libprotobuf-cpp-full", "lite": "libprotobuf-cpp-lite"}[ptype]
            if c.kind in ("static", "library", "binary"):
                c.static_libs.append(lib)
            else:
                c.shared_libs.append(lib)
            if props.get("proto", {}).get("export_proto_headers"):
                c.export_static.add(lib)
            c.cflags.append("-DGOOGLE_PROTOBUF_NO_RTTI")
            pdir = os.path.join(self.gendir(name), "proto")
            c.proto_dirs = [os.path.join(pdir, m.dir), pdir]
            c.export_proto = bool(props.get("proto", {}).get("export_proto_headers"))
        else:
            c.proto_dirs = []
            c.export_proto = False
        self.cc[name] = c
        return c

    def yasm(self, c, src):
        """cc/builder.go: a .asm source is assembled by yasm into an object
        (Soong's prebuilts/misc yasm; here the system yasm). The object goes
        into the archive like a compiled source."""
        rel = os.path.relpath(src, SRC)
        gname = f"{c.name}{{yasm:{rel}}}"
        if gname not in self.gens:
            g = Gen(gname, "yasm")
            obj = os.path.join(self.gendir(c.name), "yasm", rel + ".o")
            g.commands = [[self.cfg.vars["cmake"], "-E", "make_directory", os.path.dirname(obj)],
                          [self.cfg.vars["yasm"], *soong_flags.yasm_flags(self, c), "-o", obj, src]]
            g.outputs = [obj]
            g.sources = [obj]
            g.inputs = [src]
            # yasm -M would give the %include list; the include dirs' .inc
            # files are a superset.
            for d in c.local_include_dirs + c.include_dirs + [os.path.dirname(src)]:
                g.depends += sorted(globmod.glob(os.path.join(d, "*.inc")))
            self.gens[gname] = g
        c.gen_deps.append(gname)
        return self.gens[gname].sources

    def exports(self, name, stack=()):
        """FlagExporterInfo: (include_dirs, system_include_dirs, gen_deps)."""
        c = self.cc_module(name)
        if hasattr(c, "_exports"):
            return c._exports
        if name in stack:
            raise GenError(f"dependency cycle through {name}")
        stack = stack + (name,)
        inc = list(c.export_include_dirs)
        sysinc = list(c.export_system_include_dirs)
        gdeps = []
        if c.aconfig:
            g = self.genrule_for(name + "{aconfig}")
            inc += g.include_dirs
            gdeps.append(g.name)
        for lib in c.header_libs:
            if lib in c.export_header:
                i, s, d = self.exports(lib, stack)
                inc += i; sysinc += s; gdeps += d
        for lib in c.whole_static_libs:
            if self.is_cc(lib):
                i, s, d = self.exports(lib, stack)
                inc += i; sysinc += s; gdeps += d
        for lib in c.static_libs:
            if lib in c.export_static and self.is_cc(lib):
                i, s, d = self.exports(lib, stack)
                inc += i; sysinc += s; gdeps += d
        for lib in c.shared_libs:
            if lib in c.export_shared and self.is_cc(lib):
                i, s, d = self.exports(lib, stack)
                inc += i; sysinc += s; gdeps += d
        for gname in c.generated_headers:
            if gname in c.export_generated:
                g = self.genrule_for(gname)
                inc += g.include_dirs
                gdeps.append(gname)
        for g in c.sysprop:
            inc += g.include_dirs
            gdeps.append(g.name)
        if c.export_proto:
            inc += c.proto_dirs
            gdeps += [g.name for g in c.proto]
        if c.export_aidl:
            inc += c.aidl_dirs
            gdeps.append(name + "{aidl_cc}")
        c._exports = (_uniq(inc), _uniq(sysinc), _uniq(gdeps + c.gen_deps))
        return c._exports

    def is_cc(self, name):
        if self.cfg.module_override(name).get("external"):
            return False
        m = self.index.get(name)
        if m is None:
            raise GenError(f"module {name} not found (is its project in config/projects.toml?)")
        mtype = self.res.resolve(name)[0]
        if mtype in CC_TYPES:
            return True
        ov = self.cfg.module_override(name)
        if ov.get("external"):
            return False
        if mtype.startswith("rust_"):
            return False  # see rust_cc_deps
        self.err(f"{name} ({m.where()}): dependency of unsupported type {mtype}")
        return False

    def is_rust(self, name):
        m = self.index.get(name)
        return m is not None and self.res.resolve(name)[0].startswith("rust_")

    def rust_cc_deps(self, name, seen=None):
        """C/C++ halves of a Rust dependency. Soong compiles Rust crates as
        rlibs and links their cc whole_static_libs/static_libs (and those of
        every crate in `rustlibs`) into the final shared library, next to
        the generated librustlibs.a staticlib. The Rust code itself comes
        from the rust track (imported target `rustlibs`); we build and link
        the C++ halves (cxx.cc, the cxx bridge code, FFI helpers)."""
        top = seen is None
        seen = set() if seen is None else seen
        if name in seen:
            return []
        seen.add(name)
        if self.index.get(name) is None:
            self.rust_missing.add(name)
            return []
        mtype, props = self.res.resolve(name)
        self.rust_seen[name] = mtype
        out = []
        for d in list(props.get("whole_static_libs", [])) + list(props.get("static_libs", [])):
            if self.index.get(d) is not None and self.is_cc(d) and d not in out:
                out.append(d)
        for r in list(props.get("rustlibs", [])):
            for d in self.rust_cc_deps(r, seen):
                if d not in out:
                    out.append(d)
        return out

    def compile_flags(self, c):
        """Per-language flag lists in Soong's order (cc/builder.go)."""
        return soong_flags.module_flags(self, c)


def _uniq(xs):
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# Closure and CMake emission


def closure(gen, roots):
    """Modules to compile. Libraries listed as headers_only (or header
    libraries) are not compiled; only their exported headers are used, and we
    do not descend into their non-reexported dependencies."""
    order = []
    seen = set()

    def visit(name, via):
        if name in seen:
            return
        seen.add(name)
        try:
            c = gen.cc_module(name)
        except GenError as e:
            gen.err(f"{e} (needed by {via})")
            return
        deps = list(c.header_libs) + list(c.whole_static_libs) + list(c.static_libs) + list(c.shared_libs)
        if c.headers_only:
            deps = [d for d in c.header_libs if d in c.export_header] + list(c.whole_static_libs) + \
                   [d for d in c.static_libs if d in c.export_static] + \
                   [d for d in c.shared_libs if d in c.export_shared]
        for d in deps:
            try:
                if not gen.is_cc(d):
                    if not c.headers_only and gen.is_rust(d):
                        for x in gen.rust_cc_deps(d):
                            visit(x, d)
                    continue
            except GenError as e:
                gen.err(f"{e} (needed by {name})")
                continue
            visit(d, name)
        order.append(name)

    for r in roots:
        visit(r, "command line")
    return order


def write_if_changed(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return
    with open(path, "w") as f:
        f.write(text)


def rsp_quote(arg):
    if re.fullmatch(r"[A-Za-z0-9_\-+=/.,:@%]+", arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmake_quote(s):
    """A CMake quoted argument holding exactly `s` (no variable expansion)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace(";", "\\;") + '"'


def tid(name):
    return "m_" + re.sub(r"[^A-Za-z0-9_.+-]", "_", name)


def gtid(gname):
    return "g_" + re.sub(r"[^A-Za-z0-9_.+-]", "_", gname)


def link_closure(gen, name):
    """Libraries to link into a host tool: transitive static, whole static and
    shared dependencies (all linked statically)."""
    out = []
    seen = set()

    def walk(n):
        c = gen.cc[n]
        deps = c.whole_static_libs + c.static_libs + c.shared_libs
        if c.headers_only:
            # Only what closure() compiled: whole_static_libs (link_only).
            deps = list(c.whole_static_libs)
        for d in deps:
            if d in seen:
                continue
            seen.add(d)
            if not gen.is_cc(d):
                ov = gen.cfg.module_override(d)
                if ov.get("target") or ov.get("link"):
                    out.append(("external", d))
                elif gen.is_rust(d):
                    out.append(("rust", d))
                    for x in gen.rust_cc_deps(d):
                        if x not in seen:
                            seen.add(x)
                            dc = gen.cc_module(x)
                            if not dc.headers_only and dc.srcs:
                                out.append(("cc", x))
                            walk(x)
                continue
            dc = gen.cc_module(d)
            if not dc.headers_only and dc.srcs:
                out.append(("cc", d))
            walk(d)

    walk(name)
    return out


def emit(gen, order, out_dir):
    lines = ["# Generated by tools/bp2cmake.py. Do not edit.", ""]
    rsp_dir = os.path.join(out_dir, "rsp")
    manifest = {}
    used_gens = []
    # Compiler-version compatibility flags (overrides [compat]) go in a
    # response file shared by every compile that is deliberately not an
    # OBJECT_DEPENDS: they only demote diagnostics, so adding one must not
    # rebuild objects that already compiled.
    compat = gen.cfg.ov.get("compat", {})
    compat_rsp = {}
    for key, flags in (("c", compat.get("cflags", []) + compat.get("conlyflags", [])),
                       ("cxx", compat.get("cflags", []) + compat.get("cppflags", [])),
                       ("asm", [])):
        rp = os.path.join(rsp_dir, f"compat.{key}.rsp")
        write_if_changed(rp, "\n".join(rsp_quote(a) for a in flags) + "\n")
        compat_rsp[key] = rp
    for name in order:
        c = gen.cc[name]
        manifest[name] = {"dir": c.dir, "kind": c.kind, "headers_only": c.headers_only,
                          "srcs": len(c.srcs), "whole_static_libs": c.whole_static_libs,
                          "static_libs": c.static_libs, "shared_libs": c.shared_libs,
                          "header_libs": ([d for d in c.header_libs if d in c.export_header]
                                          if c.headers_only else c.header_libs),
                          "host_ldlibs": c.host_ldlibs}
        if c.headers_only or not c.srcs:
            continue
        flags = gen.compile_flags(c)
        t = tid(name)
        lines.append(f"# {name} ({c.where})")
        shared = c.kind == "shared" and name in gen.roots
        if c.kind == "binary":
            lines.append(f"add_executable({t}")
        elif shared:
            lines.append(f"add_library({t} SHARED")
        else:
            lines.append(f"add_library({t} STATIC")
        for src in c.srcs:
            lines.append(f"  {cmake_quote(src)}")
        lines.append(")")
        if c.kind == "binary":
            lines.append(f"set_target_properties({t} PROPERTIES OUTPUT_NAME {cmake_quote(name)} "
                         f"RUNTIME_OUTPUT_DIRECTORY {cmake_quote(gen.bin_dir)} LINKER_LANGUAGE CXX)")
        elif shared:
            lines.append(f"set_target_properties({t} PROPERTIES OUTPUT_NAME {cmake_quote(name)} "
                         f"PREFIX \"\" LIBRARY_OUTPUT_DIRECTORY {cmake_quote(gen.lib_dir)} LINKER_LANGUAGE CXX)")
        else:
            lines.append(f"set_target_properties({t} PROPERTIES OUTPUT_NAME {cmake_quote(name)} "
                         f"PREFIX \"\" ARCHIVE_OUTPUT_DIRECTORY {cmake_quote(gen.lib_dir)})")
        opts = []
        rsps = []
        for lang, key in (("C", "c"), ("CXX", "cxx"), ("ASM", "asm")):
            text = "\n".join(rsp_quote(a) for a in flags[key]) + "\n"
            rp = os.path.join(rsp_dir, f"{name}.{key}.rsp")
            write_if_changed(rp, text)
            rsps.append(rp)
            opts.append(f"\"$<$<COMPILE_LANGUAGE:{lang}>:@{rp}>\"")
            opts.append(f"\"$<$<COMPILE_LANGUAGE:{lang}>:@{compat_rsp[key]}>\"")
        lines.append(f"target_compile_options({t} PRIVATE {' '.join(opts)})")
        srcs_q = " ".join(cmake_quote(src) for src in c.srcs)
        lines.append(f"set_source_files_properties({srcs_q} TARGET_DIRECTORY {t} PROPERTIES "
                     f"OBJECT_DEPENDS {cmake_quote(';'.join(rsps)).replace(chr(92) + ';', ';')})")
        gdeps = flags["gen_deps"]
        if gdeps:
            lines.append(f"add_dependencies({t} {' '.join(gtid(g) for g in gdeps)})")
            used_gens += gdeps
        if c.kind == "binary":
            libs = link_closure(gen, name)
            items = []
            for kind, d in libs:
                if kind == "cc":
                    items.append(tid(d))
                elif kind == "external":
                    ov = gen.cfg.module_override(d)
                    items += [ov["target"]] if ov.get("target") else list(ov["link"])
                else:
                    raise GenError(f"{name}: host tool with a Rust dependency {d} is not supported")
            ldlibs = [x for x in c.host_ldlibs] + ["-ldl", "-lpthread", "-lm", "-lrt"]
            lines.append(f"target_link_libraries({t} PRIVATE -Wl,--start-group {' '.join(items)} "
                         f"-Wl,--end-group {' '.join(ldlibs)})")
            lines.append(f"target_link_options({t} PRIVATE -fuse-ld=lld -stdlib=libc++ "
                         f"-static-libstdc++ -lc++abi)")
        if shared:
            lines += emit_shared_link(gen, c, t, manifest)
        lines.append("")

    # Generators, including the ones they depend on.
    glines = ["# Generated by tools/bp2cmake.py. Do not edit.", ""]
    done = set()
    todo = list(used_gens)
    while todo:
        gname = todo.pop(0)
        if gname in done:
            continue
        done.add(gname)
        g = gen.gens[gname]
        todo += getattr(g, "gen_deps", [])
        glines.extend(emit_gen(gen, g))
    write_if_changed(os.path.join(out_dir, "generators.cmake"), "\n".join(glines) + "\n")
    write_if_changed(os.path.join(out_dir, "modules.cmake"), "\n".join(lines) + "\n")
    write_if_changed(os.path.join(out_dir, "closure.json"), json.dumps(manifest, indent=1) + "\n")


def emit_shared_link(gen, c, t, manifest):
    """Link the root as Soong links a host cc_library_shared (cc/builder.go
    transformObjToDynamicBinary: objects, static libs, then ldflags), with
    the C++ runtime, the UBSan minimal runtime and the Rust staticlib as
    CMake-level inputs the toolchain and rust tracks can replace."""
    libs = link_closure(gen, c.name)
    items = []
    rust = []
    for kind, d in libs:
        if kind == "cc":
            items.append(tid(d))
        elif kind == "rust":
            rust.append(d)
        else:
            ov = gen.cfg.module_override(d)
            items += [ov["target"]] if ov.get("target") else list(ov["link"])
    # MinimalRuntimeDep: any static dependency built with a UBSan minimal
    # runtime sanitizer makes the shared library link libclang_rt.ubsan_minimal
    # (hidden: Soong adds it as a dependency with unexportedSymbols).
    minimal = []
    for kind, d in libs:
        if kind == "cc":
            san, m = soong_flags.sanitizers(gen.cc[d])
            if san and m:
                minimal.append(d)
    lflags = soong_flags.shared_link_flags(gen, c)
    manifest[c.name]["link"] = {"static_libs": [d for k, d in libs if k == "cc"], "rust": rust,
                                "ubsan_minimal_from": minimal, "ldflags": lflags}
    out = [f"# Link of {c.name}: static closure in Soong's dependency order (lld"
           f" resolves archives in any order)."]
    out.append(f"set(AOSP_{c.name}_RUST_MODULES {' '.join(rust)})")
    out.append(f"target_link_libraries({t} PRIVATE {' '.join(items)})")
    vs = c.props.get("version_script")
    vsarg = f" VERSION_SCRIPT {cmake_quote(os.path.join(SRC, c.dir, vs))}" if vs else ""
    out.append(f"ra64_link_runtime({t} RUST {'ON' if rust else 'OFF'} "
               f"UBSAN_MINIMAL {'ON' if minimal else 'OFF'}{vsarg})")
    out.append(f"target_link_options({t} PRIVATE {' '.join(cmake_quote(f) for f in lflags)})")
    out.append(f"set_target_properties({t} PROPERTIES BUILD_RPATH "
               f"{cmake_quote(';'.join(soong_flags.RPATHS)).replace(chr(92) + ';', ';')} "
               f"BUILD_RPATH_USE_ORIGIN OFF)")
    vs = c.props.get("version_script")
    if vs:
        out.append(f"set_property(TARGET {t} APPEND PROPERTY LINK_DEPENDS "
                   f"{cmake_quote(os.path.join(SRC, c.dir, vs))})")
    return out


def emit_gen(gen, g):
    out = [f"# generator {g.name} ({g.kind})"]
    outs = " ".join(cmake_quote(o) for o in g.outputs)
    cmds = []
    for cmd in g.commands:
        if isinstance(cmd, str):
            cmds.append(f"COMMAND sh -c {cmake_quote(cmd)}")
        else:
            cmds.append("COMMAND " + " ".join(cmake_quote(a) for a in cmd))
    deps = " ".join(cmake_quote(d) for d in g.inputs + g.depends)
    tools = " ".join(g.tools)
    out.append(f"add_custom_command(OUTPUT {outs}")
    for cl in cmds:
        out.append(f"  {cl}")
    if deps or tools:
        out.append(f"  DEPENDS {deps} {tools}")
    if g.workdir:
        out.append(f"  WORKING_DIRECTORY {cmake_quote(g.workdir)}")
    out.append(f"  COMMENT {cmake_quote('Generating ' + g.name)} VERBATIM)")
    out.append(f"add_custom_target({gtid(g.name)} DEPENDS {outs})")
    gd = [gtid(x) for x in getattr(g, "gen_deps", [])]
    if gd:
        out.append(f"add_dependencies({gtid(g.name)} {' '.join(gd)})")
    out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory for generated CMake")
    ap.add_argument("--binary-dir", required=True, help="CMake binary dir")
    ap.add_argument("--cmake-command", default="cmake")
    ap.add_argument("--arch", choices=ARCHES, help="default: config/aosp.toml [variant] arch")
    ap.add_argument("--host-tools-dir", help="native host tools for a cross build (bin/ of a native build)")
    ap.add_argument("--root", action="append", default=[])
    ap.add_argument("--explain", action="append", default=[],
                    help="print the resolved properties and flags of a module")
    args = ap.parse_args()
    cfg = Config(args.arch)
    if args.host_tools_dir:
        cfg.host_tools_dir = os.path.abspath(args.host_tools_dir)
    roots = args.root or cfg.ov.get("closure", {}).get("roots", [])
    bdir = os.path.abspath(args.binary_dir)
    cfg.vars = {"binary_dir": bdir, "cmake": args.cmake_command, "protoc": shutil.which("protoc") or "protoc",
                "bison": shutil.which("bison") or "bison", "flex": shutil.which("flex") or "flex",
                "yasm": shutil.which("yasm") or "yasm"}
    gen = Generator(cfg, args.out)
    gen.roots = list(roots)
    # Toolchain builtin headers (overrides [toolchain]): a directory of
    # symlinks into src/, searched after every other include dir.
    bh = cfg.ov.get("toolchain", {}).get("builtin_headers", {})
    gen.builtin_include = None
    if bh:
        bdir_inc = os.path.join(os.path.abspath(args.out), "toolchain-include")
        for name, rel in sorted(bh.items()):
            target = os.path.join(SRC, rel)
            if not os.path.exists(target):
                gen.err(f"toolchain builtin header {rel} missing (tools/fetch.py)")
                continue
            link = os.path.join(bdir_inc, name)
            os.makedirs(os.path.dirname(link), exist_ok=True)
            if os.path.islink(link) and os.readlink(link) == target:
                continue
            if os.path.lexists(link):
                os.unlink(link)
            os.symlink(target, link)
        gen.builtin_include = bdir_inc
    gen.gen_root_abs = os.path.join(bdir, "gen")
    gen.bin_dir = os.path.join(bdir, "bin")
    gen.lib_dir = os.path.join(bdir, "lib")
    order = closure(gen, roots)
    # Host tools needed by generators, and their own closures (iterate:
    # building a tool's sources can require further tools).
    done_tools = set()
    while gen.tools_needed - done_tools:
        t = sorted(gen.tools_needed - done_tools)[0]
        done_tools.add(t)
        for n in closure(gen, [t]):
            if n not in order:
                order.append(n)
    for e in args.explain:
        c = gen.cc_module(e)
        print(json.dumps({k: (sorted(v) if isinstance(v, set) else v) for k, v in vars(c).items()
                          if not k.startswith("_") and k not in ("props", "sysprop")}, indent=1, default=str))
        if not c.headers_only:
            fl = gen.compile_flags(c)
            print("CXX:", " ".join(fl["cxx"]))
    if gen.errors:
        for e in gen.errors:
            print(f"bp2cmake: error: {e}", file=sys.stderr)
        sys.exit(1)
    emit(gen, order, os.path.abspath(args.out))
    comp = [n for n in order if not gen.cc[n].headers_only and gen.cc[n].srcs]
    print(f"bp2cmake: {cfg.arch}: {len(order)} modules in closure, {len(comp)} compiled, "
          f"{sum(len(gen.cc[n].srcs) for n in comp)} sources, {len(gen.tools_needed | gen.tools_external)} host tools"
          + (f" (from {cfg.host_tools_dir})" if cfg.host_tools_dir else ""))


if __name__ == "__main__":
    # Run as the importable module so generators.py (which imports bp2cmake)
    # shares its classes and exception types.
    import bp2cmake
    bp2cmake.main()
