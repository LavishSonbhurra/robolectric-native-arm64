"""Code generation steps referenced by cc modules.

Each function returns a bp2cmake.Gen describing one custom command: its
outputs, which of them are compilable sources, exported include dirs, inputs
and the command lines. Soong's equivalents are cited per generator.
"""

import os
import re
import shlex

import bp2cmake as b
from bp2cmake import Gen, GenError, SRC, expand_globs

# Host tools. Names are CMake-level paths/targets defined in
# cmake/host_tools.cmake (Rust tools built by cargo) or cc_binary_host
# modules built by the generated CMake itself.
ACONFIG_TARGET = "aconfig_tool"


def aconfig_path(gen):
    return gen.cfg.vars["binary_dir"] + "/rust/target/release/aconfig"


def make(gen, name):
    if "{" in name:
        base, rest = name.split("{", 1)
        rest = rest.rstrip("}")
        kind, _, arg = rest.partition(":")
        if kind == "aconfig":
            return aconfig_cc(gen, base, name)
        if kind == "sysprop":
            return sysprop_cc(gen, base, arg, name)
        if kind == "yacc_lex":
            return yacc_lex(gen, base, arg, name)
        if kind == "proto":
            return proto_cc(gen, base, arg, name)
        if kind == "aidl_cc":
            return aidl_cc(gen, base, name)
        raise GenError(f"unknown generator kind {kind} in {name}")
    m = gen.index.get(name)
    if m is None:
        raise GenError(f"generator module {name} not found")
    mtype, props = gen.res.resolve(name)
    if mtype in ("genrule", "cc_genrule"):
        return genrule(gen, name, m, props)
    if mtype == "aidl_gen":
        return aidl_gen(gen, name, props)
    raise GenError(f"{name} ({m.where()}): unsupported generator module type {mtype}")


# ---- aconfig (build/soong/aconfig) -----------------------------------------

def aconfig_value_files(gen, package):
    """Value files for one package, in RELEASE_ACONFIG_VALUE_SETS order."""
    files = []
    for vs in gen.cfg.release.value_sets:
        m = gen.index.get(vs)
        if m is None:
            gen.cfg.warn(f"aconfig value set {vs} not found")
            continue
        _, props = gen.res.resolve(vs)
        value_mods = list(props.get("values", []))
        for bpf in expand_globs(m.dir, props.get("srcs", []), [], vs):
            d = os.path.relpath(os.path.dirname(bpf), SRC)
            value_mods += [x.name for x in gen.index.by_dir.get(d, []) if x.type == "aconfig_values"]
        for vm in value_mods:
            vmod = gen.index.get(vm)
            _, vprops = gen.res.resolve(vm)
            if vprops.get("package") != package:
                continue
            files += expand_globs(vmod.dir, vprops.get("srcs", []), [], vm)
    return files


def aconfig_cc(gen, lib, gname):
    """cc_aconfig_library: aconfig create-cache (aconfig/init.go aconfigRule)
    then create-cpp-lib --mode <mode> (aconfig/codegen/init.go cppRule)."""
    _, lprops = gen.res.resolve(lib)
    decl_name = lprops["aconfig_declarations"]
    dm = gen.index.get(decl_name)
    if dm is None:
        raise GenError(f"{lib}: aconfig_declarations {decl_name} not found")
    _, dprops = gen.res.resolve(decl_name)
    package = dprops["package"]
    decls = expand_globs(dm.dir, dprops.get("srcs", []), [], decl_name)
    values = aconfig_value_files(gen, package)
    rel = gen.cfg.release
    default_perm = rel.flag("RELEASE_ACONFIG_FLAG_DEFAULT_PERMISSION") or ""
    require_ro = rel.flag("RELEASE_ACONFIG_REQUIRE_ALL_READ_ONLY")
    mode = lprops.get("mode", "production")
    g = Gen(gname, "aconfig")
    d = gen.gendir(lib)
    cache = os.path.join(d, "intermediate.pb")
    basename = package.replace(".", "_")
    cc = os.path.join(d, basename + ".cc")
    hdr = os.path.join(d, "include", basename + ".h")
    cmd = [aconfig_path(gen), "create-cache", "--package", package]
    if dprops.get("container"):
        cmd += ["--container", dprops["container"]]
    for f in decls:
        cmd += ["--declarations", f]
    for f in values:
        cmd += ["--values", f]
    if default_perm:
        cmd += ["--default-permission", default_perm]
    if require_ro is not None:
        cmd += ["--allow-read-write", "true" if require_ro == "" else "false"]
    cmd += ["--cache", cache]
    g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", d], cmd,
                  [aconfig_path(gen), "create-cpp-lib", "--mode", mode, "--cache", cache, "--out", d]]
    g.outputs = [cc, hdr]
    g.sources = [cc]
    g.headers = [hdr]
    g.include_dirs = [os.path.join(d, "include")]
    g.inputs = decls + values
    g.tools = [ACONFIG_TARGET]
    return g


