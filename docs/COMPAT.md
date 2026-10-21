# SDK 34 and below: librobolectric-nativeruntime.so for Linux arm64

Robolectric uses two native libraries. SDK 35 and later load `libandroid_runtime.so` from the
`android-all` jar (the rest of this repository). SDK 26 to 34 load `librobolectric-nativeruntime.so`
from `org.robolectric:nativeruntime-dist-compat`, which has no Linux arm64 build either. This
document covers the second one: the "compat" target.

## Source and pin

Google builds the compat library from AOSP's `android12-hostruntime-dev` branch. The branch moves,
so the pin is the generated superproject commit that matches the published 1.0.19 jar:

* `platform/manifest` `72b67c22773c160442d5a0576417bea51692e735` (project names and paths)
* `platform/superproject` `656d16be911b9cd102f94bd5a5f0ae494d82e567` (every project commit)

The module is `librobolectric-nativeruntime` in `frameworks/base/core/jni/Android.bp`. Inputs live
in `config/compat/` (`aosp.toml`, `projects.toml`, `sources.lock.json`, `overrides.toml`,
`patches/`), sources in `src-compat/`. `RA64_TARGET=compat` (CMake cache variable and environment
for the tools) switches every path; the default, `sdk36`, is unchanged.

The tree is Android 12: it builds with the tree's own libc++ (LLVM 12, `stl_module` in
`overrides.toml`) instead of the toolchain's, in Soong's link order, with Android 12's global
flags (`tools/soong_flags_s.py`). No AOSP source change is needed for the default build.

## Building

```
RA64_TARGET=compat python3 -I tools/fetch.py
cmake -S . -B build/compat -G Ninja -DRA64_TARGET=compat -DRA64_USE_SYSROOT=ON
ninja -C build/compat m_librobolectric-nativeruntime
```

or `ci/build-compat.sh`, which also strips the debug info into a separate file (the official
library keeps `.symtab` and drops the debug info; so does ours) and writes `dist-compat/`.

## Pixels: native (default) and x86 (opt-in)

Skia picks different code paths on arm64 (NEON) and on x86_64 (SSE), so some images differ from
x86 goldens by a few levels: anti-aliased edges, bitmap filtering, gradients. Google's own arm64
builds of these libraries (the macOS aarch64 files in the same jars) compile the same NEON paths,
so they should show the same kind of differences. That is reasoned from the code, not tested on a
Mac.

Whether Robolectric's maintainers accept or expect those differences is not known, so we ship
both, and we'll drop either if maintainers prefer:

* `RA64_PIXELS=native` (the default build and the default artifact,
  `robolectric-nativeruntime-compat-linux-aarch64`): the faithful arm64 build.
* `RA64_PIXELS=x86` (opt-in, artifact `robolectric-nativeruntime-compat-linux-aarch64-x86pixels`): Skia, hwui and the JNI library compile Skia's x86 SSSE3 code paths,
  the ones the x86_64 build runs, with the SSE intrinsics supplied in portable C by
  [SIMDe](https://github.com/simd-everywhere/simde) 0.8.2 (MIT, pinned by SHA-256 in
  `config/compat/projects.toml`). `rcpps`/`rsqrtps` are computed exactly, `-ffp-contract=off`
  (SSE has no fused multiply-add), and zlib hashes deflate input the way the x86_64 host build
  does. One Skia patch, `config/compat/patches/external/skia/0001`, makes seven arm64 shortcuts
  also require NEON; with NEON on it changes nothing.

Results on the fidelity rig (37 images and 3 text files, against Google's x86_64 library under
qemu):

| Build | SDK 30 identical | max delta | SDK 34 identical | max delta |
| --- | --- | --- | --- | --- |
| native | 17/37 | 47 | 16/37 | 171 |
| x86 | 37/37 | 0 | 37/37 | 0 |

The x86 mode costs no measurable time on the rig or on a 383-screenshot app suite.

Caveats for the x86 mode:

* The goldens come from qemu, which runs Skia's SSSE3 level (it never reports F16C, so Skia's
  Haswell path is not taken) and computes `rcpps`/`rsqrtps` exactly. Forcing the Haswell path
  under qemu gave identical images. Real Intel and AMD CPUs approximate `rcpps`/`rsqrtps`, each in
  their own way, and Skia uses them in the colorburn and colordodge blend modes and in perspective
  transforms. On real x86 hardware those can differ from the qemu goldens, and therefore from the
  x86 mode. Not tested on x86 hardware.

Text outputs: in the native build `bitmap-encode-sizes.txt` reports one PNG one byte larger,
because zlib uses the ARMv8 CRC32 instruction for its deflate hash on arm64. The x86 mode builds
zlib without it and matches. The rig baselines allow that line.

