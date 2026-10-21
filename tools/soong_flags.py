"""Soong's global C/C++ compiler flags and their assembly order.

Copied from build/soong/cc/config/{global.go,x86_linux_host.go,clang.go} at the
pinned AOSP tag, for the host linux_glibc toolchain. For x86_64 that is
Soong's own linux_glibc x86_64 toolchain. Soong has no linux_glibc arm64
toolchain; for arm64 ours is the x86_64 one with the x86 specific bits
replaced (see ARCH_TOOLCHAINS). Flags that only make sense
with Soong's prebuilts (--gcc-toolchain, --sysroot) are dropped; docs/NOTES.md
lists every deviation.

The assembly order replicates cc/compiler.go compilerFlags + cc/builder.go
transformSourceToObj:

  cflags   = globalCommon globalC globalConly localCommon localC localConly system noOverride
  cppflags = globalCommon globalC globalCpp   localCommon localC localCpp   system noOverride
  asflags  = globalCommon globalAs            localCommon localAs           system
"""

import os
import re

# ---- cc/config/global.go ---------------------------------------------------

COMMON_GLOBAL_CFLAGS = [
    "-O2",
    "-Wall", "-Wextra", "-Winit-self", "-Wpointer-arith", "-Wunguarded-availability",
    "-Werror=date-time", "-Werror=int-conversion", "-Werror=pragma-pack",
    "-Werror=pragma-pack-suspicious-include", "-Werror=sizeof-array-div",
    "-Werror=string-plus-int", "-Werror=unreachable-code-loop-increment",
    "-Wno-error=deprecated-declarations",
    "-Wno-c23-extensions", "-Wno-c99-designator", "-Wno-gnu-folding-constant",
    "-Wno-inconsistent-missing-override", "-Wno-error=reorder-init-list", "-Wno-reorder-init-list",
    "-Wno-sign-compare", "-Wno-unused",
    "-DANDROID", "-DNDEBUG", "-UDEBUG", "-D__compiler_offsetof=__builtin_offsetof",
    "-D__ANDROID_UNAVAILABLE_SYMBOLS_ARE_WEAK__",
    "-faddrsig", "-fdebug-default-version=5", "-fcolor-diagnostics", "-ffp-contract=off",
    "-fno-exceptions", "-fno-strict-aliasing", "-fmessage-length=0", "-gsimple-template-names",
    "-gz=zstd", "-no-canonical-prefixes",
    # init(): runtime.GOOS == "linux"
    "-fdebug-prefix-map=/proc/self/cwd=",
    # CommonGlobalCflags VariableFunc: AUTO_*_INITIALIZE unset -> zero init
    "-ftrivial-auto-var-init=zero",
    # CLANG_DEFAULT_DEBUG_LEVEL unset -> "-g" (replaced by DEBUG_FLAGS below)
]

COMMON_GLOBAL_CONLYFLAGS = []

COMMON_GLOBAL_ASFLAGS = ["-D__ASSEMBLY__", "-fdebug-default-version=4"]

COMMON_GLOBAL_CPPFLAGS = [
    "-Wimplicit-fallthrough",
    "-D_LIBCPP_ENABLE_THREAD_SAFETY_ANNOTATIONS",
    "-Wno-gnu-include-next",
]

HOST_GLOBAL_CFLAGS = []
HOST_GLOBAL_CPPFLAGS = []

