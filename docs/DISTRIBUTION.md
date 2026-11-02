# Distribution

Releases up to `v4.17-16-robolectric-13921718-3` are on GitHub only. Nothing is on Maven Central yet.
The layout below is the one for Maven Central, starting with `4.17-1`, and has not been released yet.
Central versions are permanent, so it is written down here first.

| | |
| --- | --- |
| Repository | https://github.com/LavishSonbhurra/robolectric-native-arm64 |
| Group | `io.github.lavishsonbhurra` |
| The one dependency | `robolectric-nativeruntime-linux-aarch64:4.17-1` |
| Covers | SDK 26 to 37 on Robolectric 4.17 |
| Hosting | GitHub releases, then Maven Central |

## 1. Goal

A Robolectric user on Linux arm64 (a CI runner, an Apple-silicon Linux VM, a Raspberry Pi class
machine, a Graviton instance) adds one test dependency and native graphics tests run at any SDK level
from 26 to 37. No change to Robolectric, no manual library path. On every other platform the same
dependency is inert, so one `build.gradle.kts` works for a mixed team.

## 2. What is published

| Artifact | Version | Holds | Jar size |
| --- | --- | --- | --- |
| `robolectric-nativeruntime-linux-aarch64` | `4.17-1` | The loader plugin, no library | 15 KB |
| `robolectric-nativeruntime-sdk35-linux-aarch64` | `15-robolectric-13954326-1` | `native/linux/aarch64/sdk35/libandroid_runtime.so` | 6.4 MB |
| `robolectric-nativeruntime-sdk36-linux-aarch64` | `16-robolectric-13921718-1` | `native/linux/aarch64/sdk36/libandroid_runtime.so` | 6.7 MB |
| `robolectric-nativeruntime-sdk37-linux-aarch64` | `17-robolectric-15733970-1` | `native/linux/aarch64/sdk37/libandroid_runtime.so` | 10.3 MB |
| `robolectric-nativeruntime-compat-linux-aarch64` | `1.0.19-2` | `native/linux/aarch64/librobolectric-nativeruntime.so`, native arm64 pixels, SDK 26 to 34 | 5.9 MB |
| `robolectric-nativeruntime-compat-linux-aarch64-x86pixels` | `1.0.19-2` | `native/linux/aarch64/x86-pixels/librobolectric-nativeruntime.so`, opt-in, images match the x86_64 library | 5.9 MB |

The POM and the Gradle module metadata of the loader have runtime dependencies on the SDK 35, 36, 37 and
compat artifacts, so the one dependency line brings all four, 29 MB in total. The x86-pixels artifact
is opt-in and is not among them.

Why the libraries are separate artifacts:

* Each library has its own revision. A fix to one does not republish the others.
* Each has its own notices and POM text. SDK 37 links more third parties than SDK 35 and 36.
* Each SDK has its own resource path, so all of them can be on one classpath and the loader picks by
  the SDK under test. No SDK can reach another SDK's library, which matters because that aborts the JVM.
* Separate artifacts rather than classifiers: Gradle and Maven resolve them with plain coordinates.

The cost is that the loader's POM pins the library versions, so a new library revision also needs a new
loader revision for users of the one dependency line.

The loader jar holds:

| Entry | What |
| --- | --- |
| `robolectricarm64/LinuxArm64NativeRuntimeLoader.class` | The `NativeRuntimeLoader` plugin, Java 11 bytecode (the level of Robolectric's own jars), compiled against Robolectric 4.17. |
| `META-INF/services/org.robolectric.pluginapi.NativeRuntimeLoader` | Makes Robolectric's ServiceLoader lookup find it. Its `@Priority(0)` beats the stock loader's `Integer.MIN_VALUE`. |
| `META-INF/LICENSE`, `META-INF/LICENSE-robolectric.txt`, `META-INF/NOTICE` | See [LICENSING.md](LICENSING.md). |

Each library jar holds the library, `META-INF/THIRD_PARTY_NOTICES`, `META-INF/LICENSE` and
`META-INF/NOTICE`, and no code. Its sources and javadoc jars hold `SOURCES.txt`, which says where the
library's sources are, with the same `LICENSE` and `NOTICE`.

Everything is built by one file per kind: `loader/build.gradle.kts` and
`libraries/build.gradle.kts`, which serves all five library projects. Timestamps, entry order and file
modes in the jars are fixed, so a jar depends only on its inputs. `SDK <= 34` details are in
[COMPAT.md](COMPAT.md).

The compat version is `<nativeruntime-dist-compat version>-<revision>`. The revision goes up only when
the jar changes; a new upstream version starts again at `-1`.

### GitHub release assets

One tag holds everything, so every name is unique:

| Assets | From | Checksums |
| --- | --- | --- |
| the three loader jars | `build.yml`, `package-loader` | `SHA256SUMS` |
| library, main, sources and javadoc jars, notices, `notices.json`, `build-info.txt` per SDK, as `libandroid_runtime-sdk35.so`, `sdk35-THIRD_PARTY_NOTICES` and so on | `build.yml`, `package` | `sdk35-SHA256SUMS`, `sdk36-SHA256SUMS`, `sdk37-SHA256SUMS` |
| both compat builds, with the names `build-compat.yml` has always used | `build-compat.yml`, `package` | `compat-SHA256SUMS` |

The libraries and jars also have GitHub build-provenance attestations (`gh attestation verify`).

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

Until the artifacts are on Maven Central, replace the coordinate with `files(...)` entries for the
loader jar and the library jars you need from the GitHub release: a file dependency has no POM, so it
brings nothing with it.

```kotlin
dependencies {
    testImplementation("org.robolectric:robolectric:4.17")
    // Inert on every platform except Linux aarch64.
    testRuntimeOnly("io.github.lavishsonbhurra:robolectric-nativeruntime-linux-aarch64:4.17-1")
}

tasks.withType<Test>().configureEach {
    // SDK 36 and 37 need Java 21 (android-all 16 is class file version 65). SDK 35 needs 17.
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

* **Java.** Robolectric 4.17 registers SDK 35 with required Java 17, and SDK 36 and 37 with Java 21. It
  checks this itself, so the loader does not. The test JVM must be new enough even if the project
  compiles for 17, which the Gradle toolchain block above handles. On an arm64 machine the toolchain must
  resolve to an aarch64 JDK; a library for a different CPU cannot be loaded
  (`can't load AMD 64 .so on a AARCH64 platform`).
* **`--add-opens`.** These four are what the rig uses on JDK 21. `jdk.internal.access` is needed by
  Robolectric's `FileDescriptor` interceptor; the other three come from the same family of reflective
  access. The minimal set has not been bisected; Robolectric's own docs for JDK 17+ apply. Android Gradle
  Plugin projects may already pass some of these.
* **SQLite.** In 4.17 the default SQLite mode is `NATIVE`, so every test at SDK 35 and later loads the
  library, not only graphics tests. Tests that force `SQLiteMode.LEGACY` use sqlite4java, which has no
  linux-aarch64 native; that is independent of this project (the 12 `ShadowSQLiteConnectionTest` failures
  and `SQLiteLibraryLoaderTest` in the upstream run).
* **Which library.** The loader reads the SDK level of the sandbox: 35, 36 and 37 load their own
  library, below 35 the compat library. If the artifact for that SDK is not on the classpath the test
  fails with a message naming it. SDK levels above 37, and every platform other than Linux aarch64, go
  to the stock loader.
* **Espresso at SDK 37.** Espresso 3.7.0 calls `InputManager.getInstance()`, which SDK 37 removed, so
  Compose tests and anything else that uses it fail with `NoSuchMethodException` with any library.
  3.8.0-alpha03 works. It needs minSdk 24.
* **Only some SDK levels.** To leave libraries out, exclude them:
  `testRuntimeOnly("...") { exclude(module = "robolectric-nativeruntime-sdk37-linux-aarch64") }`.
* **x86 pixels.** Add `robolectric-nativeruntime-compat-linux-aarch64-x86pixels:1.0.19-2` and set
  `-Drobolectric.arm64.compatPixels=x86`. With both compat jars on the classpath the native one is used
  otherwise ([COMPAT.md](COMPAT.md)).
* **Coming from an earlier release.** Remove the jar of version `4.17-16-robolectric-13921718-*`. It
  holds a loader with the same class name, which can shadow this one, and an SDK 36 library at
  `native/linux/aarch64/libandroid_runtime.so`, a path this loader no longer reads.
* **Override for development**: `-Drobolectric.arm64.nativeLibrary=/abs/libandroid_runtime.so` loads a
  file instead of the bundled resource (useful for testing your own build). Name the SDK it was built for
  with `-Drobolectric.arm64.nativeLibrarySdk=35` (default 36; below 35 means the compat library). At any
  other SDK the file is ignored, with a line on stderr, because loading it there would abort the JVM. The
  property `robolectric.arm64.loadedFrom` tells you what was loaded after the first test.
* **Disk**: each Robolectric sandbox copies the library (about 15 to 24 MB), fonts and ICU data under
  `java.io.tmpdir`. Point `java.io.tmpdir` at disk on machines with a RAM-backed `/tmp`.

### Maven

```xml
<dependency>
  <groupId>io.github.lavishsonbhurra</groupId>
  <artifactId>robolectric-nativeruntime-linux-aarch64</artifactId>
  <version>4.17-1</version>
  <scope>test</scope>
</dependency>
```

with `maven-surefire-plugin` `argLine` carrying the same `--add-opens` flags and a Java 21 toolchain.

## 5. Versioning

```
loader     <robolectric>-<revision>                 4.17-1
SDK 35+    <android-all>-<revision>                 16-robolectric-13921718-1
compat     <nativeruntime-dist-compat>-<revision>   1.0.19-2
```

* `<robolectric>`: the Robolectric version the loader was compiled and tested against. The loader calls
  private methods of `DefaultNativeRuntimeLoader` by reflection (`maybeCopyFonts`, `maybeCopyHyphenData`,
  `maybeCopyIcuData`), so a new Robolectric release needs a check and often a new loader version, even
  when no library changes.
* `<android-all>`: the Robolectric android-all build the library registers natives for
  (`16-robolectric-13921718`). Robolectric resolves `org.robolectric:android-all-instrumented:<this>-i7` for
  that SDK, so this is the part users can read off their own build.
* `<revision>`: our counter, from 1, incremented for any rebuild with different content (library fixes,
  notices, toolchain change). Needed because Central versions are immutable. A library artifact's revision
  moves on its own; the loader's goes up when any of its dependencies does, because its POM names them.

The earlier GitHub releases used one version for the loader and the library,
`4.17-16-robolectric-13921718-<revision>`. That scheme ends with `-3` and those jars were never on
Central. Compared as version strings it sorts after `4.17-1`, so nobody should mix the two.

Nobody should rely on range resolution; users pin exact versions.

Each release lists in its notes: Robolectric, android-all, AOSP tag, check results (rig, upstream suites,
JNI comparison), and the SHA-256 of each library.

## 6. The android-all treadmill

The library has to match the android-all jar that Robolectric picks. A mismatch is not subtle:
`RegisterNatives` fails in `JNI_OnLoad` when a Java method signature changed, and the JVM aborts (observed:
SDK 37 with the SDK 36 library, exit code 134). The loader prevents that: each SDK has its own resource path,
and an override file is used only at the SDK it names.

What changes, and how often (to be confirmed by watching; no history exists yet):

1. **A new Robolectric release with the same android-all builds.** Nothing native changes. Re-run the loader
   against the new Robolectric version (compile, rig, upstream suites) and publish `<new robolectric>-1`.
2. **A new android-all build for an SDK** (Robolectric re-cuts android-all from a newer Android branch).
   Possible effects: changed JNI signatures, changed Java-to-native contracts, new native methods, changes
   in hwui behaviour. Robolectric builds android-all from an internal branch (the official library came
   from `BLR2.250402.052`), while we build from the public tag `android-16.0.0_r1`. The two differed by four
   host fixes from later tags, now applied as patches ([rng-audit.md](rng-audit.md)), so expect similar
   drift with each new android-all build.
3. **A new SDK level**: a new target directory under `config/`, a pin, closure entries in `overrides.toml`,
   new rig goldens, and `NEWEST_LIBRARY_SDK` in the loader. SDK 35 and 37 were both done this way
   ([SDK35.md](SDK35.md), [SDK37.md](SDK37.md)). SDK 37 took 174 more modules than SDK 36.
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
suites (5 to 10 minutes native on arm64, about 9,000 tests at each SDK). Both are in `build.yml` already.

## 7. What has been verified

All local unless it says CI. Every line below was measured through the jars, resolved from a Maven
repository by the loader's one dependency line, with no override.

**Rig** (33 tests, 37 images, compared with the official x86_64 library). Every run loaded the library
from the expected jar and stayed within the ceilings in `tests/rig/baseline/`.

| SDK | Artifact | Tests passed | Images identical | Worst difference (of 255) |
| --- | --- | --- | --- | --- |
| 30 | compat | 33 of 33 | 17 of 37 | 47 |
| 34 | compat | 33 of 33 | 16 of 37 | 171 |
| 35 | sdk35, on Java 21 and on Java 17 | 33 of 33 | 24 of 37 | 135 |
| 36 | sdk36 | 33 of 33 | 28 of 37 | 135 |
| 37 | sdk37 | 33 of 33 | 28 of 37 | 135 |

**Upstream suites**, counts from the JUnit XML, failed tests in parentheses:

| SDK | robotests | nativegraphics | ctesque | Skipped |
| --- | --- | --- | --- | --- |
| 35 | 7,801 (13) | 769 (1) | 429 (0) | 12 |
| 36 | 7,886 (13) | 770 (1) | 430 (0) | 12 |
| 37 | 7,800 (13) | 769 (1) | 429 (0) | 14 |

The same 14 tests fail at each SDK: 13 force LEGACY SQLite through sqlite4java, which has no linux-aarch64
native, and `ShadowNativeTableMaskFilterTest` cannot create its test runner, on the official library too.

**Loader.** Exercised on real test runs, with no JVM abort in any of them:

* SDK 35 with only the SDK 36 jar, with an old jar that holds the SDK 36 library at the flat path, and with
  no library at all plus a wrong override: a clear error naming the missing artifact.
* SDK 30 with no compat jar: the same error, naming the compat artifact.
* SDK 35 with a wrong override and the sdk35 jar: the override is ignored with a line on stderr, and the
  jar is used.
* A correct override at SDK 36 and 37: the file is used.
* SDK 30 with only the x86-pixels jar, and with both compat jars, by default and with
  `robolectric.arm64.compatPixels=x86`: the expected jar is used.
* An unparseable `robolectric.arm64.nativeLibrarySdk`: a clear error.

**Packaging.**

* Gradle resolves the one dependency line to the loader and the four libraries, not x86-pixels, for
  consumers targeting Java 11 and 17, from the `.module` file and from the POM alone.
* Two builds of the repository under different umasks gave the same 150 files.
* The compat and x86-pixels jars are byte-identical to the released `1.0.19-2` jars.
* `ci/check-release.py` passed against a local mirror of a release, and stopped on a tampered one.
* A bundle signed with a throwaway key has 30 artifacts, each with a signature that verifies, an MD5 and a
  SHA-1. It was not uploaded.

**Not verified:**

* None of the workflows has run in this form.
* Compared per test with Google's library: for SDK 36, 81 native-relevant robotests classes plus
  nativegraphics and ctesque; for SDK 35, nativegraphics and ctesque only, so **robotests were not compared
  per test**; for SDK 37, **only an 81-class subset** of robotests plus nativegraphics and ctesque.
* The x86_64 control build, which shows whether the build recipe matches Google's pixel for pixel, is done
  for SDK 36 and 26 to 34. It is not finished for SDK 35 and does not exist for SDK 37.
* SDK 37 `MotionPredictor` loads, but no test runs TensorFlow Lite inference with a real model.
* 7 robotests files need compileSdk 37, so they do not run at any SDK.
* The suites at SDK 30 and 34 did not run through the `4.17-1` loader. The rig did. Full suite runs for SDK
  26 to 34 are in [COMPAT.md](COMPAT.md), through the earlier loader and the same compat jars.
* Only Linux arm64 on one VM: Ampere Altra, Ubuntu 26.04, JDK 21.0.12 and 17.0.19.

Linux x86_64 is not needed (Robolectric ships it); the x86_64 build in this repository exists as a control
for fidelity measurements and is not distributed.

## 8. Release process

The workflows as described here have not run yet. The SDK 36 and compat jobs ran in their earlier form
for the releases up to `-3`.

1. A tag `v<loader version>` (for example `v4.17-1`) runs `build.yml` and `build-compat.yml` with the
   rig, the reproducibility job and the upstream suites. Each SDK builds in its own job on its own runner.
2. The artifacts `release-loader`, `release-sdk35`, `release-sdk36`, `release-sdk37` and `release-compat`
   become the GitHub release. Their file names do not clash (section 2). Publish it: the upload workflow
   has a read-only token, which cannot see a draft.
3. Maven Central: run the `Upload to Maven Central` workflow (`release.yml`) by hand with the tag, from a
   commit whose Gradle versions match the release. Its `verify` job checks the five checksum files,
   rebuilds every jar from the release's libraries and stops if `ci/check-release.py` finds any
   difference, in either direction: a jar in only one of the two places is an error. The same check
   wants the loader's dependencies at the versions in the repository, in the POM and in the module
   metadata, and the sentences the notices require in each library's POM description. The `rig` job runs
   the rig at SDK 30, 34, 35, 36 and 37 through those artifacts. The `upload` job signs that same
   repository and uploads it to the Central Portal.
4. The upload stops at `VALIDATED` and is private. Check it in the Portal, then press Publish, or Drop it
   to upload again. Publish is permanent: the version can never be replaced or removed.

The signing key is a dedicated RSA 4096 key, fingerprint `4E2CCCBC8495F4B2CFC79ADA40010BA3FD767082`, with no
subkeys because Central verifies against the primary key. It expires on 2031-11-01. Secrets live in the
`maven-central` GitHub environment, so no other workflow can read them.
