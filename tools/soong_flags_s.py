"""Soong's global C/C++ flags for Android 12 (S) trees, as a profile for
tools/soong_flags.py (config [variant] soong = "android12").

Copied from build/soong at the compat pin (android12-hostruntime-dev,
82b104c4): cc/config/global.go, cc/config/clang.go,
cc/config/x86_linux_host.go, and the assembly order in cc/compiler.go and
cc/builder.go. The order of the lists is the same as in Android 16, so
soong_flags.module_flags() is reused; what differs is:

* the lists themselves (below);
* cc/compiler.go adds -frtti/-fno-rtti only for bionic toolchains, so a
  linux_glibc host module gets neither (clang's default: RTTI on);
* a module without -Werror/-Wno-error gets "-Wall -Werror" prepended (not
  just -Werror);
* there is no NoOverrideExternalGlobalCflags list;
* "-g" is part of commonGlobalCflags (no CLANG_DEFAULT_DEBUG_LEVEL).

Deviations, because the flags no longer exist in clang 21 (Soong used
clang-r416183b1, clang 12.0.7):

* "-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang"
  is dropped (removed in clang 16; -ftrivial-auto-var-init=zero no longer
  needs it);
* "-fexperimental-new-pass-manager" is dropped (removed in clang 15; the new
  pass manager is the only one).
"""

# cc/config/global.go commonGlobalCflags, then clang.go ClangExtraCflags,
# then the zero-init flag (CommonClangGlobalCflags VariableFunc). Unknown
# flags (ClangUnknownCflags: -fno-canonical-system-headers) are filtered by
# soong_flags.filter_unknown() at use.
COMMON_GLOBAL_CFLAGS = [
    "-DANDROID", "-fmessage-length=0", "-W", "-Wall", "-Wno-unused", "-Winit-self",
    "-Wpointer-arith", "-Wunreachable-code-loop-increment",
    "-no-canonical-prefixes",
    "-DNDEBUG", "-UDEBUG",
    "-fno-exceptions", "-Wno-multichar",
    "-O2", "-g", "-fdebug-info-for-profiling",
    "-fno-strict-aliasing",
    "-Werror=date-time", "-Werror=pragma-pack", "-Werror=pragma-pack-suspicious-include",
    "-Werror=string-plus-int", "-Werror=unreachable-code-loop-increment",
    # init(): android.BuildOs == android.Linux
    "-fdebug-prefix-map=/proc/self/cwd=",
    # ClangExtraCflags
    "-D__compiler_offsetof=__builtin_offsetof", "-faddrsig", "-fcommon", "-Werror=int-conversion",
    # "-fexperimental-new-pass-manager": dropped, see the module docstring.
    "-Wno-reserved-id-macro", "-Wno-unused-command-line-argument", "-fcolor-diagnostics",
    "-Wno-sign-compare", "-Wno-defaulted-function-deleted", "-Wno-inconsistent-missing-override",
    "-Wno-c99-designator", "-Wno-gnu-folding-constant", "-Wunguarded-availability",
    "-D__ANDROID_UNAVAILABLE_SYMBOLS_ARE_WEAK__",
    # AUTO_*_INITIALIZE unset: zero init. The companion -enable-trivial-...
    # flag is dropped, see the module docstring.
    "-ftrivial-auto-var-init=zero",
]

COMMON_GLOBAL_CONLYFLAGS = []

# compiler.go: Global.AsFlags = target, tc.ClangAsflags() (empty), -D__ASSEMBLY__
COMMON_GLOBAL_ASFLAGS = ["-D__ASSEMBLY__"]

# commonGlobalCppflags + ClangExtraCppflags
COMMON_GLOBAL_CPPFLAGS = [
    "-Wsign-promo",
    "-Wimplicit-fallthrough", "-D_LIBCPP_ENABLE_THREAD_SAFETY_ANNOTATIONS", "-Wno-gnu-include-next",
]

HOST_GLOBAL_CFLAGS = []
HOST_GLOBAL_CPPFLAGS = []

# noOverrideGlobalCflags + ClangExtraNoOverrideCflags
NO_OVERRIDE_GLOBAL_CFLAGS = [
    "-Werror=bool-operation", "-Werror=implicit-int-float-conversion", "-Werror=int-in-bool-context",
    "-Werror=int-to-pointer-cast", "-Werror=pointer-to-int-cast", "-Werror=string-compare",
    "-Werror=xor-used-as-pow", "-Wno-void-pointer-to-enum-cast", "-Wno-void-pointer-to-int-cast",
    "-Wno-pointer-to-int-cast", "-Werror=fortify-source",
    "-Werror=address-of-temporary", "-Werror=return-type",
    "-Wno-tautological-constant-compare", "-Wno-tautological-type-limit-compare",
    "-Wno-reorder-init-list", "-Wno-implicit-int-float-conversion", "-Wno-int-in-bool-context",
    "-Wno-sizeof-array-div", "-Wno-tautological-overlap-compare", "-Wno-deprecated-copy",
    "-Wno-range-loop-construct", "-Wno-misleading-indentation", "-Wno-zero-as-null-pointer-constant",
    "-Wno-deprecated-anon-enum-enum-conversion", "-Wno-deprecated-enum-enum-conversion",
    "-Wno-string-compare", "-Wno-enum-enum-conversion", "-Wno-enum-float-conversion",
    "-Wno-pessimizing-move", "-Wno-non-c-typedef-for-linkage", "-Wno-string-concatenation",
]