NO_OVERRIDE_GLOBAL_CFLAGS = [
    "-Werror=bool-operation", "-Werror=dangling", "-Werror=format-insufficient-args",
    "-Werror=implicit-int-float-conversion", "-Werror=int-in-bool-context",
    "-Werror=int-to-pointer-cast", "-Werror=pointer-to-int-cast", "-Werror=xor-used-as-pow",
    "-Wimplicit-int-float-conversion", "-Wno-void-pointer-to-enum-cast",
    "-Wno-void-pointer-to-int-cast", "-Wno-pointer-to-int-cast", "-Werror=fortify-source",
    "-Wno-unused-variable", "-Wno-missing-field-initializers", "-Wno-packed-non-pod",
    "-Werror=address-of-temporary", "-Werror=incompatible-function-pointer-types",
    "-Werror=null-dereference", "-Werror=return-type",
    "-Wno-tautological-constant-compare", "-Wno-tautological-type-limit-compare",
    "-Wno-implicit-int-float-conversion", "-Wno-tautological-overlap-compare",
    "-Wno-deprecated-copy", "-Wno-range-loop-construct", "-Wno-zero-as-null-pointer-constant",
    "-Wno-deprecated-anon-enum-enum-conversion", "-Wno-deprecated-enum-enum-conversion",
    "-Wno-error=pessimizing-move", "-Wno-non-c-typedef-for-linkage", "-Wno-align-mismatch",
    "-Wno-error=unused-but-set-variable", "-Wno-error=unused-but-set-parameter",
    "-Wno-error=deprecated-builtins", "-Wno-error=deprecated", "-Wno-error=invalid-offsetof",
    "-Wno-vla-cxx-extension", "-Wno-cast-function-type-mismatch",
]

NO_OVERRIDE_64_GLOBAL_CFLAGS = []

EXTERNAL_CFLAGS = [
    "-Wno-enum-compare", "-Wno-enum-compare-switch", "-Wno-null-pointer-arithmetic",
    "-Wno-null-dereference", "-Wno-pointer-compare", "-Wno-final-dtor-non-final-class",
    "-Wno-psabi", "-Wno-null-pointer-subtraction", "-Wno-string-concatenation",
    "-Wno-deprecated-non-prototype", "-Wno-unused", "-Wno-deprecated", "-Wno-error=format",
]

NO_OVERRIDE_EXTERNAL_GLOBAL_CFLAGS = [
    "-fcommon", "-Wno-format-insufficient-args", "-Wno-misleading-indentation",
    "-Wno-bitwise-instead-of-logical", "-Wno-unused", "-Wno-unused-parameter",
    "-Wno-unused-but-set-parameter", "-Wno-unqualified-std-cast-call", "-Wno-array-parameter",
    "-Wno-gnu-offsetof-extensions", "-Wno-pessimizing-move",
]

ILLEGAL_FLAGS = {"-w", "-pedantic", "-pedantic-errors", "-Werror=pedantic"}

C_STD = "gnu23"
CPP_STD = "gnu++20"
EXPERIMENTAL_C_STD = "gnu2x"
EXPERIMENTAL_CPP_STD = "gnu++2b"

# "Everything in these lists is a crime against abstraction" (global.go).
# Only the ones that exist are passed (PrefixedExistentPathsForSourcesVariable).
COMMON_GLOBAL_INCLUDES = [
    "system/core/include", "system/logging/liblog/include", "system/media/audio/include",
    "hardware/libhardware/include", "hardware/libhardware_legacy/include", "hardware/ril/include",
    "frameworks/native/include", "frameworks/native/opengl/include", "frameworks/av/include",
]

WARNING_ALLOWED_PROJECTS = ("device/", "vendor/")

# Behaviour switches (Android 16 values). tools/soong_flags_s.py changes them
# for Android 12 trees, see use_profile().
HOST_RTTI_FLAG = True        # cc/compiler.go: -frtti/-fno-rtti on every toolchain
WERROR_PREFIX = ["-Werror"]  # prepended when a module has neither -Werror nor -Wno-error
DEBUG_IN_COMMON = False      # "-g" comes from debug_flags(), not COMMON_GLOBAL_CFLAGS

# ---- cc/config/clang.go ----------------------------------------------------

