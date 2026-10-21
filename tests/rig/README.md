# Fidelity rig (SDK 36, native graphics)

A small Android Gradle project that renders a fixed set of scenes with Robolectric 4.17
native graphics (`@Config(sdk = [36])`, `GraphicsMode.NATIVE`,
`robolectric.pixelCopyRenderMode=hardware`) and writes them to PNG. Two runs can then be
pixel-diffed. It checks the source-built Linux arm64 `libandroid_runtime.so` against the
official x86_64 one that Robolectric ships inside android-all.

The loader plugin the rig puts on the test classpath is the repository's own
[`loader/`](../../loader) project; `settings.gradle.kts` includes it, so a rig run always tests
the current loader sources (or, with `RIG_LOADER_JAR`, a prebuilt jar).

## Layout

| Path | What it is |
| --- | --- |
| `app/src/test/java/rig/fidelity/` | The scenes: `CanvasScenesTest`, `BitmapScenesTest`, `TextScenesTest`, `ViewScenesTest`, `ComposeScenesTest`, and `LoaderProbeTest`. |
| `app/src/test/resources/images/` | Decoder inputs (PNG RGBA/palette/gray, JPEG baseline/progressive, WebP lossy/lossless), made by `scripts/make-assets.py`. |
| `scripts/run.sh` | Runs the rig in one mode and writes `out/<mode>/`. |
| `scripts/compare.py` | Pixel diff of two output directories. |
| `goldens/x86_64/` | Reference output (37 PNG, 3 text files) from the official x86_64 library, mode `golden-x86`. |
| `baseline/arm64.json` | Per-image ceilings (largest channel delta, number of differing pixels) for the arm64 build against the goldens. Checked by `ci/check-baseline.py`. |

## Scenes

* Canvas: shapes with and without anti-aliasing, stroke widths, caps and joins, paths
  (cubic, quad, arcs, fill types, `Path.op`), path effects, linear/radial/sweep gradients in
  every tile mode, all 29 `BlendMode`s, colour filters, bitmap/compose/AGSL runtime shaders,
  blur mask filters and shadow layers, perspective matrices, clips and regions, layers,
  `Picture`, a Display P3 bitmap drawn into sRGB, `drawVertices` and `drawBitmapMesh`.
* Bitmap: nearest vs. bilinear vs. mipmap scaling, `BitmapFactory` and `ImageDecoder` for
  every input format, `inSampleSize`, `RGB_565`, density scaling, `BitmapRegionDecoder`,
  encode and decode round trips through PNG, JPEG (q80, q30) and WebP (lossy, lossless), and
  pixel configs (`RGB_565`, `RGBA_F16`, `ARGB_4444`, `ALPHA_8`, `extractAlpha`).
* Text: 13 font families, styles and weights, 6 to 64 px, paint flags (subpixel, linear,
  fake bold, skew, scale, letter spacing, OpenType features, variation settings), Arabic,
  Hebrew, Persian and mixed bidi, 12 scripts (Greek, Cyrillic, Devanagari, Bengali, Tamil,
  Thai, CJK, Vietnamese, Georgian, combining marks), colour emoji with ZWJ sequences and
  skin tones, hyphenation and line breaking for en-US and de-DE in three break strategies
  (with justification), underline, strike, outline, gradient text, text on a path, glyph
  outlines, spans, `drawTextRun`. Line breaks and font metrics also go to `.txt` files.
* Views: a framework-widget hierarchy (TextView, Button, CheckBox, RadioButton, Switch,
  SeekBar, ProgressBar, EditText, RatingBar, GradientDrawable, elevated rounded card, oval
  outline) in Material light and dark, each rendered with `View.draw` on a software canvas
  and with `PixelCopy` (hardware renderer path, real elevation shadows).
* Compose (BOM 2026.06.01, Material 3): a full Scaffold screen in light and dark, a graphics
  screen (Canvas drawing, shadows, clips, `graphicsLayer` with 3D rotation, `blur`), a text
  screen (families, weights, decorations, annotated strings, emoji, ellipsis, hyphenation,
  RTL, plus an AGSL `RuntimeShader`, which only the hardware path supports), and a lazy
  list. They are captured with a window `PixelCopy` (hardware renderer), not
  `captureToImage`, whose `forceRedraw` gives up after 2 s of wall time and times out under
  qemu. The lazy list is also captured with Roborazzi (`captureRoboImage` on the root node
  and `captureScreenRoboImage`), the way screenshot-test suites usually do it.

PNGs are written with `Bitmap.compress` (the native encoder), except the one Roborazzi file.
The compare script decodes before diffing, so encoder byte differences do not count.
Each output directory also has `_env.txt` (JVM, arch, which library was loaded),
`_loader.txt` (which `NativeRuntimeLoader` Robolectric chose and the file it loaded),
`_timing.txt` and `_junit/`.

