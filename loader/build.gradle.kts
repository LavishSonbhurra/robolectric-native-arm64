// SPDX-License-Identifier: Apache-2.0
//
// The published jar: a Robolectric NativeRuntimeLoader plugin, its ServiceLoader file and the
// Linux arm64 libandroid_runtime.so as the resource native/linux/aarch64/libandroid_runtime.so.
//
//   ./gradlew :loader:jar -Pra64.nativeLib=/abs/path/build/out/lib/libandroid_runtime.so
//
// The library is a build product and is never committed. It is taken from the Gradle property
// ra64.nativeLib or the environment variable RA64_NATIVE_LIB. The notices file next to it
// (NOTICE, as the CMake build writes it, or THIRD_PARTY_NOTICES, as in a release) goes into
// the jar as META-INF/THIRD_PARTY_NOTICES; ra64.nativeNotice or RA64_NATIVE_NOTICE names
// another file. Without a library the jar holds only the plugin, which is enough when tests
// point -Drobolectric.arm64.nativeLibrary at a file; publishing refuses such a jar.
//
// This project is also included by tests/rig (see tests/rig/settings.gradle.kts), so it must
// not use a version catalog or declare repositories.
plugins {
    `java-library`
    `maven-publish`
}

group = "io.github.lavishsonbhurra"
version = "4.17-16-robolectric-13921718-2"

val artifactName = "robolectric-nativeruntime-linux-aarch64"
// The loader reflects into this Robolectric release; see DefaultNativeRuntimeLoader.
val robolectricVersion = "4.17"

base { archivesName.set(artifactName) }

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.withType<JavaCompile>().configureEach { options.release.set(17) }

dependencies {
    // Provided by Robolectric at test time; never bundled and not in the POM.
    compileOnly("org.robolectric:nativeruntime:$robolectricVersion")
    compileOnly("org.robolectric:pluginapi:$robolectricVersion")
    compileOnly("org.robolectric:utils:$robolectricVersion")
    compileOnly("org.robolectric:shadowapi:$robolectricVersion")
    compileOnly("javax.annotation:javax.annotation-api:1.3.2")
}

fun pathSetting(property: String, env: String): Provider<File> =
    providers.gradleProperty(property).orElse(providers.environmentVariable(env)).map {
        val f = File(it)
        if (f.isAbsolute) f else gradle.startParameter.currentDir.resolve(it)
    }

val nativeLib: Provider<File> = pathSetting("ra64.nativeLib", "RA64_NATIVE_LIB")
// Default: NOTICE next to the library (CMake build output), else THIRD_PARTY_NOTICES (release layout).
val nativeNotice: Provider<File> =
    pathSetting("ra64.nativeNotice", "RA64_NATIVE_NOTICE").orElse(
        nativeLib.map { lib ->
            lib.resolveSibling("NOTICE").takeIf { it.isFile } ?: lib.resolveSibling("THIRD_PARTY_NOTICES")
        },
    )

val checkNativeLib by tasks.registering {
    description = "Checks that the library to bundle is a Linux aarch64 ELF file with a NOTICE file."
    val lib = nativeLib.map { it.path }.orElse("")
    val notice = nativeNotice.map { it.path }.orElse("")
    inputs.property("nativeLib", lib)
    inputs.property("nativeNotice", notice)
    doLast {
        if (lib.get().isEmpty()) return@doLast
        val so = File(lib.get())
        require(so.isFile) { "ra64.nativeLib / RA64_NATIVE_LIB: no such file: $so" }
        val head = so.inputStream().use { it.readNBytes(20) }
        val elf = head.size == 20 && head[0] == 0x7f.toByte() && String(head, 1, 3, Charsets.US_ASCII) == "ELF"
        // e_ident[EI_CLASS] = 2 (64-bit), e_ident[EI_DATA] = 1 (little endian), e_machine = 183 (EM_AARCH64).
        val aarch64 = elf && head[4] == 2.toByte() && head[5] == 1.toByte() &&
            (head[18].toInt() and 0xff) == 183 && head[19] == 0.toByte()
        require(aarch64) { "$so is not a 64-bit little-endian aarch64 ELF file" }
        require(File(notice.get()).isFile) {
            "No notices file at ${notice.get()}. The library build writes NOTICE next to " +
                "libandroid_runtime.so; set ra64.nativeNotice / RA64_NATIVE_NOTICE to name it."
        }
    }
}

tasks.named<ProcessResources>("processResources") {
    dependsOn(checkNativeLib)
    inputs.property("nativeLib", nativeLib.map { it.path }.orElse(""))
    if (nativeLib.isPresent) {
        from(nativeLib) {
            into("native/linux/aarch64")
            rename { "libandroid_runtime.so" }
        }
        from(nativeNotice) {
            into("META-INF")
            rename { "THIRD_PARTY_NOTICES" }
        }
    }
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    metaInf {
        from(layout.projectDirectory.file("../LICENSE"))
        from(layout.projectDirectory.file("LICENSE-robolectric.txt"))
        val notice = layout.projectDirectory.file("../NOTICE").asFile
        if (notice.isFile) from(notice)
    }
}

tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Implementation-Title" to artifactName,
            "Implementation-Version" to project.version,
            "Robolectric-Version" to robolectricVersion,
            "Android-All-Version" to "16-robolectric-13921718",
        )
    }
}

tasks.named<Javadoc>("javadoc") {
    (options as StandardJavadocDocletOptions).addBooleanOption("Xdoclint:all,-missing", true)
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            artifactId = artifactName
            from(components["java"])
            pom {
                name.set("Robolectric native runtime for Linux aarch64 (unofficial)")
                description.set(
                    "libandroid_runtime.so for Linux aarch64, built from AOSP android-16.0.0_r1 for " +
                        "Robolectric $robolectricVersion SDK 36 (android-all 16-robolectric-13921718), " +
                        "and a NativeRuntimeLoader plugin that loads it. Unofficial; not affiliated " +
                        "with Google or the Robolectric project. Library sources: the AOSP tag plus " +
                        "the build scripts in the project repository.",
                )
                url.set("https://github.com/LavishSonbhurra/robolectric-native-arm64")
                licenses {
                    license {
                        name.set("Apache-2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                        comments.set("Build scripts and loader. The bundled library is under the licenses in META-INF/THIRD_PARTY_NOTICES.")
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

// A published version is immutable, so never publish a jar without the library.
tasks.withType<AbstractPublishToMaven>().configureEach {
    val lib = nativeLib.map { it.path }.orElse("")
    doFirst {
        check(lib.get().isNotEmpty()) { "Refusing to publish without the library: set ra64.nativeLib or RA64_NATIVE_LIB" }
    }
}