CLANG_UNKNOWN_CFLAGS = {
    "-finline-functions", "-finline-limit=64", "-fno-canonical-system-headers", "-Wno-clobbered",
    "-fno-devirtualize", "-fno-tree-sra", "-fprefetch-loop-arrays", "-funswitch-loops",
    "-Wmaybe-uninitialized", "-Wno-error=clobbered", "-Wno-error=maybe-uninitialized",
    "-Wno-extended-offsetof", "-Wno-free-nonheap-object", "-Wno-literal-suffix",
    "-Wno-maybe-uninitialized", "-Wno-old-style-declaration", "-Wno-unused-local-typedefs",
    "-fdiagnostics-color", "-fuse-init-array", "-fgcse-after-reload", "-frerun-cse-after-loop",
    "-frename-registers", "-fno-strict-volatile-bitfields", "-fno-align-jumps",
    "-mthumb-interwork", "-fno-builtin-sin", "-fno-caller-saves", "-fno-early-inlining",
    "-fno-move-loop-invariants", "-fno-partial-inlining", "-fno-tree-copy-prop",
    "-fno-tree-loop-optimize", "-finline-limit=300", "-fno-inline-functions-called-once",
    "-mfpmath=sse", "-mbionic", "--enable-stdcall-fixup",
}

# ---- cc/config/x86_linux_host.go (x86_64), adapted for arm64 --------------

# linuxCflags, minus "--gcc-toolchain=${LinuxGccRoot}" (we use the system
# GCC runtime and glibc). linuxGlibcCflags ("--sysroot ...") is dropped for
# the same reason (the toolchain file passes our sysroot).
LINUX_CFLAGS = [
    "-Wa,--noexecstack",
    "-fPIC",
    "-fno-omit-frame-pointer",
    "-U_FORTIFY_SOURCE",
    "-D_FORTIFY_SOURCE=3",
    "-fstack-protector",
    "-fstack-protector-strong",
]
# Per architecture (RA64_ARCH):
#   cflags            tc.Cflags() after linuxCflags: linuxX8664Cflags
#                     ("-m64") for x86_64, nothing for arm64.
#   toolchain_cflags  tc.ToolchainCflags(): none for x86_64 (toolchainBase);
#                     Soong's only arm64 host toolchain (linux_bionic,
#                     arm64_linux_host.go) uses "-march=armv8-a".
#   ldflags           tc.Lldflags() after linuxLldflags: linuxX8664Ldflags
#                     minus the -B/-L paths into Soong's GCC prebuilt.
#   yasm              tc.YasmFlags() (LinuxX8664YasmFlags); arm64 has no
#                     .asm sources.
#   triple            tc.ClangTriple().
ARCH_TOOLCHAINS = {
    "arm64": {"cflags": [], "toolchain_cflags": ["-march=armv8-a"], "ldflags": [],
              "yasm": [], "triple": "aarch64-linux-gnu"},
    "x86_64": {"cflags": ["-m64"], "toolchain_cflags": [], "ldflags": ["-m64"],
               "yasm": ["-f", "elf64", "-m", "amd64"], "triple": "x86_64-linux-gnu"},
}


def toolchain(arch):
    if arch not in ARCH_TOOLCHAINS:
        raise ValueError(f"unsupported arch {arch} (have {', '.join(sorted(ARCH_TOOLCHAINS))})")
    return ARCH_TOOLCHAINS[arch]

# ---- choices that are ours, not Soong's -------------------------------------

# Soong passes -nostdinc++ and the include dirs of external/libcxx; we use
# the system libc++ instead (see docs/NOTES.md).
STL_CPPFLAGS = ["-stdlib=libc++"]
# With cmake/toolchain-sysroot.cmake, do what Soong does instead:
# -nostdinc++ plus our libc++ headers as a system include.
if os.environ.get("RA64_LIBCXX_INCLUDE"):
    STL_CPPFLAGS = ["-nostdinc++", "-isystem", os.environ["RA64_LIBCXX_INCLUDE"]]


PROFILES = ("android16", "android12")


def use_profile(name):
    """Switch the global flag tables to another Soong version: "android16"
    (the tables above) or "android12" (tools/soong_flags_s.py)."""
    if name in (None, "", "android16"):
        return
    if name != "android12":
        raise ValueError(f"unknown Soong flag profile {name} (have {', '.join(PROFILES)})")
    import soong_flags_s
    g = globals()
    for k, v in vars(soong_flags_s).items():
        if k.isupper():
            if k not in g:
                raise ValueError(f"soong_flags_s.{k} does not replace anything in soong_flags")
            g[k] = v


