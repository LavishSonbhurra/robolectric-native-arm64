/*
 * Copyright 2026 Lavish Sonbhurra
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * The loading sequence in loadCustom() follows Robolectric's
 * org.robolectric.nativeruntime.DefaultNativeRuntimeLoader (robolectric-4.17),
 * Copyright (c) 2010 Xtreme Labs, Pivotal Labs and Google Inc., used under the MIT License.
 * The MIT License text is in loader/LICENSE-robolectric.txt and, in the published jar, in
 * META-INF/LICENSE-robolectric.txt.
 */

package robolectricarm64;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import javax.annotation.Priority;
import org.robolectric.nativeruntime.DefaultNativeRuntimeLoader;
import org.robolectric.shadow.api.Shadow;
import org.robolectric.util.PerfStatsCollector;
import org.robolectric.util.ReflectionHelpers;
import org.robolectric.util.TempDirectory;

/**
 * A {@link org.robolectric.pluginapi.NativeRuntimeLoader} that lets Robolectric 4.17 load a
 * Linux arm64 build of libandroid_runtime for SDK 35 and above, and of
 * librobolectric-nativeruntime (the nativeruntime-dist-compat library) for SDK 26 to 34.
 *
 * <p>Robolectric picks its NativeRuntimeLoader through ServiceLoader and keeps the candidate
 * with the highest {@code @Priority}. The stock {@link DefaultNativeRuntimeLoader} declares
 * {@code Integer.MIN_VALUE}, so this class (priority 0) wins as soon as its jar is on the test
 * runtime classpath. No Robolectric class is patched.
 *
 * <p>Where it does something different from the stock loader:
 *
 * <ul>
 *   <li>If the system property {@value #LIBRARY_PROPERTY} names a file, that file is loaded, on
 *       any OS and architecture. This is how the rig checks this code path with the official
 *       x86_64 library.
 *   <li>Otherwise, on Linux aarch64, the classpath resource {@value #ARM64_RESOURCE} is used
 *       (from android-all itself once upstream ships it, or from any jar on the test classpath).
 *   <li>For SDK levels below 35 on Linux aarch64, the compat library from the classpath:
 *       {@value #ARM64_COMPAT_RESOURCE} (the default, native arm64 pixels) or
 *       {@value #ARM64_COMPAT_X86_RESOURCE} (the x86-pixels build). With both on the classpath
 *       the native one is used unless {@value #COMPAT_PIXELS_PROPERTY} is {@code x86}.
 *   <li>Everywhere else it hands over to the stock loader unchanged.
 * </ul>
 *
 * <p>The setup steps (fonts, hyphenation data, ICU data, JNI registration properties, deferred
 * static initializers) are the stock loader's own private methods, called reflectively, so
 * the result matches upstream exactly. That ties this class to Robolectric 4.17's internals;
 * it fails with a clear message if they change.
 */
@Priority(0)
public class LinuxArm64NativeRuntimeLoader extends DefaultNativeRuntimeLoader {

  /** Absolute path of a libandroid_runtime to load instead of the bundled one. */
  public static final String LIBRARY_PROPERTY = "robolectric.arm64.nativeLibrary";

  /** Set after loading: where the library came from (for logs and the rig's manifest). */
  public static final String LOADED_FROM_PROPERTY = "robolectric.arm64.loadedFrom";

  /** The SDK level the library was built for (default 36); other SDKs use the stock loader. */
  public static final String LIBRARY_SDK_PROPERTY = "robolectric.arm64.nativeLibrarySdk";

  public static final String ARM64_RESOURCE = "native/linux/aarch64/libandroid_runtime.so";

  /** The SDK <= 34 library (nativeruntime-dist-compat's layout), for SDK levels below 35. */
  public static final String ARM64_COMPAT_RESOURCE =
      "native/linux/aarch64/librobolectric-nativeruntime.so";