NO_OVERRIDE_64_GLOBAL_CFLAGS = []

# ClangExtraExternalCflags
EXTERNAL_CFLAGS = [
    "-Wno-enum-compare", "-Wno-enum-compare-switch", "-Wno-null-pointer-arithmetic",
    "-Wno-null-dereference", "-Wno-pointer-compare", "-Wno-xor-used-as-pow",
    "-Wno-final-dtor-non-final-class", "-Wno-psabi",
]

NO_OVERRIDE_EXTERNAL_GLOBAL_CFLAGS = []

ILLEGAL_FLAGS = {"-w"}

C_STD = "gnu99"
CPP_STD = "gnu++17"
EXPERIMENTAL_C_STD = "gnu11"
EXPERIMENTAL_CPP_STD = "gnu++2a"

COMMON_GLOBAL_INCLUDES = [
    "system/core/include", "system/logging/liblog/include", "system/media/audio/include",
    "hardware/libhardware/include", "hardware/libhardware_legacy/include", "hardware/ril/include",
    "frameworks/native/include", "frameworks/native/opengl/include", "frameworks/av/include",
]

# clang.go ClangUnknownCflags
CLANG_UNKNOWN_CFLAGS = {
    "-finline-functions", "-finline-limit=64", "-fno-canonical-system-headers", "-Wno-clobbered",
    "-fno-devirtualize", "-fno-tree-sra", "-fprefetch-loop-arrays", "-funswitch-loops",
    "-Werror=unused-but-set-parameter", "-Werror=unused-but-set-variable", "-Wmaybe-uninitialized",
    "-Wno-error=clobbered", "-Wno-error=maybe-uninitialized", "-Wno-error=unused-but-set-parameter",
    "-Wno-error=unused-but-set-variable", "-Wno-extended-offsetof", "-Wno-free-nonheap-object",
    "-Wno-literal-suffix", "-Wno-maybe-uninitialized", "-Wno-old-style-declaration",
    "-Wno-unused-but-set-parameter", "-Wno-unused-but-set-variable", "-Wno-unused-local-typedefs",
    "-Wunused-but-set-parameter", "-Wunused-but-set-variable", "-fdiagnostics-color",
    "-fuse-init-array", "-fgcse-after-reload", "-frerun-cse-after-loop", "-frename-registers",
    "-fno-strict-volatile-bitfields", "-fno-align-jumps", "-mthumb-interwork", "-fno-builtin-sin",
    "-fno-caller-saves", "-fno-early-inlining", "-fno-move-loop-invariants", "-fno-partial-inlining",
    "-fno-tree-copy-prop", "-fno-tree-loop-optimize", "-finline-limit=300",
    "-fno-inline-functions-called-once", "-mfpmath=sse", "-mbionic", "--enable-stdcall-fixup",
}

# x86_linux_host.go linuxClangCflags = filtered linuxCflags (-fdiagnostics-color
# is unknown) + -fstack-protector-strong, minus --gcc-toolchain/--sysroot.
LINUX_CFLAGS = [
    "-Wa,--noexecstack",
    "-fPIC",
    "-U_FORTIFY_SOURCE",
    "-D_FORTIFY_SOURCE=2",
    "-fstack-protector",
    "-D__STDC_FORMAT_MACROS",
    "-D__STDC_CONSTANT_MACROS",
    "-fstack-protector-strong",
]

# global.go hostGlobalLldflags; x86_linux_host.go linuxLdflags.
HOST_GLOBAL_LLDFLAGS = ["-fuse-ld=lld"]
LINUX_LLDFLAGS = ["-Wl,-z,noexecstack", "-Wl,-z,relro", "-Wl,-z,now", "-Wl,--no-undefined-version"]

# Behaviour switches read by soong_flags.module_flags().
HOST_RTTI_FLAG = False          # no -frtti/-fno-rtti on glibc hosts
WERROR_PREFIX = ["-Wall", "-Werror"]
DEBUG_IN_COMMON = True          # "-g" is in COMMON_GLOBAL_CFLAGS