def debug_flags():
    if DEBUG_IN_COMMON:
        return []
    # Soong: "-g" unless CLANG_DEFAULT_DEBUG_LEVEL says otherwise.
    lvl = os.environ.get("AOSP_DEBUG_LEVEL", "g")
    return ["-g"] if lvl == "g" else ["-g" + lvl]


def filter_unknown(flags):
    return [f for f in flags if f not in CLANG_UNKNOWN_CFLAGS]


PATH_FLAGS = ("-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-I")


def absolutize(flags, src):
    """Soong runs the compiler from the source root, so relative paths in
    module flags are relative to it. We run from the build directory."""
    def fix(flag, path):
        if os.path.isabs(path):
            return path
        # -include/-imacros fall back to the include search path when the
        # file is not found relative to the working directory.
        if flag in ("-include", "-imacros") and not os.path.exists(os.path.join(src, path)):
            return path
        return os.path.join(src, path)

    out = []
    pending = None
    for f in flags:
        if pending:
            out.append(fix(pending, f))
            pending = None
            continue
        if f in PATH_FLAGS:
            out.append(f)
            pending = f
            continue
        for p in PATH_FLAGS:
            if f.startswith(p) and len(f) > len(p):
                f = p + fix(p, f[len(p):])
                break
        out.append(f)
    return out


_SHELL_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-=.,/")


def shell_args(flags):
    """What the compiler's argv becomes for module flags. Soong escapes them
    with proptools.NinjaAndShellEscapeList: a flag whose only unsafe
    characters are spaces is left unquoted (so the shell splits it, e.g.
    expat's "-include stdio.h"); any other unsafe character makes Soong
    single-quote the whole flag, keeping it one argument."""
    out = []
    for f in flags:
        if " " in f and all(ch in _SHELL_SAFE or ch == " " for ch in f):
            out += f.split()
        else:
            out.append(f)
    return out


# ---- cc/sanitize.go, host linux_glibc, SANITIZE_HOST unset ----------------

MINIMAL_RUNTIME_FLAGS = ("-fsanitize-minimal-runtime -fno-sanitize-trap=integer,undefined "
                         "-fno-sanitize-recover=integer,undefined")
INT_OVERFLOW_CFLAGS = ["-fsanitize-ignorelist=build/soong/cc/config/integer_overflow_blocklist.txt"]
HOST_ONLY_SANITIZE_FLAGS = ["-fno-sanitize-recover=all"]
UBSAN_MINIMAL_RUNTIME = "libclang_rt.ubsan_minimal"


def sanitizers(c):
    """(sanitizers, minimal_runtime) for the module, as sanitize.begin and
    sanitizerRuntimeMutator compute them. Only the UBSan family matters on a
    glibc host: address/thread/fuzzer/cfi are not used in this closure (an
    error is raised if they appear), hwasan/memtag/scs are bionic-only."""
    s = c.props.get("sanitize", {}) or {}
    if s.get("never"):
        return [], False
    for k in ("address", "thread", "fuzzer", "cfi", "safestack", "scudo"):
        if s.get(k):
            raise ValueError(f"{c.name}: sanitize.{k} is not supported")
    if (s.get("diag") or {}).get("undefined") or (s.get("diag") or {}).get("integer_overflow") \
            or (s.get("diag") or {}).get("misc_undefined"):
        raise ValueError(f"{c.name}: sanitize.diag (full UBSan runtime) is not supported")
    out = []
    if s.get("all_undefined"):
        out.append("undefined")
    else:
        if s.get("undefined"):
            out += ["bool", "integer-divide-by-zero", "object-size", "return",
                    "returns-nonnull-attribute", "shift-exponent", "unreachable", "vla-bound"]
        out += list(s.get("misc_undefined", []))
    if s.get("integer_overflow"):
        out += ["unsigned-integer-overflow", "signed-integer-overflow"]
    minimal = bool(s.get("integer_overflow") or s.get("misc_undefined") or s.get("undefined")
                   or s.get("all_undefined"))
    return out, minimal


