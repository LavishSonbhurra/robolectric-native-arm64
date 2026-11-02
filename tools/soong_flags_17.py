"""Soong's global C/C++ flags for Android 17 trees, as a profile for
tools/soong_flags.py (config [variant] soong = "android17").

Copied from build/soong at android-17.0.0_r1: cc/config/global.go and
cc/config/clang.go. The assembly order in cc/compiler.go and cc/builder.go is
the same as in Android 16, so soong_flags.module_flags() is reused; only the
lists differ.

What the Android 17 lists change from Android 16:

* -Winit-self is gone. -Werror=bool-operation moved to the overridable list.
  -Werror=format-security (was device only), -Werror=multichar and
  -Werror=sizeof-pointer-memaccess are new.
* The noOverride list has fewer "-Wno-" entries and the ones new clangs need.
* -fcommon for third-party code now depends on the release flag
  RELEASE_SOONG_FNO_COMMON_FOR_3P_CODE (not set in cp2a, so -fcommon stays).
* -Wno-error=format and the -Wno-psabi group left the third-party list.
"""

COMMON_GLOBAL_CFLAGS = [
    "-O2",
    "-Wall", "-Wextra", "-Wpointer-arith", "-Wunguarded-availability",
    "-Werror=bool-operation", "-Werror=date-time", "-Werror=format-security",
    "-Werror=int-conversion", "-Werror=multichar", "-Werror=pragma-pack",
    "-Werror=pragma-pack-suspicious-include", "-Werror=sizeof-array-div",
    "-Werror=sizeof-pointer-memaccess", "-Werror=string-plus-int",
    "-Werror=unreachable-code-loop-increment",
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
    # CLANG_DEFAULT_DEBUG_LEVEL unset -> "-g" (soong_flags.debug_flags)
]

NO_OVERRIDE_GLOBAL_CFLAGS = [
    "-Werror=address-of-temporary", "-Werror=dangling", "-Werror=format-insufficient-args",
    "-Werror=fortify-source", "-Werror=incompatible-function-pointer-types",
    "-Werror=int-in-bool-context", "-Werror=int-to-pointer-cast", "-Werror=null-dereference",
    "-Werror=return-type", "-Werror=xor-used-as-pow",
    "-Wno-missing-field-initializers", "-Wno-packed-non-pod",
    "-Wno-error=tautological-constant-compare", "-Wno-implicit-int-float-conversion",
    "-Wno-tautological-overlap-compare", "-Wno-deprecated-copy",
    "-Wno-zero-as-null-pointer-constant", "-Wno-deprecated-anon-enum-enum-conversion",
    "-Wno-deprecated-enum-enum-conversion", "-Wno-error=pessimizing-move",
    "-Wno-non-c-typedef-for-linkage", "-Wno-align-mismatch",
    "-Wno-error=unused-but-set-parameter", "-Wno-error=deprecated", "-Wno-error=invalid-offsetof",
    "-Wno-nontrivial-memcall", "-Wno-invalid-specialization",
    "-Wno-unterminated-string-initialization", "-Wno-implicit-int-conversion-on-negation",
    "-Wno-default-const-init-field-unsafe", "-Wno-default-const-init-var-unsafe",
    "-Wno-preferred-type-bitfield-enum-conversion", "-Wno-implicit-enum-enum-cast",
    "-Wno-character-conversion", "-Wno-error=uninitialized-const-pointer",
    "-Wno-incompatible-pointer-types", "-Wno-c2y-extensions",
    "-Wno-vla-cxx-extension", "-Wno-cast-function-type-mismatch",
]

EXTERNAL_CFLAGS = [
    "-Wno-enum-compare", "-Wno-enum-compare-switch", "-Wno-null-pointer-arithmetic",
    "-Wno-null-pointer-subtraction", "-Wno-string-concatenation",
    "-Wno-deprecated-non-prototype", "-Wno-unused", "-Wno-unused-but-set-variable",
    "-Wno-deprecated", "-Wno-tautological-constant-compare",
]

# -fcommon at the end: the VariableFunc appends it unless
# RELEASE_SOONG_FNO_COMMON_FOR_3P_CODE is set, which cp2a does not set.
NO_OVERRIDE_EXTERNAL_GLOBAL_CFLAGS = [
    "-Wno-format-insufficient-args", "-Wno-misleading-indentation",
    "-Wno-unused", "-Wno-unused-parameter", "-Wno-unused-but-set-parameter",
    "-Wno-unused-variable", "-Wno-unqualified-std-cast-call", "-Wno-array-parameter",
    "-Wno-gnu-offsetof-extensions", "-Wno-pessimizing-move", "-Wno-pointer-to-int-cast",
    "-fcommon",
]

ILLEGAL_FLAGS = {"-w", "-pedantic", "-pedantic-errors", "-Werror=pedantic", "-Wno-all", "-Wno-everything"}

EXPERIMENTAL_C_STD = "gnu2y"