## AGSL uniforms at SDK 33 and 34 (Robolectric, not arm64)

`RuntimeShader.setFloatUniform(name, x, y)` and the other scalar setters never reach the native code
at SDK 33 and 34 in Robolectric 4.17: `ShadowNativeRuntimeShader` implements their native method,
`nativeUpdateUniforms(long, String, float, float, float, float, int)`, as a no-op (the int variants
too). Skia's `SkRuntimeShaderBuilder` allocates its uniform block with `SkData::MakeUninitialized`,
so the shader then reads whatever bytes the heap left there. The output depends on earlier
allocations and changes between runs, with Google's library as well as with ours.

Measured with the rig's AGSL box (`uniform float2 size`), ten runs of the Compose scenes at SDK 34
each: Google's x86_64 library under qemu drew the box black nine times and green once; our native
build drew it red eight times and black twice. The colours differ by architecture because the
input is undefined; they are not a fidelity difference of the library. The array setter, `setFloatUniform(name, float[])`, goes through
`nativeUpdateUniforms(long, String, float[], boolean)`, which the shadow forwards, and is not
affected. The rig uses it.

## Host maths library: glibc 2.41

Skia's SVG `arcTo` (path data `a`/`A`, used by VectorDrawable) calls `atan2f` and `tanf` from the
system libm. glibc 2.41 made these (and other single-precision functions) correctly rounded; 2.40
and older return approximations that also differ between x86_64 and aarch64. Rendering therefore
depends on the host's glibc, for Google's library as much as for ours.

Robolectric's `ShadowNativeVectorDrawableTest.testBasicVectorDrawables` has goldens from an older
glibc. On a host with glibc 2.41 or later it fails with 87 pixels over its tolerance (it allows
20), on either architecture: Google's x86_64 library on x86_64 with glibc 2.43 fails it with the
same image our arm64 library produces, and our x86_64 build passes it with glibc 2.39. It is in
`ci/upstream-expected-failures-compat.txt` for that reason.

## Using it

The loader plugin (`:loader`, artifact `robolectric-nativeruntime-linux-aarch64`, version
`4.17-16-robolectric-13921718-2` or later) handles both libraries. For SDK levels below 35 on
Linux aarch64 it loads the compat library from the test classpath. Two artifacts provide it, both
version `1.0.19-1` and without code:

| Artifact (`:project`) | Resource | Pixels |
| --- | --- | --- |
| `robolectric-nativeruntime-compat-linux-aarch64` (`:compat`) | `native/linux/aarch64/librobolectric-nativeruntime.so` | native NEON (default) |
| `robolectric-nativeruntime-compat-linux-aarch64-x86pixels` (`:compat-x86pixels`) | `native/linux/aarch64/x86-pixels/librobolectric-nativeruntime.so` | x86 |

Add one of them. If both are on the classpath the loader takes the native one, unless
`-Drobolectric.arm64.compatPixels=x86`; naming a build that is not on the classpath fails with a
clear message. The native build uses the path `nativeruntime-dist-compat` uses for x86_64, so
Robolectric's stock loader would find it too once it accepts Linux aarch64; the x86-pixels build
has its own path so that the two jars never shadow each other and the stock loader never picks it
up by accident. Separate artifacts rather than a classifier: each has its own POM, notices and
checksums, and a Gradle user adds either with a plain coordinate.

Fonts, ICU data and hyphenation data come from `nativeruntime-dist-compat`, which Robolectric
already depends on.

`-Drobolectric.arm64.nativeLibrary=/path/librobolectric-nativeruntime.so` together with
`-Drobolectric.arm64.nativeLibrarySdk=34` loads a file instead.

## Checks

* JNI tables against the official library: 76 tables, 906 methods, identical including order
  (`tools/jni_tables.py compare`).
* Exports: the official library has no version script and exports 13,610 symbols. The differences
  are template and inline copies whose emission depends on the compiler's inlining (all weak), the
  architecture's own libwebp entry points and `va_list` mangling, and `_init`/`_fini`, which are
  local in ours.
* Strings: the differences are compiler output (lambda type names, `__PRETTY_FUNCTION__` text) and
  two error strings clang 21 proved unreachable.
* NOTICE and licence check (`config/compat/notices-*.toml`): four licence kinds are acknowledged
  with written reasons, among them Skia's GIF decoder, which is MPL 1.1 / GPL 2.0 / LGPL 2.1 and is
  used under the MPL 1.1 as in Google's build.
* Upstream suites (robotests, nativegraphics, ctesque) at SDK 26 to 34 on arm64, compared per test
  with Google's library on x86_64 at SDK 30 and 34: the only differences are the known environment
  failures in `ci/upstream-expected-failures-compat.txt`.