def sanitize_cflags(c, local_cflags):
    """sanitize.flags(): appended to Local.CFlags after compiler, linker and
    stl flags."""
    s = c.props.get("sanitize", {}) or {}
    san, minimal = sanitizers(c)
    if not san:
        return []  # SanitizerEnabled false: no flags at all (not even blocklist)
    out = []
    from bp2cmake import SRC
    # Soong passes these paths relative to the source root (its cwd).
    if s.get("integer_overflow"):
        out += [f.replace("=", "=" + SRC + "/", 1) for f in INT_OVERFLOW_CFLAGS]
    out.append("-fsanitize=" + ",".join(san))
    # !Bionic: no vptr/function sanitizers in the host prebuilts.
    out.append("-fno-sanitize=vptr,function")
    out += HOST_ONLY_SANITIZE_FLAGS
    if minimal:
        out.append(MINIMAL_RUNTIME_FLAGS)
    allf = local_cflags + out

    def has_int(flags):
        return any(f.startswith("-fsanitize") and "integer" in f for f in flags)
    if not any("sanitize=implicit-integer-sign-change" in f for f in allf) and has_int(allf):
        out.append("-fno-sanitize=implicit-integer-sign-change")
    allf = local_cflags + out
    if not any("sanitize=unsigned-shift-base" in f for f in allf) and has_int(allf):
        out.append("-fno-sanitize=unsigned-shift-base")
    if s.get("recover"):
        out.append("-fsanitize-recover=" + ",".join(s["recover"]))
    if (s.get("diag") or {}).get("no_recover"):
        out.append("-fno-sanitize-recover=" + ",".join(s["diag"]["no_recover"]))
    if s.get("blocklist"):
        out.append("-fsanitize-ignorelist=" + os.path.join(SRC, c.dir, s["blocklist"]))
    return out