# ---- sysprop in cc srcs (cc/gen.go genSysprop) -----------------------------

def sysprop_cc(gen, mod, rel, gname):
    m = gen.index.get(mod)
    d = os.path.join(gen.gendir(mod), "sysprop")
    src = os.path.join(SRC, m.dir, rel)
    hdr = os.path.join(d, "include", rel + ".h")
    phdr = os.path.join(d, "public", "include", rel + ".h")
    cpp = os.path.join(d, rel + ".cpp")
    g = Gen(gname, "sysprop")
    tool = host_tool(gen, "sysprop_cpp")
    g.commands = [[tool[0], f"--header-dir={os.path.dirname(hdr)}",
                   f"--public-header-dir={os.path.dirname(phdr)}",
                   f"--source-dir={os.path.dirname(cpp)}", f"--include-name={rel}.h", src]]
    g.outputs = [cpp, hdr, phdr]
    g.sources = [cpp]
    g.headers = [hdr, phdr]
    g.include_dirs = [os.path.join(d, "include")]
    g.local_include_dir = os.path.join(d, "include")
    g.inputs = [src]
    g.tools = [t for t in [tool[1]] if t]
    return g


# ---- yacc / lex in cc srcs (cc/gen.go genYacc, genLex) ---------------------

def yacc_lex(gen, mod, rel, gname):
    m = gen.index.get(mod)
    _, props = gen.res.resolve(mod)
    src = os.path.join(SRC, m.dir, rel)
    base, ext = os.path.splitext(rel)
    ydir = os.path.join(gen.gendir(mod), "yacc")
    g = Gen(gname, "yacc_lex")
    g.inputs = [src]
    if ext in (".y", ".yy"):
        out = os.path.join(ydir, m.dir, base + (".cpp" if ext == ".yy" else ".c"))
        hdr = os.path.join(ydir, m.dir, base + ".h")
        flags = list(props.get("yacc", {}).get("flags", []))
        g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", os.path.dirname(out)],
                      [gen.cfg.vars["bison"], "-d", *flags, f"--defines={hdr}", "-o", out, src]]
        g.outputs = [out, hdr]
        loc = props.get("yacc", {})
        if loc.get("gen_location_hh"):
            g.outputs.append(os.path.join(os.path.dirname(out), "location.hh"))
        if loc.get("gen_position_hh"):
            g.outputs.append(os.path.join(os.path.dirname(out), "position.hh"))
    else:
        out = os.path.join(gen.gendir(mod), "lex", m.dir, base + (".cpp" if ext == ".ll" else ".c"))
        flags = list(props.get("lex", {}).get("flags", []))
        g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", os.path.dirname(out)],
                      [gen.cfg.vars["flex"], *flags, "-o" + out, src]]
        g.outputs = [out]
    g.sources = [out]
    g.include_dirs = []
    return g


# ---- genrule (genrule/genrule.go) ------------------------------------------

def host_tool(gen, name):
    """(command path, CMake target) for a tool used by a generator."""
    ov = gen.cfg.ov.get("tool", {}).get(name)
    if ov:
        return (ov["path"].format(**gen.cfg.vars), ov.get("target", ""))
    m = gen.index.get(name)
    if m is None:
        raise GenError(f"host tool {name} not found")
    mtype = gen.res.resolve(name)[0]
    if mtype in ("cc_binary_host", "cc_binary"):
        if gen.cfg.host_tools_dir:
            # Cross build: a native build of the same tree provides the tool.
            path = os.path.join(gen.cfg.host_tools_dir, name)
            if not os.access(path, os.X_OK):
                raise GenError(f"host tool {name} not found in {gen.cfg.host_tools_dir}")
            gen.tools_external.add(name)
            return (path, "")
        gen.tools_needed.add(name)
        return (os.path.join(gen.bin_dir, name), b.tid(name))
    raise GenError(f"host tool {name} ({m.where()}) has type {mtype}; map it in overrides [tool.{name}]")


