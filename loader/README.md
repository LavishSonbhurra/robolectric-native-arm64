# Loader plugin

`robolectricarm64.LinuxArm64NativeRuntimeLoader` is a Robolectric `NativeRuntimeLoader` plugin
that makes Robolectric 4.17 load a Linux arm64 `libandroid_runtime.so` for SDK 36, without
forking or patching Robolectric. This project builds the published jar:

| Entry | What |
| --- | --- |
| `robolectricarm64/LinuxArm64NativeRuntimeLoader.class` | The plugin, compiled for Java 17 against Robolectric 4.17. |
| `META-INF/services/org.robolectric.pluginapi.NativeRuntimeLoader` | Lets Robolectric's plugin lookup find it. |
| `native/linux/aarch64/libandroid_runtime.so` | The library, if one was given at build time. |
| `META-INF/THIRD_PARTY_NOTICES` | The notices file of the library build. |
| `META-INF/LICENSE`, `META-INF/LICENSE-robolectric.txt` | Apache-2.0 (this project) and the MIT License of the Robolectric code the loader follows. |

Maven coordinates: `io.github.lavishsonbhurra:robolectric-nativeruntime-linux-aarch64:4.17-16-robolectric-13921718-1`
(Robolectric version, android-all build, revision).

## Building

From the repository root, after building the library (`build/out/lib/libandroid_runtime.so`,
with `NOTICE` next to it):

```
./gradlew :loader:jar -Pra64.nativeLib=$PWD/build/out/lib/libandroid_runtime.so
# loader/build/libs/robolectric-nativeruntime-linux-aarch64-4.17-16-robolectric-13921718-1.jar
```

| Setting (Gradle property or environment variable) | Meaning |
| --- | --- |
| `ra64.nativeLib`, `RA64_NATIVE_LIB` | The library to bundle. It is checked to be a 64-bit little-endian aarch64 ELF file. Without it the jar contains only the plugin. |
| `ra64.nativeNotice`, `RA64_NATIVE_NOTICE` | The notices file to bundle (default: `NOTICE` next to the library, else `THIRD_PARTY_NOTICES` next to it). Required when a library is given. |

`:loader:sourcesJar` and `:loader:javadocJar` build the companion jars Maven Central needs, and
`:loader:publishToMavenLocal` installs all three with the POM. Publishing tasks refuse to run
without a library. Signing and the upload to Central are not part of this build.

## How Robolectric 4.17 finds libandroid_runtime

All of this is from the 4.17 sources (`org.robolectric:nativeruntime:4.17` and friends).

**Which SDK jar.** `org.robolectric.plugins.DefaultSdkProvider` maps SDK 36 (`BAKLAVA`) to
android version `16`, build `13921718`, required Java 21. `DefaultSdk.getAndroidSdkDependency()`
asks for `org.robolectric:android-all-instrumented:16-robolectric-13921718-i7`; the `-i7`
suffix is `"i" + PREINSTRUMENTED_VERSION` with `PREINSTRUMENTED_VERSION = 7`. With
`-Drobolectric.usePreinstrumentedJars=false` it asks for plain
`org.robolectric:android-all:16-robolectric-13921718` instead and instruments at run time.
Resolution goes through `org.robolectric.plugins.LegacyDependencyResolver`, which picks, in
order: a `robolectric-deps.properties` system property or classpath file
(`PropertiesDependencyResolver`), `robolectric.dependency.dir` or `robolectric.offline=true`
(`LocalDependencyResolver`, jars in that directory), and otherwise
`org.robolectric.internal.dependency.MavenDependencyResolver`. That one downloads from
`robolectric.dependency.repo.url` (default Maven Central) into the local Maven repository:
`maven.repo.local`, else `<localRepository>` from `~/.m2/settings.xml`, else
`~/.m2/repository`. The Gradle cache is not used for android-all; Gradle never sees it.

**Which loader.** For SDK 35 and above, `AndroidTestEnvironment.setUpApplicationState()` calls
`DefaultNativeRuntimeLoader.injectAndLoad()` up front when the graphics mode is NATIVE (or
SQLite needs it). `injectAndLoad()` builds an `org.robolectric.util.inject.Injector` on the
sandbox class loader and asks it for `org.robolectric.pluginapi.NativeRuntimeLoader`.
`PluginFinder` loads every implementation listed in
`META-INF/services/org.robolectric.pluginapi.NativeRuntimeLoader`, drops classes named by
`@Supersedes`, and returns the one with the highest `javax.annotation.Priority` (no
annotation counts as 0; a tie is an error). `DefaultNativeRuntimeLoader` is registered with
`@AutoService` and `@Priority(Integer.MIN_VALUE)`, so any other registered loader wins.

**How the stock loader loads.** `DefaultNativeRuntimeLoader.ensureLoaded()`:

1. `isSupported()` must be true, or it throws
   `AssertionError("The Robolectric native runtime is not supported on Linux (aarch64)")`.
   It accepts mac aarch64/x86_64, Linux x86_64 and Windows x86_64 only (`os.arch` `amd64`
   is normalised to `x86_64`).