def module_flags(gen, c):
    from bp2cmake import ROOT, SRC, is_third_party, _uniq

    third_party = is_third_party(c.dir)
    gen_deps = list(c.gen_deps)
    tc = toolchain(gen.cfg.arch)

    # Global common flags
    g_common = []
    g_common += []  # instruction set flags: none
    g_common += LINUX_CFLAGS + tc["cflags"]  # tc.Cflags()
    g_common += COMMON_GLOBAL_CFLAGS + debug_flags() + HOST_GLOBAL_CFLAGS
    if third_party:
        g_common += EXTERNAL_CFLAGS
    g_common += tc["toolchain_cflags"]
    # Not Soong: make __FILE__ and debug paths relative to the source root,
    # as they are in a Soong build (which compiles with relative paths). The
    # checkout and the build directory are mapped too (the compilation
    # directory, sysroot headers), so the debug info, and with it the GNU
    # build-id, does not depend on where the tree lives. clang applies the
    # last matching map, so the more specific ones come later.
    g_common += [f"-ffile-prefix-map={ROOT}=.",
                 f"-ffile-prefix-map={os.path.dirname(gen.gen_root_abs)}=out",
                 f"-ffile-prefix-map={SRC}/=", f"-ffile-prefix-map={gen.gen_root_abs}/=out/gen/"]

    g_c = ["-target", tc["triple"]]
    if not c.dir.startswith("external/"):
        g_c.append("-DANDROID_STRICT")
    g_conly = list(COMMON_GLOBAL_CONLYFLAGS)
    g_cpp = list(COMMON_GLOBAL_CPPFLAGS) + list(HOST_GLOBAL_CPPFLAGS) + []  # tc.Cppflags() empty
    g_as = ["-target", tc["triple"]] + [] + COMMON_GLOBAL_ASFLAGS  # tc.Asflags() empty

    # Local common flags: include paths
    l_common = []
    if c.kind != "binary":
        l_common += ["-I" + d for d in c.export_include_dirs]
    l_common += ["-I" + d for d in c.local_include_dirs]
    l_common += ["-I" + d for d in c.include_dirs]
    if c.include_build_directory:
        l_common.append("-I" + os.path.join(SRC, c.dir))
    # compilerFlags order: proto, yacc, aidl, sysprop
    l_common += ["-I" + d for d in c.proto_dirs]
    l_common += ["-I" + d for d in c.yacc_dirs]
    l_common += ["-I" + d for d in c.aidl_dirs]
    for g in c.sysprop:
        l_common.append("-I" + g.local_include_dir)

    # Dependency exported include dirs, in Soong's dependency visit order:
    # header_libs, whole_static_libs, static_libs, shared_libs, generated
    # sources, generated headers.
    dep_inc = []
    dep_sys = []
    if c.aconfig:
        g = gen.genrule_for(c.name + "{aconfig}")
        dep_inc += g.include_dirs
    for lib in c.header_libs + c.whole_static_libs + c.static_libs + c.shared_libs:
        if not gen.is_cc(lib):
            continue
        i, s, d = gen.exports(lib)
        dep_inc += i
        dep_sys += s
        gen_deps += d
    for gname in c.generated_sources + c.generated_headers:
        g = gen.genrule_for(gname)
        dep_inc += g.include_dirs
    l_common += ["-I" + d for d in _uniq(dep_inc)]
    for d in _uniq(dep_sys):
        l_common += ["-isystem", d]

    # Local C flags
    cflags = shell_args([f for f in filter_unknown(c.cflags) if f not in ILLEGAL_FLAGS])
    cflags += shell_args(c.platform_cflags)
    san_flags = shell_args(sanitize_cflags(c, cflags))
    cppflags = shell_args([f for f in filter_unknown(c.cppflags) if f not in ILLEGAL_FLAGS])
    conlyflags = shell_args([f for f in filter_unknown(c.conlyflags) if f not in ILLEGAL_FLAGS])
    asflags = shell_args(list(c.asflags))
    if c.srcs:
        if "-Wno-error" not in cflags + cppflags and "-Werror" not in cflags + cppflags:
            if not c.dir.startswith(WARNING_ALLOWED_PROJECTS):
                cflags = WERROR_PREFIX + cflags

    def std(v, default, experimental):
        if not v:
            return default
        if v == "experimental":
            return experimental
        return v

    c_std = std(c.c_std, C_STD, EXPERIMENTAL_C_STD)
    cpp_std = std(c.cpp_std, CPP_STD, EXPERIMENTAL_CPP_STD)
    if c.gnu_extensions is False:
        c_std = c_std.replace("gnu", "c")
        cpp_std = cpp_std.replace("gnu", "c")
    conlyflags = ["-std=" + c_std] + conlyflags
    cppflags = ["-std=" + cpp_std] + cppflags
    if HOST_RTTI_FLAG:
        cppflags.append("-frtti" if c.rtti else "-fno-rtti")
    # Sanitizer flags are Local.CFlags appended after the compiler's own (and
    # after -Werror is prepended), so they follow the module cflags.
    cflags += san_flags
    # cc/stl.go: libc++ for host by default; stl "none" passes -nostdinc++.
    # AOSP clang's builtin stdatomic.h (overrides [toolchain]) must be found
    # before libc++'s <stdatomic.h> wrapper: libc++ 21's <atomic> refuses to
    # follow that wrapper before C++23 (LLVM 20, AOSP's, only checks for the
    # kill_dependency macro), so the directory goes ahead of the libc++
    # headers. For C, and with stl "none", it is searched last.
    builtin = ["-isystem", gen.builtin_include] if getattr(gen, "builtin_include", None) else []
    cppflags += ["-nostdinc++"] if c.stl == "none" else builtin + STL_CPPFLAGS

    # Per-module compatibility flags from overrides (clang 21 vs Soong's clang 20).
    # (Global compat flags live in their own response file, see bp2cmake.emit.)
    ov = gen.cfg.module_override(c.name)
    extra_common = list(ov.get("extra_cflags", []))
    extra_cpp = list(ov.get("extra_cppflags", []))

    sys_inc = []
    for d in COMMON_GLOBAL_INCLUDES:
        if os.path.isdir(os.path.join(SRC, d)):
            sys_inc.append("-I" + os.path.join(SRC, d))

    no_override = list(NO_OVERRIDE_GLOBAL_CFLAGS) + NO_OVERRIDE_64_GLOBAL_CFLAGS
    if third_party:
        no_override += NO_OVERRIDE_EXTERNAL_GLOBAL_CFLAGS

    cflags = absolutize(cflags, SRC)
    cppflags = absolutize(cppflags, SRC)
    conlyflags = absolutize(conlyflags, SRC)
    asflags = absolutize(asflags, SRC)

    # Not Soong flags: AOSP's clang resource-dir headers (overrides [toolchain]).
    c_line = g_common + g_c + g_conly + l_common + cflags + conlyflags + sys_inc + no_override + extra_common + builtin
    cxx_line = (g_common + g_c + g_cpp + l_common + cflags + cppflags + sys_inc + no_override + extra_common
                + extra_cpp + (builtin if c.stl == "none" else []))
    asm_line = g_common + g_as + l_common + asflags + [f for f in san_flags if f.startswith("-fsanitize=")] + sys_inc
    return {"c": c_line, "cxx": cxx_line, "asm": asm_line, "gen_deps": _uniq(gen_deps)}