def genrule(gen, name, m, props):
    g = Gen(name, "genrule")
    d = gen.gendir(name)
    outs = [os.path.join(d, o) for o in props.get("out", [])]
    srcs = []
    for s in props.get("srcs", []):
        if s.startswith(":"):
            srcs += gen.module_ref(s[1:], m.dir)
            ref = s[1:].split("{")[0]
            if gen.res.resolve(ref)[0] != "filegroup":
                g.depends_gens = getattr(g, "depends_gens", []) + [ref]
        else:
            srcs += expand_globs(m.dir, [s], props.get("exclude_srcs", []), name)
    tools = {}
    tool_targets = []
    for t in props.get("tools", []):
        path, target = host_tool(gen, t)
        tools[t] = path
        if target:
            tool_targets.append(target)
    tool_files = {}
    for t in props.get("tool_files", []):
        if t.startswith(":"):
            files = gen.module_ref(t[1:], m.dir)
            tool_files[t] = files[0] if files else ""
        else:
            tool_files[t] = os.path.join(SRC, m.dir, t)
    cmd = props.get("cmd", "")

    def loc(mt):
        label = (mt.group(2) or "").strip()
        many = mt.group(1) == "locations"
        if not label:
            if tools:
                return next(iter(tools.values()))
            if tool_files:
                return next(iter(tool_files.values()))
            raise GenError(f"{name}: $(location) without tools")
        if label in tools:
            return tools[label]
        if label in tool_files:
            return tool_files[label]
        if label.startswith(":"):
            files = gen.module_ref(label[1:], m.dir)
            return " ".join(shlex.quote(f) for f in (files if many else files[:1]))
        p = os.path.join(SRC, m.dir, label)
        return p

    def subst(text):
        text = text.replace("$$", "\0DOLLAR\0")
        text = re.sub(r"\$\((location|locations)(?:\s+([^)]*))?\)", loc, text)
        text = text.replace("$(in)", " ".join(shlex.quote(s) for s in srcs))
        text = text.replace("$(out)", " ".join(shlex.quote(o) for o in outs))
        text = text.replace("$(genDir)", shlex.quote(d))
        if "$(depfile)" in text:
            text = text.replace("$(depfile)", shlex.quote(os.path.join(d, "genrule.d")))
        if re.search(r"\$\(", text):
            raise GenError(f"{name}: unsupported genrule substitution in {text!r}")
        return text.replace("\0DOLLAR\0", "$")

    g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", d], subst(cmd)]
    g.workdir = SRC
    g.outputs = outs
    g.sources = [o for o in outs if os.path.splitext(o)[1] in (".c", ".cc", ".cpp", ".cxx", ".S", ".s")]
    g.headers = [o for o in outs if o not in g.sources]
    eid = props.get("export_include_dirs")
    g.include_dirs = [os.path.join(d, x) for x in eid] if eid else [d]
    g.inputs = srcs + list(tool_files.values())
    g.tools = tool_targets
    return g


# ---- aidl_interface code generation (system/tools/aidl/build) --------------

def _aidl_srcs(gen, it, version):
    r = it.srcs_for_version(SRC, version)
    if r is None:
        # srcs given through filegroups: paths are relative to local_include_dir.
        root = os.path.join(SRC, it.dir, it.p.get("local_include_dir", ""))
        files = []
        for pat in it.p.get("srcs", []):
            if pat.startswith(":"):
                files += gen.module_ref(pat[1:], it.dir)
            else:
                files += expand_globs(it.dir, [pat], [], it.name)
        return [(f, os.path.relpath(f, root)) for f in files], root
    return r


def _import_versions(it, version):
    """aidlInterface.getImports: name -> version key into preprocessed."""
    from aidl_interface import parse_versioned
    use_latest = (not it.unstable) and version != "" and version != it.next_version()
    out = {}
    for imp in it.imports_for_version(version):
        n, v = parse_versioned(imp)
        if v == "" and use_latest:
            v = "latest"
        out[n] = v
    return out