  /**
   * The same library built with x86 pixels (RA64_PIXELS=x86), from its own artifact. A separate
   * path, so the two jars never shadow each other and the stock loader never picks it up.
   */
  public static final String ARM64_COMPAT_X86_RESOURCE =
      "native/linux/aarch64/x86-pixels/librobolectric-nativeruntime.so";

  /**
   * Which compat build to load from the classpath: {@code native} or {@code x86}. Unset: the
   * native one if present, otherwise the x86-pixels one.
   */
  public static final String COMPAT_PIXELS_PROPERTY = "robolectric.arm64.compatPixels";

  private static final int VANILLA_ICE_CREAM = 35;

  @Override
  public synchronized void ensureLoaded() {
    if (loaded.get()) {
      return;
    }
    String override = System.getProperty(LIBRARY_PROPERTY, "").trim();
    boolean linuxArm64 = isLinux() && "aarch64".equals(arch());
    // A libandroid_runtime only matches the android-all it was built from: loading the SDK 36
    // library into another SDK's sandbox aborts the JVM in JNI_OnLoad (RegisterNatives fails
    // on changed signatures). Other SDKs go to the stock loader, which fails cleanly.
    int librarySdk = Integer.parseInt(System.getProperty(LIBRARY_SDK_PROPERTY, "36").trim());
    // SDK <= 34 use one library for every SDK level (librobolectric-nativeruntime, from
    // android12-hostruntime-dev): it registers its natives on Robolectric's own *Natives
    // classes, so any SDK below 35 can load it. Used when the override names such a library
    // (LIBRARY_SDK_PROPERTY below 35) or, on Linux arm64 with no override, from the classpath.
    if (sdkInt() < VANILLA_ICE_CREAM
        && ((!override.isEmpty() && librarySdk < VANILLA_ICE_CREAM)
            || (override.isEmpty() && linuxArm64 && compatResource() != null))) {
      loaded.set(true);
      PerfStatsCollector.getInstance()
          .measure("loadNativeRuntime", () -> loadCompat(override));
      return;
    }
    if (sdkInt() < VANILLA_ICE_CREAM
        || sdkInt() != librarySdk
        || (override.isEmpty() && !linuxArm64)) {
      super.ensureLoaded();
      if (System.getProperty(LOADED_FROM_PROPERTY) == null) {
        System.setProperty(LOADED_FROM_PROPERTY, "upstream DefaultNativeRuntimeLoader");
      }
      return;
    }
    loaded.set(true);
    PerfStatsCollector.getInstance()
        .measure("loadNativeRuntime", () -> loadCustom(override));
  }

  private void loadCustom(String override) {
    try {
      TempDirectory dir = new TempDirectory("nativeruntime");
      setExtractDirectory(dir);
      callPrivate("maybeCopyFonts", dir);
      callPrivate("maybeCopyHyphenData", dir);
      callPrivate("maybeCopyIcuData", dir);
      maybeCopyExtraResources(dir);

      Path library = resolveLibrary(override, dir);
      Map<String, String> saved = new HashMap<>();
      for (String key : JNI_PROPERTIES) {
        saved.put(key, System.getProperty(key));
      }
      System.setProperty("use_base_native_hostruntime", "true");
      System.setProperty("core_native_classes", String.join(",", getCoreClassNatives()));
      System.setProperty("graphics_native_classes", String.join(",", getGraphicsNatives()));
      System.setProperty("method_binding_format", METHOD_BINDING_FORMAT);
      try {
        System.load(library.toAbsolutePath().toString());
      } finally {
        for (Map.Entry<String, String> e : saved.entrySet()) {
          if (e.getValue() == null) {
            System.clearProperty(e.getKey());
          } else {
            System.setProperty(e.getKey(), e.getValue());
          }
        }
      }
      System.setProperty(
          LOADED_FROM_PROPERTY,
          (override.isEmpty() ? "classpath resource" : override) + " via " + library.toAbsolutePath());

      invokeDeferredStaticInitializers();
      setNativeSystemProperty(
          "ro.hyphen.data.dir",
          dir.getBasePath().resolve("hyphen-data").toFile().getAbsolutePath());
      ClassLoader sandbox = Shadow.class.getClassLoader();
      ReflectionHelpers.callStaticMethod(
          sandbox, "android.graphics.Typeface", "loadPreinstalledSystemFontMap");
      ReflectionHelpers.callStaticMethod(sandbox, "android.text.Hyphenator", "init");
    } catch (IOException e) {
      throw new AssertionError("Unable to load Robolectric native runtime library", e);
    }
  }

