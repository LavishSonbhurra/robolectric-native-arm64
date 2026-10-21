// SPDX-License-Identifier: Apache-2.0
//
// The SDK <= 34 library librobolectric-nativeruntime.so for Linux aarch64, as two jars with no
// code. The loader plugin in :loader finds them on the test classpath for SDK levels below 35.
// Fonts, ICU data and hyphenation data come from nativeruntime-dist-compat, which Robolectric
// already depends on. This file builds both projects (see settings.gradle.kts):
//
//   :compat            robolectric-nativeruntime-compat-linux-aarch64, the default build
//                      (native arm64 pixels), as native/linux/aarch64/librobolectric-nativeruntime.so
//                      (the path org.robolectric:nativeruntime-dist-compat uses for x86_64)
//   :compat-x86pixels  robolectric-nativeruntime-compat-linux-aarch64-x86pixels, the
//                      RA64_PIXELS=x86 build, as native/linux/aarch64/x86-pixels/
//                      librobolectric-nativeruntime.so. Its own path, so both jars can be on the
//                      classpath: the loader then takes the native one unless
//                      robolectric.arm64.compatPixels=x86.
//
//   ./gradlew :compat:jar -Pra64.compatLib=/abs/path/librobolectric-nativeruntime.so
//   ./gradlew :compat-x86pixels:jar -Pra64.compatX86Lib=/abs/path/librobolectric-nativeruntime.so
//
// The NOTICE file next to the library (CMake output) or THIRD_PARTY_NOTICES (release layout)
// goes in as META-INF/THIRD_PARTY_NOTICES; ra64.compatNotice / ra64.compatX86Notice name
// another file.
//
// Version: <nativeruntime-dist-compat version>-<our build number>.
plugins {
    `java-library`
    `maven-publish`
}

group = "io.github.lavishsonbhurra"
version = "1.0.19-1"

val x86Pixels = project.name == "compat-x86pixels"
val artifactName =
    "robolectric-nativeruntime-compat-linux-aarch64" + if (x86Pixels) "-x86pixels" else ""
val resourceDir = if (x86Pixels) "native/linux/aarch64/x86-pixels" else "native/linux/aarch64"
base { archivesName.set(artifactName) }

java {
    withSourcesJar()
    withJavadocJar()
}

fun pathSetting(property: String, env: String): Provider<File> =
    providers.gradleProperty(property).orElse(providers.environmentVariable(env)).map {
        val f = File(it)
        if (f.isAbsolute) f else gradle.startParameter.currentDir.resolve(it)
    }

val compatLib: Provider<File> =
    if (x86Pixels) pathSetting("ra64.compatX86Lib", "RA64_COMPAT_X86_LIB")
    else pathSetting("ra64.compatLib", "RA64_COMPAT_LIB")
val compatNotice: Provider<File> =
    (if (x86Pixels) pathSetting("ra64.compatX86Notice", "RA64_COMPAT_X86_NOTICE")
     else pathSetting("ra64.compatNotice", "RA64_COMPAT_NOTICE")).orElse(
        compatLib.map { lib ->
            lib.resolveSibling("NOTICE").takeIf { it.isFile } ?: lib.resolveSibling("THIRD_PARTY_NOTICES")
        },
    )

val checkCompatLib by tasks.registering {
    description = "Checks that the library to bundle is a Linux aarch64 ELF file with a NOTICE file."
    val lib = compatLib.map { it.path }.orElse("")
    val notice = compatNotice.map { it.path }.orElse("")
    inputs.property("compatLib", lib)
    inputs.property("compatNotice", notice)
    doLast {
        val so = File(lib.get())
        val setting = if (x86Pixels) "ra64.compatX86Lib / RA64_COMPAT_X86_LIB" else "ra64.compatLib / RA64_COMPAT_LIB"
        require(lib.get().isNotEmpty() && so.isFile) { "$setting: no such file: $so" }
        val head = so.inputStream().use { it.readNBytes(20) }
        val elf = head.size == 20 && head[0] == 0x7f.toByte() && String(head, 1, 3, Charsets.US_ASCII) == "ELF"
        val aarch64 = elf && head[4] == 2.toByte() && head[5] == 1.toByte() &&
            (head[18].toInt() and 0xff) == 183 && head[19] == 0.toByte()
        require(aarch64) { "$so is not a 64-bit little-endian aarch64 ELF file" }
        require(File(notice.get()).isFile) { "No notices file at ${notice.get()}; set the notice property" }
    }
}

tasks.named<ProcessResources>("processResources") {
    dependsOn(checkCompatLib)
    inputs.property("compatLib", compatLib.map { it.path }.orElse(""))
    from(compatLib) {
        into(resourceDir)
        rename { "librobolectric-nativeruntime.so" }
    }
    from(compatNotice) {
        into("META-INF")
        rename { "THIRD_PARTY_NOTICES" }
    }
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    metaInf {
        from(rootProject.layout.projectDirectory.file("LICENSE"))
    }
}

tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Implementation-Title" to artifactName,
            "Implementation-Version" to project.version,
            "Nativeruntime-Dist-Compat-Version" to "1.0.19",
            "Ra64-Pixels" to if (x86Pixels) "x86" else "native",
        )
    }
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            artifactId = artifactName
            from(components["java"])
            pom {
                name.set(
                    "Robolectric SDK <= 34 native runtime for Linux aarch64" +
                        (if (x86Pixels) ", x86 pixels" else "") + " (unofficial)",
                )
                description.set(
                    "librobolectric-nativeruntime.so for Linux aarch64, built from AOSP " +
                        "android12-hostruntime-dev at the source of org.robolectric:" +
                        "nativeruntime-dist-compat 1.0.19" +
                        (if (x86Pixels) ", with Skia's x86 code paths so that images match the x86_64 build" else "") +
                        ". Load it with the plugin in " +
                        "robolectric-nativeruntime-linux-aarch64. Unofficial; not affiliated with " +
                        "Google or the Robolectric project.",
                )
                url.set("https://github.com/LavishSonbhurra/robolectric-native-arm64")
                licenses {
                    license {
                        name.set("Apache-2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                        comments.set("Build scripts. The bundled library is under the licenses in META-INF/THIRD_PARTY_NOTICES.")
                    }
                }
                developers {
                    developer {
                        id.set("LavishSonbhurra")
                        name.set("Lavish Sonbhurra")
                        url.set("https://github.com/LavishSonbhurra")
                    }
                }
                scm {
                    url.set("https://github.com/LavishSonbhurra/robolectric-native-arm64")
                    connection.set("scm:git:https://github.com/LavishSonbhurra/robolectric-native-arm64.git")
                    developerConnection.set("scm:git:ssh://git@github.com/LavishSonbhurra/robolectric-native-arm64.git")
                }
            }
        }
    }
}
