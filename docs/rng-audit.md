# Host-only commit audit (android-16.0.0_r1 to r4)

Question: besides `30eb173fa210` (patch 0001), which host-only or Robolectric
("[RNG]") changes does the official SDK 36 library (android-all
`16-robolectric-13921718`, build BLR2.250402.052) contain that our pin
`android-16.0.0_r1` lacks?

Answer: two more upstream commits, plus one hunk of a third as their
prerequisite. Applied as `patches/frameworks/base/0002` to `0004`. Everything
else is either absent from the official library or has no effect on a Linux
build. Three build-level differences that are not commits are listed at the
end; they need a decision.

## Scope and method

Commits listed:

* frameworks/base, every non-merge commit in `android-16.0.0_r1..r4` and
  `r1..main` touching `core/jni`, `libs/hwui`, `libs/androidfw`,
  `libs/hostgraphics`, `libs/nativehelper_jvm`, `native/`, `media/jni`
  (278 commits). The public `main` stops at 2025-03-26, so r4
  (android16-qpr2-release, 2025-11) is the newest source. Each diff was
  scanned for `__ANDROID__`/`__linux__`/`_WIN32`/`__APPLE__`/`__BIONIC__`
  branches, host files, layoutlib/Robolectric/Ravenwood and host Android.bp
  stanzas; all commits by the host graphics people (Hoisie, Moll, Gaillard,
  Sullivan) were taken regardless of path. Messages were grepped for `RNG`
  across the whole project: `30eb173fa210` is the only `[RNG]` commit.
