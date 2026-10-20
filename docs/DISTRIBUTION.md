# Distribution

Nothing has been published yet. This document describes what the releases will contain, where they are
hosted and how versions are numbered.

| | |
| --- | --- |
| Repository | https://github.com/LavishSonbhurra/robolectric-native-arm64 |
| Group | `io.github.lavishsonbhurra` |
| Artifact | `robolectric-nativeruntime-linux-aarch64` |
| First version | `4.17-16-robolectric-13921718-1` |
| Hosting | GitHub releases first, Maven Central after that |

## 1. Goal

A Robolectric user on Linux arm64 (a CI runner, an Apple-silicon Linux VM, a Raspberry Pi class
machine, a Graviton instance) adds one test dependency and an SDK 36 native-graphics test runs. No
change to Robolectric, no manual library path. On every other platform the same dependency is inert, so
one `build.gradle.kts` works for a mixed team.

## 2. What is published

One artifact, a jar, containing:

| Entry | What |
| --- | --- |
| `robolectricarm64/LinuxArm64NativeRuntimeLoader.class` | The `NativeRuntimeLoader` plugin (about 230 lines of Java 17 bytecode, compiled against Robolectric 4.17). |
| `META-INF/services/org.robolectric.pluginapi.NativeRuntimeLoader` | Makes Robolectric's ServiceLoader lookup find it. Its `@Priority(0)` beats the stock loader's `Integer.MIN_VALUE`. |
| `native/linux/aarch64/libandroid_runtime.so` | The stripped library, about 15 MB (about 6.6 MB compressed with gzip; the jar's deflate is similar). The path is the one Robolectric itself would use if Google shipped the file inside `android-all`. |
| `META-INF/THIRD_PARTY_NOTICES`, `META-INF/LICENSE`, `META-INF/NOTICE` | See [LICENSING.md](LICENSING.md). |

Why one jar and not a plugin jar plus a natives jar: the plugin and the library must match (the plugin
only loads the library for the SDK it was built for, and the library only matches one android-all build),
and a user would otherwise have to keep two versions in step. If the project later grows an x86_64 build or
an SDK 35 build, the natives move to classifier artifacts or separate artifacts per SDK and the loader
becomes its own artifact.

Plus, as GitHub release assets for every tag: the bare `libandroid_runtime.so`, `THIRD_PARTY_NOTICES`,
`notices.json`, `SHA256SUMS`, `build-info.txt` and the GitHub build-provenance attestation (`gh attestation
verify`). The jar is attested too.

## 3. Where to host it

| Option | Consumers need | Cost to the maintainer | Verdict |
| --- | --- | --- | --- |
| **Maven Central** (Central Portal) | Nothing: Gradle and Maven resolve from Central by default, and Robolectric users already use it | Namespace verification, GPG key, sources and javadoc jars, POM metadata, a portal token. One-time setup of about half a day | **Chosen** for releases after the first GitHub release |
| GitHub Packages (Maven) | A GitHub token with `read:packages` even for public packages, and a repository block in every consumer build | Low | Poor fit: every user needs credentials. Acceptable only for internal snapshots |
| GitHub Releases + manual download | A `files(...)` dependency or a download task | None | **Chosen** as the first public step and as the source of truth for checksums; poor developer experience |
| Own Maven repository on static hosting | One repository block | A host and its upkeep | Not worth it next to Central |
| JitPack | n/a | n/a | Cannot work: it builds on its own x86 infrastructure, and the arm64 build takes about an hour with the toolchain downloads |

### Maven Central requirements (checked on central.sonatype.org on 2026-10-19)

* **Namespace** verified in the Central Portal. For `io.github.lavishsonbhurra`, signing in with the
  GitHub account normally verifies it automatically. The group id cannot be changed after the first
  Central release without republishing under new coordinates.
* **POM**: coordinates, `name`, `description`, `url`, at least one `license`, `developer`, `scm`.
  Version must not end in `-SNAPSHOT`.
* **Sources jar and javadoc jar** for every jar; placeholder jars are allowed. The sources jar holds the
  loader's Java sources (the library's sources are the AOSP tag plus this repository; say so in the POM
  description and in the sources jar's README).
* **Checksums**: `.md5` and `.sha1` for every file (`.sha256`, `.sha512` optional).
* **GPG signature** (`.asc`) for every file. A dedicated release key, published to a key server, kept as a
  CI secret or used from a local machine.
* **Immutability**: a published version cannot be replaced. That is why the version has a revision suffix
  (section 5).
* Publishing: the Central Portal API accepts a bundle; the Gradle plugin `com.vanniktech.maven.publish` or a
  small script does it. The release workflow will need the portal username and token and the signing key
  and passphrase as secrets. The build workflow uses none of them.

Order: (1) a GitHub release with assets and attestations for the first tag, (2) Maven Central once the
namespace is verified, (3) the release assets stay the place to fetch a bare library. The group is not
under `org.robolectric`, which belongs to the Robolectric project.

## 4. Consuming it

### Gradle (Kotlin DSL), JVM or Android module

Until the artifact is on Maven Central, replace the coordinates with
`files("libs/<jar from the GitHub release>")`.

```kotlin
dependencies {
    testImplementation("org.robolectric:robolectric:4.17")
    // Inert on every platform except Linux aarch64.
    testRuntimeOnly("io.github.lavishsonbhurra:robolectric-nativeruntime-linux-aarch64:4.17-16-robolectric-13921718-1")
}

tasks.withType<Test>().configureEach {
    // SDK 36 needs Java 21 (android-all 16 is class file version 65).
    javaLauncher.set(javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) })
    jvmArgs(
        "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED",
    )
    systemProperty("robolectric.graphicsMode", "NATIVE")
}
```

Tests keep their usual annotations, for example `@Config(sdk = [36])`.

Notes:

* **Java 21.** Robolectric 4.17 registers SDK 36 (`BAKLAVA`) with required Java 21, so the test JVM must
  be 21 even if the project compiles for 17. The Gradle toolchain block above handles that. On an arm64
  machine the toolchain must resolve to an aarch64 JDK; a library for a different CPU cannot be loaded
  (`can't load AMD 64 .so on a AARCH64 platform`).
* **`--add-opens`.** These four are what the rig uses on JDK 21. `jdk.internal.access` is needed by
  Robolectric's `FileDescriptor` interceptor; the other three come from the same family of reflective
  access. The minimal set has not been bisected; Robolectric's own docs for JDK 17+ apply. Android Gradle
  Plugin projects may already pass some of these.
* **SQLite.** In 4.17 the default SQLite mode is `NATIVE`, so every SDK 36 test loads this library, not only
  graphics tests. Tests that force `SQLiteMode.LEGACY` use sqlite4java, which has no linux-aarch64 native;
  that is independent of this project (the 12 `ShadowSQLiteConnectionTest` failures and
  `SQLiteLibraryLoaderTest` in the upstream run).
* **Other SDK levels.** Only SDK 36 uses the library. Other SDKs, and any platform other than Linux
  aarch64, go to the stock loader (property `robolectric.arm64.nativeLibrarySdk`, default 36).
* **Override for development**: `-Drobolectric.arm64.nativeLibrary=/abs/libandroid_runtime.so` loads a
  file instead of the bundled resource (useful for testing your own build). The property
  `robolectric.arm64.loadedFrom` tells you what was loaded after the first test.
* **Disk**: each Robolectric sandbox copies the library (about 60 MB unstripped, 15 MB stripped), fonts and
  ICU data under `java.io.tmpdir`. Point `java.io.tmpdir` at disk on machines with a RAM-backed `/tmp`.

### Maven

```xml
<dependency>
  <groupId>io.github.lavishsonbhurra</groupId>
  <artifactId>robolectric-nativeruntime-linux-aarch64</artifactId>
  <version>4.17-16-robolectric-13921718-1</version>
  <scope>test</scope>
</dependency>
```

with `maven-surefire-plugin` `argLine` carrying the same `--add-opens` flags and a Java 21 toolchain.

## 5. Versioning

```
<robolectric>-<android-all>-<revision>        4.17-16-robolectric-13921718-1
```

* `<robolectric>`: the Robolectric version the loader was compiled and tested against. The loader calls
  private methods of `DefaultNativeRuntimeLoader` by reflection (`maybeCopyFonts`, `maybeCopyHyphenData`,
  `maybeCopyIcuData`), so a new Robolectric release needs a check and often a new artifact version, even
  when the library does not change.
* `<android-all>`: the Robolectric android-all build the library registers natives for
  (`16-robolectric-13921718`). Robolectric resolves `org.robolectric:android-all-instrumented:<this>-i7` for
  SDK 36, so this is the part users can read off their own build.
* `<revision>`: our counter, from 1, incremented for any rebuild with different content (library fixes,
  notices, toolchain change). Needed because Central versions are immutable.

Maven and Gradle compare such strings piecewise, so `4.17-...-2` sorts after `4.17-...-1`, and a later
Robolectric (`4.18-...`) sorts after `4.17-...`. Nobody should rely on range resolution; users pin exact
versions.

Each release lists in its notes: Robolectric, android-all, AOSP tag, check results (rig, upstream suites,
JNI comparison), and the SHA-256 of the library.

## 6. The android-all treadmill

The library has to match the android-all jar that Robolectric picks. A mismatch is not subtle:
`RegisterNatives` fails in `JNI_OnLoad` when a Java method signature changed, and the JVM aborts (observed:
SDK 37 with the SDK 36 library, exit code 134). The loader prevents that by using the library only for SDK 36.

What changes, and how often (to be confirmed by watching; no history exists yet):

1. **A new Robolectric release with the same android-all build.** Nothing native changes. Re-run the loader
   against the new Robolectric version (compile, rig, upstream suites) and publish `<new robolectric>-16-robolectric-13921718-1`.
2. **A new android-all build for SDK 36** (Robolectric re-cuts android-all from a newer Android branch).
   Possible effects: changed JNI signatures, changed Java-to-native contracts, new native methods, changes
   in hwui behaviour. Robolectric builds android-all from an internal branch (the official library came
   from `BLR2.250402.052`), while we build from the public tag `android-16.0.0_r1`. The two differed by four
   host fixes from later tags, now applied as patches ([rng-audit.md](rng-audit.md)), so expect similar
   drift with each new android-all build.
3. **A new SDK level** (37 and later): a new pin, possibly new closure entries in `overrides.toml`, new
   rig goldens. The tooling is designed for it ("Moving to another AOSP release" in
   [BUILDING.md](BUILDING.md)) but the effort is unknown until tried.
4. **A new Robolectric release that ships Linux arm64 itself.** The project ends gracefully: the loader
   already delegates to the stock path wherever the stock path works, so the artifact becomes an empty shim
   and can be retired.

How CI will handle it (a scheduled workflow, separate from `build.yml`, not written yet):

1. Once a day: fetch `maven-metadata.xml` for `org.robolectric:android-all-instrumented` and
   `org.robolectric:robolectric` from Central; compare with the versions in a file in the repository.
2. On a new android-all build: download the jar (the pinned hash goes into the issue), extract the official
   x86_64 library, run `tools/jni_tables.py compare` and `dynsym` against our current library and against the
   expected-differences file. If the tables match, open an issue "new android-all build, tables unchanged;
   run the rig and the upstream suites"; if not, open an issue with the table diff. Either way it is a
   human decision, because behaviour can change without any JNI difference.
3. On a new Robolectric release: run the loader unit check (class loads, reflective targets exist), then
   the rig and the upstream suites against the new version, via `workflow_dispatch` with the version as an
   input.
4. If the library has to change: bump the pin in `config/aosp.toml` or add a patch, regenerate, run the
   full `build.yml`, release with the revision counter or a new android-all part.

The cheapest safety net is the JNI table comparison (minutes, no compile); the strongest is the upstream
suites (5 to 10 minutes native on arm64, 9,086 tests at SDK 36). Both are in `build.yml` already.

## 7. Out of scope for now

SDK 34 and below use a different native library (`robolectric-nativeruntime`, from the Android 12 host
runtime branch, distributed in `nativeruntime-dist-compat`) built by a different recipe from different
sources (branch `android12-hostruntime-dev`). This project does not cover them. SDK 35 uses a
`libandroid_runtime` like SDK 36 but built from Android 15; the same tooling may work with another pin and
another closure, but nothing has been tried and no claim is made. Linux x86_64 is not needed (Robolectric
ships it); the x86_64 build in this repository exists as a control for fidelity measurements and is not
distributed.

## 8. Release process

1. A tag `v<version>` (for example `v4.17-16-robolectric-13921718-1`) runs `build.yml` with the rig, the
   reproducibility job and the upstream suites.
2. The `release` artifact of that run (jar, bare library, notices, checksums, build info, attestations)
   becomes the GitHub release.
3. Maven Central publishing follows once the namespace is verified, from a separate workflow or from a
   local machine with the signing key. It is not set up yet.