## Requirements

* Gradle: the repository's wrapper (`../../gradlew`, Gradle 8.13), running on JDK 17 or 21.
* The Android SDK with `platforms;android-36` (`ANDROID_HOME`).
* A Java 21 JDK for the test JVM. SDK 36 needs Java 21: Robolectric's `DefaultSdkProvider`
  registers `BAKLAVA` with required Java version 21, and android-all 16 is compiled to class
  file version 65. `arm64` mode needs an aarch64 JDK, the two x86 modes an x86_64 JDK. By
  default `run.sh` looks in `.work/jdk/aarch64` and `.work/jdk/x64` (not committed).
* On an arm64 host: qemu-user with binfmt for x86_64 binaries, because AGP's `aapt2` exists
  for x86_64 Linux only. If the x86_64 C library is not installed system-wide, point
  `QEMU_LD_PREFIX` at an amd64 sysroot (`python3 -I toolchain/make-sysroot.py --arch amd64`
  builds one; `libc6-amd64-cross` with `/usr/x86_64-linux-gnu` also works). The x86 modes run
  the whole test JVM under qemu the same way.
* For `compare.py`: Python 3 with Pillow (no numpy).

## Running

```
scripts/run.sh <mode> [extra Gradle arguments]
```

| Mode | Test JVM | Loader and library |
| --- | --- | --- |
| `golden-x86` | x86_64 JDK 21 under qemu-user | stock `DefaultNativeRuntimeLoader`, official x86_64 library from android-all. Produces the goldens. |
| `x86-via-loader` | same | `LinuxArm64NativeRuntimeLoader`, forced to load the official x86_64 library from a file (or `RIG_X86_LIB`). Shows that the plugin renders exactly like the stock loader. |
| `arm64` | native aarch64 JDK 21 | `LinuxArm64NativeRuntimeLoader` with the arm64 library from `RIG_ARM64_LIB`, `RIG_LOADER_JAR` or `RA64_NATIVE_LIB`. |

Output goes to `out/<mode>/` (or `out/$RIG_OUT_NAME/`). Extra arguments go to Gradle, for
example `--tests 'rig.fidelity.TextScenesTest'`. The exit status is Gradle's.

Environment variables, all optional:

| Variable | Meaning |
| --- | --- |
| `RIG_ARM64_JDK`, `RIG_X64_JDK` | Java 21 homes for the test JVM (default `.work/jdk/aarch64`, `.work/jdk/x64`). |
| `RIG_ARM64_LIB` | `arm64`: load this `libandroid_runtime.so` through `-Drobolectric.arm64.nativeLibrary`. |
| `RIG_LOADER_JAR` | `arm64`: put this prebuilt loader jar on the test classpath instead of the `:loader` project. Use it to test the release jar, library bundled. |
| `RIG_COMPAT_JAR` | `arm64`: also put these compat jars (comma-separated) on the test classpath, for SDK 34 and below. Use it with `RIG_LOADER_JAR` and without `RIG_ARM64_LIB` to test the release jars. |
| `RIG_COMPAT_PIXELS` | `arm64`: `native` or `x86`, which compat jar the loader takes when both are on the classpath. |
| `RA64_NATIVE_LIB` | Read by the `:loader` project: bundle this library into its jar for the run, so it is loaded as a classpath resource. |
| `RIG_X86_LIB` | `x86-via-loader`: the x86_64 library to load (default: the official one, unpacked from android-all into `.work/x86lib/`). |
| `RIG_M2_REPO` | The local Maven repository Robolectric downloads android-all into (default `$HOME/.m2/repository`). |
| `RIG_SDK` | SDK level to run (default 36). Below 35 the SDK <= 34 compat library is used, and the goldens are `goldens/x86_64-sdk<N>`. |
| `RIG_OUT_NAME` | Output directory name under `out/` (default: the mode). |
| `GRADLE` | Gradle command (default `../../gradlew`). |
| `GRADLE_JAVA_HOME` | JDK that runs Gradle itself (default: `JAVA_HOME` as set). |
| `ANDROID_HOME` | Android SDK (`ANDROID_SDK_ROOT` or `sdk.dir` in `local.properties` also work). |
| `QEMU_LD_PREFIX` | amd64 sysroot for qemu-user (see Requirements). |
| `RIG_LOCK_FILE` | Hold an `flock` on this file during the Gradle run, to serialise with other builds. |
| `RIG_MIN_MEM_MB` | Wait until `MemAvailable` is at least this many MB before starting (default 0, off). |

Examples:

```
# The release jar, library inside (the path a user gets):
./gradlew :loader:jar -Pra64.nativeLib=$PWD/build/out/lib/libandroid_runtime.so     # repository root
RIG_LOADER_JAR=../../loader/build/libs/robolectric-nativeruntime-linux-aarch64-4.17-16-robolectric-13921718-1.jar \
  scripts/run.sh arm64

# A library file, loaded through the system property:
RIG_ARM64_LIB=/abs/path/libandroid_runtime.so scripts/run.sh arm64

# Compare with the goldens, then check the ceilings:
scripts/compare.py goldens/x86_64 out/arm64 --json out/arm64/_report.json
python3 -I ../../ci/check-baseline.py out/arm64/_report.json --baseline baseline/arm64.json
```

`out/arm64/_loader.txt` must name `robolectricarm64.LinuxArm64NativeRuntimeLoader` and say
where the library came from (`classpath resource via ...` for a bundled library, the file path
for `RIG_ARM64_LIB`).

Gradle runs with `--no-daemon`; `gradle.properties` sets one worker and modest heaps, so the
rig fits a 2 vCPU machine. The test JVM heap is `-Prig.heap` (default 1280m). The test JVM
gets `--add-opens` for `java.base/jdk.internal.access` and friends (Robolectric's
FileDescriptor interceptor fails without it on JDK 17+), and `java.io.tmpdir` is set to
`.work/tmp` (`-Prig.tmp`) so the roughly 60 MB Robolectric extracts per sandbox stays off a
RAM-backed `/tmp`. The Gradle properties behind `run.sh` (`rig.java`, `rig.out`,
`rig.nativeLib`, `rig.loaderJar`, `rig.stock`, `rig.heap`, `rig.tmp`) are documented in
`app/build.gradle.kts` and can be passed to `./gradlew -p tests/rig :app:testDebugUnitTest`
directly.

`compare.py` prints, per file, the largest channel delta, the number of differing pixels,
the number above `--tolerance`, and writes `<name>-diff.png` (reference, candidate, diff
side by side) into `CANDIDATE/_diff/`. Text files are compared line by line. It exits 1 on
any difference above the tolerance; the arm64 build is held to `baseline/arm64.json`
instead of a single tolerance.

## Results

Measured on a 2 vCPU arm64 VM (Ampere), Temurin 21.

| Run | Outcome | Wall time |
| --- | --- | --- |
| `golden-x86` (official x86_64 library, stock loader, qemu-user) | 33 tests pass, 37 PNGs + 3 text files, saved as `goldens/x86_64/` | 558 s |
| `x86-via-loader` (official x86_64 library through the plugin) | 37/37 PNGs and 3/3 text files identical to the goldens, max delta 0 (two runs) | 540 s |
| `x86-via-loader` with `RIG_X86_LIB` = this repository's x86_64 build | 37/37 PNGs and 3/3 text files identical to the goldens, max delta 0 | 572 s |
| `arm64` (this repository's arm64 build) | 28/37 PNGs and 3/3 text files identical; the other nine within `baseline/arm64.json` | about 40 s after the first build |
| `arm64` with the stock loader (`-Prig.stock`) | `AssertionError: The Robolectric native runtime is not supported on Linux (aarch64)` | 44 s |
| `arm64` without a library | `AssertionError: No Linux arm64 Robolectric native runtime found. Put native/linux/aarch64/libandroid_runtime.so on the test runtime classpath, or set -Drobolectric.arm64.nativeLibrary=...` | 46 s |

Under qemu the first test of each test class's sandbox costs 110 to 150 s (sandbox
creation, loading android-all, `JNI_OnLoad`); later tests take 1 to 10 s each. The goldens
are deterministic: independent qemu runs and the forced-loader runs match bit for bit.

The nine arm64 images that differ: `bitmap-scaling-filters` (max delta 29, a rotated
bilinear bitmap), `canvas-transforms-clips` (135 in 8 pixels, a perspective shader sample
landing on the neighbouring texel), and seven images with deltas of 1 to 4 levels
(`canvas-blend-modes`, `canvas-color-filters`, `canvas-gradients`, `canvas-shaders`,
`compose-graphics`, `compose-material-light`, `text-effects`). They come from Skia's NEON code
paths (the legacy fixed-point sampler, NEON reciprocal estimates, exact `div255`), not from
the build: the same sources built for x86_64 match the goldens exactly. See "Control
experiment" in [docs/NOTES.md](../../docs/NOTES.md).

Known content quirks, all deterministic: one Emoji 13 character renders as tofu because the
bundled `NotoColorEmoji.ttf` in `nativeruntime-dist-compat` predates it, and the
software-canvas View captures have no elevation shadows or outline clipping (only the
`PixelCopy` ones do).