  /**
   * The stock 4.17 loader's steps for SDK levels below 35, with our library: fonts and
   * hyphenation data (SDK 26+), ICU data, extra resources, load, then hyphen.data.dir and
   * Hyphenator.init() (SDK 28+). No JNI registration properties: this library binds its
   * natives itself.
   */
  private void loadCompat(String override) {
    try {
      TempDirectory dir = new TempDirectory("nativeruntime");
      setExtractDirectory(dir);
      if (sdkInt() >= 26) {
        callPrivate("maybeCopyFonts", dir);
        callPrivate("maybeCopyHyphenData", dir);
      }
      callPrivate("maybeCopyIcuData", dir);
      maybeCopyExtraResources(dir);
      Path target = dir.getBasePath().resolve("librobolectric-nativeruntime.so");
      if (!override.isEmpty()) {
        Path path = Paths.get(override);
        if (!Files.isRegularFile(path)) {
          throw new AssertionError(LIBRARY_PROPERTY + " points at a missing file: " + path);
        }
        Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING);
      } else {
        try (InputStream in = compatResource().url.openStream()) {
          Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
        }
      }
      System.load(target.toAbsolutePath().toString());
      System.setProperty(
          LOADED_FROM_PROPERTY,
          (override.isEmpty() ? "classpath resource " + compatResource().name : override)
              + " via " + target.toAbsolutePath());
      System.setProperty(
          "hyphen.data.dir",
          dir.getBasePath().resolve("hyphen-data").toFile().getAbsolutePath());
      if (sdkInt() >= 28) {
        ReflectionHelpers.callStaticMethod(
            Shadow.class.getClassLoader(), "android.text.Hyphenator", "init");
      }
    } catch (IOException e) {
      throw new AssertionError("Unable to load Robolectric native runtime library", e);
    }
  }

  /** A compat library found on the classpath. */
  private static final class CompatResource {
    final String name;
    final URL url;

    CompatResource(String name, URL url) {
      this.name = name;
      this.url = url;
    }
  }

  /**
   * The compat library on the classpath (not named *android_runtime*, so no sandbox rule), chosen
   * by {@value #COMPAT_PIXELS_PROPERTY}; null if there is none. Naming a build that is not on
   * the classpath is an error rather than a silent fallback.
   */
  private static CompatResource compatResource() {
    String pixels = System.getProperty(COMPAT_PIXELS_PROPERTY, "").trim();
    URL nativeUrl = resource(ARM64_COMPAT_RESOURCE);
    URL x86Url = resource(ARM64_COMPAT_X86_RESOURCE);
    switch (pixels) {
      case "":
        if (nativeUrl != null) {
          return new CompatResource(ARM64_COMPAT_RESOURCE, nativeUrl);
        }
        return x86Url == null ? null : new CompatResource(ARM64_COMPAT_X86_RESOURCE, x86Url);
      case "native":
        if (nativeUrl == null) {
          throw new AssertionError(COMPAT_PIXELS_PROPERTY + "=native, but "
              + ARM64_COMPAT_RESOURCE + " is not on the test classpath");
        }
        return new CompatResource(ARM64_COMPAT_RESOURCE, nativeUrl);
      case "x86":
        if (x86Url == null) {
          throw new AssertionError(COMPAT_PIXELS_PROPERTY + "=x86, but "
              + ARM64_COMPAT_X86_RESOURCE + " is not on the test classpath");
        }
        return new CompatResource(ARM64_COMPAT_X86_RESOURCE, x86Url);
      default:
        throw new AssertionError(
            COMPAT_PIXELS_PROPERTY + " must be native or x86, not \"" + pixels + "\"");
    }
  }

  private static URL resource(String name) {
    URL url = LinuxArm64NativeRuntimeLoader.class.getClassLoader().getResource(name);
    return url != null ? url : ClassLoader.getSystemResource(name);
  }

  private static final String[] JNI_PROPERTIES = {
    "use_base_native_hostruntime", "core_native_classes", "graphics_native_classes",
    "method_binding_format",
  };

  /**
   * The override file or the classpath resource, copied into the extract directory. Always a
   * fresh copy, as the stock loader does: every sandbox class loader needs its own instance of
   * the library, and the JVM refuses to load one file into a second class loader
   * ("already loaded in another classloader").
   */
  private static Path resolveLibrary(String override, TempDirectory dir) throws IOException {
    Path target = dir.getBasePath().resolve("libandroid_runtime.so");
    if (!override.isEmpty()) {
      Path path = Paths.get(override);
      if (!Files.isRegularFile(path)) {
        throw new AssertionError(LIBRARY_PROPERTY + " points at a missing file: " + path);
      }
      Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING);
      return target;
    }
    // The sandbox loader serves any resource whose name contains "android_runtime" from
    // android-all only (InstrumentationConfiguration.shouldAcquireResource), so a jar on the
    // test classpath is invisible through it. Ask it first (android-all may ship the file one
    // day), then walk up to the ordinary application class loader.
    URL url = null;
    for (ClassLoader cl = LinuxArm64NativeRuntimeLoader.class.getClassLoader();
        cl != null && url == null;
        cl = cl.getParent()) {
      url = cl.getResource(ARM64_RESOURCE);
    }
    if (url == null) {
      url = ClassLoader.getSystemResource(ARM64_RESOURCE);
    }
    if (url == null) {
      throw new AssertionError(
          "No Linux arm64 Robolectric native runtime found. Put "
              + ARM64_RESOURCE
              + " on the test runtime classpath, or set -D"
              + LIBRARY_PROPERTY
              + "=/path/to/libandroid_runtime.so");
    }
    try (InputStream in = url.openStream()) {
      Files.copy(in, target, StandardCopyOption.REPLACE_EXISTING);
    }
    return target;
  }

  private void callPrivate(String name, TempDirectory dir) throws IOException {
    try {
      Method m = DefaultNativeRuntimeLoader.class.getDeclaredMethod(name, TempDirectory.class);
      m.setAccessible(true);
      m.invoke(this, dir);
    } catch (NoSuchMethodException | IllegalAccessException e) {
      throw new AssertionError(
          "DefaultNativeRuntimeLoader." + name + " is gone; this loader targets Robolectric 4.17",
          e);
    } catch (InvocationTargetException e) {
      Throwable cause = e.getCause();
      if (cause instanceof IOException) {
        throw (IOException) cause;
      }
      if (cause instanceof RuntimeException) {
        throw (RuntimeException) cause;
      }
      throw new AssertionError(cause);
    }
  }

  /** Keeps the stock getDirectory() working; harmless if the field is renamed. */
  private void setExtractDirectory(TempDirectory dir) {
    try {
      Field f = DefaultNativeRuntimeLoader.class.getDeclaredField("extractDirectory");
      f.setAccessible(true);
      f.set(this, dir);
    } catch (ReflectiveOperationException ignored) {
      // Only used by Robolectric's own tests.
    }
  }

  private static int sdkInt() {
    return ReflectionHelpers.getStaticField(
        ReflectionHelpers.loadClass(Shadow.class.getClassLoader(), "android.os.Build$VERSION"),
        "SDK_INT");
  }

  private static boolean isLinux() {
    return System.getProperty("os.name", "").toLowerCase(Locale.US).startsWith("linux");
  }

  private static String arch() {
    return System.getProperty("os.arch", "").toLowerCase(Locale.US);
  }
}
