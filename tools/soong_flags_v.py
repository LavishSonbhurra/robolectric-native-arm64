"""Soong's global C/C++ flags for Android 15 (V) trees, as a profile for
tools/soong_flags.py (config [variant] soong = "android15").

Copied from build/soong at android-15.0.0_r1 (3fe78dc9b): cc/config/global.go,
cc/config/clang.go, cc/config/x86_linux_host.go, and cc/compiler.go. The order
of the lists is the same as in Android 16, so soong_flags.module_flags() is
reused. What differs from Android 16:

* the lists themselves (below): -D_FORTIFY_SOURCE=2, no
  -fno-omit-frame-pointer, gnu17, and warnings removed or added;
* cc/compiler.go adds -frtti/-fno-rtti only for bionic toolchains, so a
  linux_glibc host module gets neither (clang's default: RTTI on);
* "-pedantic" and friends are not illegal flags yet.

Deviations, because clang 21 no longer has these flags (Soong used
clang-r522817, clang 18):

* -fno-relaxed-template-template-args is dropped. Soong passes it as a
  workaround for its libc++ snapshot (b/341084395). clang 19 made relaxed
  matching the default and clang 21 removed the option; we build against
  libc++ 21.
* -Wno-error=enum-constexpr-conversion is dropped: the diagnostic became a
  hard error and the option is gone, so with -Werror it would fail the
  compile. Any code it covers shows up as a compile error.
"""

COMMON_GLOBAL_CFLAGS = [
    "-O2",
    "-Wall", "-Wextra", "-Winit-self", "-Wpointer-arith", "-Wunguarded-availability",
    "-Werror=date-time", "-Werror=int-conversion", "-Werror=pragma-pack",
    "-Werror=pragma-pack-suspicious-include", "-Werror=sizeof-array-div",
    "-Werror=string-plus-int", "-Werror=unreachable-code-loop-increment",
    "-Wno-error=deprecated-declarations",
    "-Wno-c99-designator", "-Wno-gnu-folding-constant",
    "-Wno-inconsistent-missing-override", "-Wno-error=reorder-init-list", "-Wno-reorder-init-list",
    "-Wno-sign-compare", "-Wno-unused",
    "-DANDROID", "-DNDEBUG", "-UDEBUG", "-D__compiler_offsetof=__builtin_offsetof",
    "-D__ANDROID_UNAVAILABLE_SYMBOLS_ARE_WEAK__",
    "-faddrsig", "-fdebug-default-version=5", "-fcolor-diagnostics", "-ffp-contract=off",
    "-fno-exceptions", "-fno-strict-aliasing", "-fmessage-length=0", "-gsimple-template-names",
    "-gz=zstd", "-no-canonical-prefixes", "-Wno-error=format",
    # init(): runtime.GOOS == "linux"
    "-fdebug-prefix-map=/proc/self/cwd=",
    # CommonGlobalCflags VariableFunc: AUTO_*_INITIALIZE unset -> zero init
    "-ftrivial-auto-var-init=zero",
    # CLANG_DEFAULT_DEBUG_LEVEL unset -> "-g" (soong_flags.debug_flags())
]

NO_OVERRIDE_GLOBAL_CFLAGS = [
    "-Werror=bool-operation", "-Werror=format-insufficient-args",
    "-Werror=implicit-int-float-conversion", "-Werror=int-in-bool-context",
    "-Werror=int-to-pointer-cast", "-Werror=pointer-to-int-cast", "-Werror=xor-used-as-pow",
    "-Wno-void-pointer-to-enum-cast", "-Wno-void-pointer-to-int-cast",
    "-Wno-pointer-to-int-cast", "-Werror=fortify-source",
    "-Wno-unused-variable", "-Wno-missing-field-initializers", "-Wno-packed-non-pod",
    "-Werror=address-of-temporary", "-Werror=incompatible-function-pointer-types",
    "-Werror=null-dereference", "-Werror=return-type",
    "-Wno-tautological-constant-compare", "-Wno-tautological-type-limit-compare",
    "-Wno-implicit-int-float-conversion", "-Wno-tautological-overlap-compare",
    "-Wno-deprecated-copy", "-Wno-range-loop-construct", "-Wno-zero-as-null-pointer-constant",
    "-Wno-deprecated-anon-enum-enum-conversion", "-Wno-deprecated-enum-enum-conversion",
    "-Wno-pessimizing-move", "-Wno-non-c-typedef-for-linkage", "-Wno-align-mismatch",
    "-Wno-error=unused-but-set-variable", "-Wno-error=unused-but-set-parameter",
    "-Wno-error=deprecated-builtins", "-Wno-error=deprecated",
    "-Wno-error=single-bit-bitfield-constant-conversion",
    "-Wno-error=invalid-offsetof", "-Wno-error=thread-safety-reference-return",
    "-Wno-deprecated-dynamic-exception-spec", "-Wno-vla-cxx-extension",
]

EXTERNAL_CFLAGS = [
    "-Wno-enum-compare", "-Wno-enum-compare-switch", "-Wno-null-pointer-arithmetic",
    "-Wno-null-dereference", "-Wno-pointer-compare", "-Wno-final-dtor-non-final-class",
    "-Wno-psabi", "-Wno-null-pointer-subtraction", "-Wno-string-concatenation",
    "-Wno-deprecated-non-prototype", "-Wno-unused", "-Wno-deprecated",
]

NO_OVERRIDE_EXTERNAL_GLOBAL_CFLAGS = [
    "-fcommon", "-Wno-format-insufficient-args", "-Wno-misleading-indentation",
    "-Wno-bitwise-instead-of-logical", "-Wno-unused", "-Wno-unused-parameter",
    "-Wno-unused-but-set-parameter", "-Wno-unqualified-std-cast-call", "-Wno-array-parameter",
    "-Wno-gnu-offsetof-extensions", "-Wno-fortify-source",
]

ILLEGAL_FLAGS = {"-w"}

C_STD = "gnu17"

# cc/config/x86_linux_host.go linuxCflags, minus --gcc-toolchain (see
# soong_flags.LINUX_CFLAGS).
LINUX_CFLAGS = [
    "-Wa,--noexecstack",
    "-fPIC",
    "-U_FORTIFY_SOURCE",
    "-D_FORTIFY_SOURCE=2",
    "-fstack-protector",
    "-fstack-protector-strong",
]

# cc/compiler.go: -frtti/-fno-rtti only with a bionic toolchain.
HOST_RTTI_FLAG = False