def aidl_preprocessed(gen, iface_name, version):
    """Path of <iface>/<version>/preprocessed.aidl, creating its Gen."""
    it = gen.aidl_ifaces[iface_name]
    if version == "latest":
        version = it.latest_version() if it.versions else it.next_version()
    elif version == "":
        version = it.next_version()
    gname = f"{iface_name}{{aidl_pre:{version}}}"
    if gname in gen.gens:
        return gen.gens[gname]
    srcs, root = _aidl_srcs(gen, it, version)
    out = os.path.join(gen.gendir(iface_name), version or "unversioned", "preprocessed.aidl")
    tool = host_tool(gen, "aidl")
    g = Gen(gname, "aidl_pre")
    cmd = [tool[0], "--preprocess", out]
    if not it.unstable:
        cmd.append("--structured")
    if it.p.get("stability"):
        cmd += ["--stability", it.p["stability"]]
    pre = []
    for n, v in _import_versions(it, version).items():
        if n in gen.aidl_ifaces:
            pg = aidl_preprocessed(gen, n, v)
            pre.append(pg)
    cmd += ["-p" + p.outputs[0] for p in pre]
    imports = _uniq_dirs([os.path.normpath(f[: len(f) - len(r)].rstrip("/")) for f, r in srcs])
    imports += [os.path.join(SRC, d) for d in it.p.get("include_dirs", [])]
    imports += [os.path.join(SRC, d) for d in it.p.get("include_dirs", [])]
    cmd += ["-I" + d for d in imports]
    cmd += [f for f, _ in srcs]
    g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", os.path.dirname(out)], cmd]
    g.outputs = [out]
    g.inputs = [f for f, _ in srcs] + [p.outputs[0] for p in pre]
    g.tools = [t for t in [tool[1]] if t]
    g.gen_deps = [p.name for p in pre]
    gen.gens[gname] = g
    return g