2. It makes a `TempDirectory("nativeruntime")` under `java.io.tmpdir` and copies into it
   `fonts/` (from the classpath, which for SDK 36 means `nativeruntime-dist-compat`; it sets
   `robolectric.nativeruntime.fontdir`), `hyphen-data/` (from android-all), and the single
   `icu/icudt*.dat` in android-all (sets `icu.data.path` and `icu.locale.default`).
3. It sets `use_base_native_hostruntime=true`, `core_native_classes`,
   `graphics_native_classes` and `method_binding_format=$$robo$$${method}$nativeBinding`,
   which the library reads during `JNI_OnLoad` to decide what to register, and restores them
   afterwards.
4. `loadLibrary()` reads the resource `native/<os>/<arch>/libandroid_runtime.so`
   (`nativeLibraryPath()`; `<os>` is linux/mac/windows, `<arch>` is the normalised
   `os.arch`, so `aarch64` on arm64 Linux) with Guava `Resources.getResource`, which uses the
   context class loader (the `SandboxClassLoader`), copies it into the temp directory and
   calls `System.load` on the copy. Note that
   `InstrumentationConfiguration.shouldAcquireResource()` returns true for any resource name
   containing `android_runtime`, and `SandboxClassLoader.getResource()` then answers only
   from android-all (its `ResourceProvider`) and never asks the parent. So the library can
   only come from the android-all jar; a jar on the test classpath is invisible to this
   lookup.
5. It runs the deferred `__staticInitializer__` of `FontFamily`, `Path`, `PathIterator`,
   `Typeface`, `MeasuredText$Builder` and `ImageReader`, sets the native system property
   `ro.hyphen.data.dir`, then calls `Typeface.loadPreinstalledSystemFontMap()` and
   `Hyphenator.init()`.

There is no system property that overrides the library path in 4.17. The only properties
involved are the JNI registration ones above (set by the loader itself) and the dependency
resolution ones. The android-all 16 jar ships `native/linux/x86_64`, `native/mac/aarch64`,
`native/mac/x86_64` and `native/windows/x86_64`.

## What the plugin does

`LinuxArm64NativeRuntimeLoader extends DefaultNativeRuntimeLoader`, carries `@Priority(0)` and
is listed in `META-INF/services/org.robolectric.pluginapi.NativeRuntimeLoader`. Putting the
jar on `testRuntimeOnly` is enough for Robolectric's own plugin lookup to pick it over the
stock loader. Its `ensureLoaded()`:

* hands over to the stock `super.ensureLoaded()` for SDK below 35, for any SDK other than
  the one the library was built for (`-Drobolectric.arm64.nativeLibrarySdk`, default 36:
  loading the SDK 36 library into an SDK 37 sandbox aborts the JVM in `JNI_OnLoad`, while the
  stock loader fails cleanly), and on every platform other than Linux aarch64 unless forced,
  so one test classpath works on every machine;
* otherwise loads the file named by `-Drobolectric.arm64.nativeLibrary=/abs/path.so`, or the
  classpath resource `native/linux/aarch64/libandroid_runtime.so`, always as a fresh copy in
  the sandbox's temp directory, as the stock loader does (the JVM refuses to load one file
  into a second sandbox class loader: "already loaded in another classloader"), and fails
  with a message naming both options if neither exists. The resource is looked up on the
  sandbox loader first (android-all, should it ever ship the file) and then up its parent
  chain, which is how it gets past the sandbox's android-all-only rule for `*android_runtime*`
  names;
* does every other step exactly as upstream by calling the stock loader's private
  `maybeCopyFonts`, `maybeCopyHyphenData`, `maybeCopyIcuData` reflectively and its protected
  `getCoreClassNatives()`, `getGraphicsNatives()`, `invokeDeferredStaticInitializers()` and
  `setNativeSystemProperty()` directly;
* records where the library came from in the system property `robolectric.arm64.loadedFrom`.

The reflection ties it to 4.17's private method names; a rename fails loudly with a message
rather than silently misbehaving. The class is Java on purpose: the sandbox does not acquire
`kotlin.*`, and this class must be loaded by the sandbox loader to see the sandbox's
`android.*` classes.

Other options considered: lying about `os.arch` breaks every other native library in the JVM
(sqlite4java, conscrypt); shadowing `DefaultNativeRuntimeLoader` with a same-named class
earlier on the classpath works but replaces the whole class and must track every upstream
change; a Java agent or bytecode patch of `isSupported()` is unnecessary because the
ServiceLoader hook exists.

## The upstream change that would make this unnecessary

One line in `DefaultNativeRuntimeLoader.isSupported()`:

```java
|| (OsUtil.isLinux() && (Objects.equals(arch(), "x86_64") || Objects.equals(arch(), "aarch64")))
```

Nothing else in the loader is arch-specific: `nativeLibraryPath()` already yields
`native/linux/aarch64/libandroid_runtime.so`, and Robolectric would ship that file in the
android-all jar next to the other four. Letting users supply it from their own test classpath
would need a second change, because the sandbox serves `*android_runtime*` resources from
android-all only (step 4 above); for example, fall back to the sandbox loader's parent when
android-all has no such entry. Once upstream ships the file, the plugin can simply be removed:
it already delegates to the stock path wherever the stock path works.