* `android12-hostruntime-dev`, the SDK <= 34 Robolectric branch, for every
  project that has it (frameworks/base 213 commits, minikin, native,
  libnativehelper, system/core, skia, sqlite, icu, zlib, dng_sdk, protobuf,
  bionic, build/*), compared against what r1 already contains.
* r1..r4 of every other project in `config/projects.toml` (minikin,
  libnativehelper, frameworks/native, system/core, libbase, logging,
  libziparchive, sqlite, icu, skia, dng_sdk, the image and font libraries,
  hwbinder, hidl, vintf, cxx, fmtlib, wuffs, incremental_delivery,
  server_configurable_flags), by message and changed host files.

Sources: blobless partial clones from android.googlesource.com (git still
works without a login), history of reverted 2024 changes from the LineageOS
GitHub mirror, diffs for the patches from Gitiles `+/<sha>^!`.

Evidence comes from the official x86_64 library (extracted from the android-all jar, stripped) against
our x86_64 build of r1 (`build/x86_64`, unstripped, 37/37
pixel-identical in the rig): JNI tables (`tools/jni_tables.py`), strings,
call sites of imported functions, and disassembly of the functions a change
touches, found through JNI tables or the strings they reference. The helper
scripts are in `tools/audit/` (stdlib only, x86_64 ELF): `xref.py` (string
references and their functions), `pltcalls.py` (call sites of PLT imports),
`near.py` (strings used around an address), `jnifn.py` (function of a JNI
method), `strdiff.py` (strings in one library and not the other),
`callers.py`, and the commit filters `classify.py`, `hunks.py`, `inr1.py`.

## Result

| Commit | Title | Verdict | Evidence |
| --- | --- | --- | --- |
| `30eb173fa210` | [RNG] Bitmap::allocateHardwareBitmap() must copy source content | in official (patch 0001, earlier) | Official `allocateHardwareBitmap` = `allocateHeapBitmap` + `memcpy` (the android12-hostruntime-dev form `25874ec`); main's `readPixels` form is applied, equal for minimal row bytes. |
| `a86bb7e46466` | Make sqlite JNI available for host Mac and Windows in libandroid_runtime | **in official, applied (0003)** | CursorWindow fields after `mAshmemFd` are 8 bytes later in the official `writeToParcel` (`mData` at 0x18, r1 0x10): the added `unique_ptr<MappedFile>`. Official has 17 `mmap` / 16 `munmap` call sites, ours 19 / 18; matched by surrounding strings, the missing ones are `CursorWindow::maybeInflate`, `createFromParcel` (mmap) and `~CursorWindow`, `maybeInflate` (munmap). JNI table starts `nativeCreate, nativeDispose, nativeCreateFromParcel`. |
| `06b30aa5b930` (CursorWindow.cpp hunk only) | Update @CriticalNative usage for framework methods | **in official as far as observable, applied (0002)** | Host-neutral (`CRITICAL_JNI_PARAMS_COMMA` is `JNIEnv*, jclass,` on host) but sets the table order the official library has (`nativeAllocRow, nativeGetLong, nativeGetDouble, nativeClear, ...`); a86bb7e464 is written against it. The Trace/Perfetto hunks are not built for host, the Binder hunk changes nothing there. |
| `67ed6fce1304` | Remove call to `addHyphenator("am", 1, 1)` | **in official, applied (0004)** | Official `init()` builds the short strings `af`, `as`, `be` (`movw $0x6661/$0x7361/$0x6562`) with no `am` (`$0x6d61`) between them; the one `am` left is the alias to `und-Ethi`. r1 has both. |
| `c80d23f520c7` | Add defensive empty checks to CursorWindow.{writeTo,createFrom}Parcel | not in official | Official `writeToParcel` goes from the three header writes straight to `mAshmemFd != -1`; no `mNumRows == 0` branch and no extra `writeUint32`/`writeBool`. |
| `cb2d94a92fc8` | Print an informative message when trying to register an unsupported class | not in official | "Missing registration function for %s" / "Failed to register class %s" absent; `unordered_map::at` message present. |
| `8d01b954363e` | [Ravenwood] Stop flag hardcoding on native side | not in official | Host hwui flags stay hard-coded `false`: official `Properties::resampleGainmapRegions` calls `GetBoolProperty("debug.hwui.resample_gainmap_regions", false)`; with the commit the aconfig value (true in our release config) would be the default. |
| `6d61930c61f5` | Remove bracket missed in previous change | not in official | Fixes `f857605b88` (removes `early_preload_gl_context`), which the official lacks: "debug.hwui.early_preload_gl_context" is still there. |
| `a785a1bc9e` | [Ravenwood] Build our own libandroid_runtime | no effect on Linux (not applied) | Splits Android.bp into defaults + Ravenwood module; same static libraries for host libandroid_runtime; the dropped export lines name `__system_property_*`, which this library does not define (neither library exports them). |
| `4c8baf6fe9` | Update hostgraphics API of BufferQueue/BufferItemConsumer | not in official | Official exports the two-argument `BufferQueue::createBufferQueue(sp<IGraphicBufferProducer>*, sp<IGraphicBufferConsumer>*)`; the commit adds a `bool`. |
| `dfa285e051`, `60fcdc7dea`, `acaa1f8c58` | hostgraphics: detachBuffer stub; C++23 includes; warren_buffer flag cleanup | no effect on Linux (not applied) | Unused inline stub, includes, and preprocessor cleanup in a host-only header. |
| `3008d3c24c` | Use fontation SkTypeface backend | not in official | Host branch would default to Fontations; official text is pixel-identical to our FreeType path in the rig. |
| `1fed3c5` (minikin), `7b1afec` (logging), `5a1e746` (server_configurable_flags), `f50207b` (dng_sdk) | Windows/macOS build fixes | no effect on Linux | Other host OSes only. |
| `22c0248` (icu), `be5a893` (skia) | Ravenwood libicu; host_supported for libskia_skcms | no effect on this library | Build graph only. |
| `044e189` (libbase) | libbase: use ubsan on the host too | not in official | Official `WriteFully` is the same instruction sequence as ours (`addq`/`subq` with no overflow check); with the commit the `size_t` arithmetic would be instrumented. |
| `9bccb41` (sqlite) | Don't link liblog on the host | no effect on this library | `ENABLE_ANDROID_LOG` was already 0; liblog is linked into libandroid_runtime anyway. |
| `135b220` (libnativehelper) | Fix jniRegisterNativeMethods() to match the docs | not in official (not host-only either) | "RegisterNatives() != JNI_OK" absent; official keeps the `__android_log_print` form. |
| android12-hostruntime-dev, frameworks/base (213) | RNR registration, O to P JNI variants, Windows/Mac builds, backports | not applicable, except `25874ec` | Registration lives in `RobolectricNativeRuntime.cpp` (SDK <= 34 only); O to P variants would change JNI tables, which match r1. Behaviour backports are already in r1 (forceEndAnimators 10/10 lines, setElegantTextFlag 21/21, PathIterator 41/41, Path natives 63/63, Hyphenator via `ro.hyphen.data.dir`, sqlite `SQLITE_ENABLE_ICU` on host). Checked one that r1 lacks: `9662d03` (lazy ColorSpace lookups) is not in the official library; its ColorSpace lookups are in `register_android_graphics_Graphics` at the same relative offsets as ours. `1ac927d`, `bb2ce22`, `feb7808` touch files that do not exist at r1. |
| android12-hostruntime-dev, other projects | libnativehelper JVM fixes, sqlite ICU, minikin backports, ashmem-host Windows, rMoveTo (skia, 2021) | not applicable | Already in r1 (libnativehelper_jvm, `SQLITE_ENABLE_ICU` host stanza, upstream Skia) or Windows only. |

The official library is therefore r1 plus a hand-picked set of host fixes
from August 2025 (and an earlier form of 0001), not a later snapshot of
main: `c80d23f520`, merged the same week as `a86bb7e464`, is missing.

## Not commits: differences that need a decision

Found by comparing the strings of both libraries (`tools/audit/strdiff.py`).

1. **The official library was built as a debuggable product.** It contains
   minikin's `MINIKIN_ASSERT` messages ("Font collection must have at least
   one valid typeface", "!(start <= end)", about 25 more) and libbinder's
   recording and RPC debug code ("Started Binder recording.", "%s: No
   keepAliveBinder provided."), which exist only with
   `product_variables.debuggable` (`-DENABLE_ASSERTION` plus `Debug.cpp` in
   minikin, `-DBINDER_ENABLE_RECORDING -DBINDER_RPC_DEV_SERVERS` in
   libbinder; liblog and libhidl have debuggable stanzas too). Ours has the
   release-build strings instead ("Binder recording disallowed because
   recording is not enabled"). `overrides.toml` sets `debuggable = false`.
   Effect: minikin aborts on violated assertions in the official library,
   ours ignores them. `eng` could not be determined from the binary.
   **Settled (2026-10-19):** with `debuggable = true` all 47 of these
   strings appear and the three release-build counterparts disappear, on
   both architectures, with nothing moving the other way (strings only in
   the reference: 117 to 70); exports, JNI tables, rig and upstream suites
   unchanged. `overrides.toml` now sets `debuggable = true` (NOTES.md,
   "Debuggable product").
2. **libandroid_runtime's own fatal checks carry no message in the official
   library.** Every `LOG_ALWAYS_FATAL_IF` in `core/jni` (the `*OrDie`
   helpers of `jni_wrappers.h`, ImageReader's class init, and so on)
   compiles there to `__android_log_call_aborter("Fatal Error")`; 69 message
   strings and their log tags are missing. hwui and minikin keep their
   messages, so it is a per-module redefinition of `LOG_ALWAYS_FATAL_IF`.
   The string "Fatal Error" appears nowhere in our sources or in any
   r1..r4 diff, so the change is not public. Only abort messages differ. Not
   reproducible without the source; leave as is.
3. **libinput looks different.** Two groups of strings are only in ours:
   the `com.android.input.flags` names (`enable_multi_device_input` and 31
   more), which come from that library's test-mode aconfig code (r1 and r4
   both declare `mode: "test"` for `com.android.input.flags-aconfig-cc`),
   and the evdev label tables (`ABS_*`, `BTN_*`, `KEY_*`: 668 strings from
   the `toolbox_input_labels` genrule, used by
   `InputEventLookup::getLinuxEvdevLabel`). The key code labels of the same
   source file (`DPAD_CENTER`, ...) are in both. Either the official link
   pulls a different set of libinput objects or that library was generated
   differently; no public commit explains it. Runtime effect for Robolectric
   is probably nil (flag defaults are the same, evdev labels are debug
   output). Worth a look when the release config is next revisited.

Smaller string differences come from the toolchain (compiler-rt UBSan
messages, libc++abi's `__cxa_thread_atexit` fallback, Rust panic string
layout) and from 0001's `readPixels` form.

## Verification after applying 0002 to 0004

Both architectures rebuilt from clean (arm64 36 min, x86_64 36 min, `-j2`):
check-so OK (GLIBC_2.30), 226 exports identical, JNI tables identical to the
official library including order (1,328 methods). The x86_64 build has 17
`mmap` and 16 `munmap` call sites, as the official one. Rig: x86_64 build
37/37 images identical to the official goldens (max delta 0); arm64 build
33/33 tests, images identical to the previous arm64 run. Upstream 4.17
suites on arm64: robotests 7865/14, nativegraphics 767/1, ctesque 427/0,
the same outcomes as before except the HARDWARE bitmap test fixed by 0001
(details in NOTES.md, "Host commit audit").