def _uniq_dirs(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def aidl_gen(gen, name, props):
    it = gen.aidl_ifaces[props["iface"]]
    version = props["version"]
    lang = props["lang"]
    srcs, root = _aidl_srcs(gen, it, version)
    d = gen.gendir(name)
    hdr_dir = os.path.join(d, "include")
    tool = host_tool(gen, "aidl")
    g = Gen(name, "aidl")
    pre = [aidl_preprocessed(gen, n, v) for n, v in _import_versions(it, version).items()
           if n in gen.aidl_ifaces]
    next_imports = _uniq_dirs([os.path.normpath(f[: len(f) - len(r)].rstrip("/")) for f, r in srcs])
    import_flags = ["-I" + os.path.join(SRC, x) for x in it.p.get("include_dirs", [])]
    flags = list(it.flags_for_version(version))
    hash_file = os.path.join(root, ".hash")
    if not it.unstable:
        flags += ["--structured", "--version", version or "1"]
        if os.path.exists(hash_file):
            with open(hash_file) as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            flags += ["--hash", lines[-1] if lines else "notfrozen"]
            g.inputs.append(hash_file)
        else:
            flags += ["--hash", "notfrozen"]
    if it.gen_trace(lang):
        flags.append("-t")
    if it.p.get("stability"):
        flags += ["--stability", it.p["stability"]]
    flags += ["--min_sdk_version", it.min_sdk(lang) or "current"]
    flags += ["-p" + p.outputs[0] for p in pre]
    if (version and version != "1" and not it.unstable and not os.path.exists(hash_file)
            and not gen.cfg.release.flag("RELEASE_AIDL_USE_UNFROZEN")):
        prev = str(int(version) - 1)
        prev_dir = os.path.join(SRC, it.dir, "aidl_api", it.name, prev)
        flags.append("--previous_api_dir=" + prev_dir)
        with open(os.path.join(prev_dir, ".hash")) as f:
            flags += ["--previous_hash", [ln for ln in f.read().splitlines() if ln.strip()][-1]]
    if it.p.get("backend", {}).get(lang, {}).get("gen_log"):
        flags.append("--log")
    prefix = "aidl" if lang == "ndk" else ""
    cmds = [[gen.cfg.vars["cmake"], "-E", "make_directory", hdr_dir]]
    for f, rel in srcs:
        out = os.path.join(d, os.path.splitext(rel)[0] + ".cpp")
        type_name = os.path.splitext(os.path.basename(rel))[0]
        pkg = os.path.dirname(rel)
        base = type_name
        if len(base) >= 2 and base[0] == "I" and base[1].isupper():
            base = base[1:]
        hdrs = [os.path.join(hdr_dir, prefix, pkg, n + ".h") for n in (type_name, "Bp" + base, "Bn" + base)]
        cmds.append([tool[0], f"--lang={lang}", *flags, "--ninja", "-d", out + ".d", "-h", hdr_dir,
                     "-o", d, *import_flags, *["-N" + x for x in next_imports], f])
        g.outputs.append(out)
        g.sources.append(out)
        g.headers += hdrs
        g.inputs.append(f)
    g.outputs += g.headers
    g.commands = cmds
    g.include_dirs = [hdr_dir]
    g.inputs += [p.outputs[0] for p in pre]
    g.tools = [t for t in [tool[1]] if t]
    g.gen_deps = [p.name for p in pre]
    return g


# ---- .aidl in cc srcs (cc/gen.go genAidl, cc/compiler.go aidl flags) -------

def aidl_flags(gen, mod, props):
    """flags.aidlFlags in compilerFlags order: aidl.flags, aidl.local_include_dirs,
    aidl.include_dirs, -t unless aidl.generate_traces is false,
    --min_sdk_version (MinSdkVersion(): min_sdk_version, else sdk_version,
    else "platform_apis")."""
    m = gen.index.get(mod)
    a = props.get("aidl", {})
    if a.get("libs"):
        raise GenError(f"{mod}: aidl.libs is not supported")
    flags = list(a.get("flags", []))
    flags += ["-I" + os.path.normpath(os.path.join(SRC, m.dir, d)) for d in a.get("local_include_dirs", [])]
    flags += ["-I" + os.path.normpath(os.path.join(SRC, d)) for d in a.get("include_dirs", [])]
    if a.get("generate_traces", True):
        flags.append("-t")
    ver = props.get("min_sdk_version") or ""
    if ver in ("", "apex_inherit"):
        ver = props.get("sdk_version") or ""
    flags.append("--min_sdk_version=" + (ver or "platform_apis"))
    return flags


def aidl_cc(gen, mod, gname):
    """One `aidl-cpp -d<dep> --ninja <flags> -I<base> <file> <outdir> <cpp>`
    per .aidl source. Headers I<Name>.h, Bn<Name>.h, Bp<Name>.h land in
    gen/aidl/<package>/ next to the .cpp, and gen/aidl is the include dir."""
    _, props = gen.res.resolve(mod)
    flags = aidl_flags(gen, mod, props)
    out_dir = os.path.join(gen.gendir(mod), "aidl")
    tool = host_tool(gen, "aidl-cpp")
    g = Gen(gname, "aidl_cc")
    cmds = []
    for f, rel in gen.aidl_cc_inputs[gname]:
        pkg = os.path.dirname(rel)
        base = os.path.splitext(os.path.basename(rel))[0]
        short = base[1:] if len(base) >= 2 and base[0] == "I" and base[1].isupper() else base
        cpp = os.path.join(out_dir, pkg, base + ".cpp")
        base_dir = f[: len(f) - len(rel)].rstrip("/")
        hdrs = [os.path.join(out_dir, pkg, n + ".h") for n in (base, "Bn" + short, "Bp" + short)]
        cmds.append([gen.cfg.vars["cmake"], "-E", "make_directory", os.path.join(out_dir, pkg)])
        cmds.append([tool[0], "-d" + cpp + ".d", "--ninja", *flags, "-I" + base_dir, f, out_dir, cpp])
        g.outputs.append(cpp)
        g.sources.append(cpp)
        g.headers += hdrs
        g.inputs.append(f)
    g.outputs += g.headers
    g.commands = cmds
    g.include_dirs = [out_dir]
    g.tools = [t for t in [tool[1]] if t]
    return g


# ---- .proto in cc srcs (cc/proto.go genProto, android/proto.go ProtoRule) ---

def proto_cc(gen, mod, rel_from_root, gname):
    """canonical_path_from_root defaults to true: protoc runs with -I . from
    the source root and outputs gen/proto/<path from root>.pb.{cc,h}, using
    aprotoc from external/protobuf like Soong."""
    _, props = gen.res.resolve(mod)
    m = gen.index.get(mod)
    pp = props.get("proto", {})
    if pp.get("canonical_path_from_root", True) is False:
        raise GenError(f"{mod}: proto.canonical_path_from_root: false is not supported")
    if pp.get("plugin"):
        raise GenError(f"{mod}: proto plugins are not supported")
    ptype = pp.get("type", "lite")
    pdir = os.path.join(gen.gendir(mod), "proto")
    base = os.path.splitext(rel_from_root)[0]
    cc = os.path.join(pdir, base + ".pb.cc")
    hdr = os.path.join(pdir, base + ".pb.h")
    flags = ["-I" + os.path.join(SRC, m.dir, d) for d in pp.get("local_include_dirs", [])]
    flags += ["-I" + os.path.join(SRC, d) for d in pp.get("include_dirs", [])]
    out_params = "lite:" if ptype == "lite" else ""
    g = Gen(gname, "proto")
    tool = host_tool(gen, "aprotoc")
    g.commands = [[gen.cfg.vars["cmake"], "-E", "make_directory", pdir],
                  [tool[0], f"--cpp_out={out_params}{pdir}", "-I", ".", *flags, rel_from_root]]
    g.tools = [t for t in [tool[1]] if t]
    g.workdir = SRC
    g.outputs = [cc, hdr]
    g.sources = [cc]
    g.headers = [hdr]
    g.include_dirs = [pdir]
    g.inputs = [os.path.join(SRC, rel_from_root)]
    return g