def yasm_flags(gen, c):
    """cc/builder.go yasm rule: globalYasmFlags (tc.YasmFlags()) then
    localYasmFlags (cc/compiler.go: asflags, local_include_dirs,
    include_dirs, the module directory)."""
    from bp2cmake import SRC
    f = list(toolchain(gen.cfg.arch)["yasm"])
    f += shell_args(list(c.asflags))
    f += ["-I" + d for d in c.local_include_dirs]
    f += ["-I" + d for d in c.include_dirs]
    if c.include_build_directory:
        f.append("-I" + os.path.join(SRC, c.dir))
    return absolutize(f, SRC)


# ---- Link flags of a host cc_library_shared --------------------------------

# cc/config/global.go hostGlobalLldflags (= commonGlobalLldflags).
HOST_GLOBAL_LLDFLAGS = ["-fuse-ld=lld", "-Wl,--icf=safe", "-Wl,--no-demangle"]
# cc/config/x86_linux_host.go linuxLldflags, minus --gcc-toolchain and the
# linuxGlibcLdflags --sysroot (the toolchain file supplies a sysroot). The
# per-arch part (-m64 for x86_64) is ARCH_TOOLCHAINS ldflags.
LINUX_LLDFLAGS = ["-Wl,-z,noexecstack", "-Wl,-z,relro", "-Wl,-z,now", "-Wl,--no-undefined-version",
                  "-Wl,--compress-debug-sections=zstd"]


RPATHS = ["$ORIGIN/", "$ORIGIN/lib64", "$ORIGIN/../lib64", "$ORIGIN/../../lib64", "$ORIGIN/../../../lib64"]


def shared_link_flags(gen, c):
    """Global.LdFlags then Local.LdFlags in Soong's order (CommonLinkerFlags,
    libraryDecorator.linkerFlags, stl, baseLinker.linkerFlags). -shared and
    -soname come from CMake's SHARED library rule. The C++ runtime
    (stl libc++_static: -nostdlib++ plus the static archives) is added by
    ra64_link_runtime() in CMake."""
    from bp2cmake import SRC
    f = list(HOST_GLOBAL_LLDFLAGS)
    f.append("-Wl,--no-undefined")
    f += LINUX_LLDFLAGS + toolchain(gen.cfg.arch)["ldflags"]
    f += ["-ldl", "-lpthread", "-lm", "-lrt"]
    # RpathFlags() ($ORIGIN/, lib64, ../lib64, ../../lib64, ../../../lib64)
    # are set as the target's BUILD_RPATH, so CMake escapes $ORIGIN.
    if c.stl in ("libc++", "libc++_static", None):
        f.append("-nostdlib++")
    f += list(c.host_ldlibs)
    f += absolutize(shell_args(list(c.ldflags)), SRC)
    # version_script (-Wl,--version-script,<file>) is passed by
    # ra64_link_runtime(), which hands it to the toolchain's link policy.
    return f
