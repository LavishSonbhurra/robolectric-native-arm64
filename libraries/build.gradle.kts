// SPDX-License-Identifier: Apache-2.0
//
// The native library artifacts for Linux aarch64: jars with a library, its notices and no code.
// This file builds all five projects (see settings.gradle.kts). Each project directory has a
// gradle.properties with its version and, for an SDK library, what it was built from.
//
//   :sdk35, :sdk36, :sdk37  robolectric-nativeruntime-sdk<NN>-linux-aarch64: libandroid_runtime.so
//                           as native/linux/aarch64/sdk<NN>/libandroid_runtime.so. One path per SDK,
//                           so all three can be on the classpath; the loader picks by SDK level.
//   :compat                 robolectric-nativeruntime-compat-linux-aarch64: the SDK <= 34 library,
//                           native arm64 pixels, as native/linux/aarch64/librobolectric-nativeruntime.so
//                           (the path org.robolectric:nativeruntime-dist-compat uses for x86_64)
//   :compat-x86pixels       robolectric-nativeruntime-compat-linux-aarch64-x86pixels: the
//                           RA64_PIXELS=x86 build, as native/linux/aarch64/x86-pixels/
//                           librobolectric-nativeruntime.so. Its own path, so both compat jars can be
//                           on the classpath: the loader takes the native one unless
//                           robolectric.arm64.compatPixels=x86.
//
// The library is a build product and is never committed. Name it with a Gradle property or an
// environment variable:
//
//   ./gradlew :sdk35:jar -Pra64.sdk35Lib=/abs/path/libandroid_runtime.so            (RA64_SDK35_LIB)
//   ./gradlew :compat:jar -Pra64.compatLib=/abs/path/librobolectric-nativeruntime.so (RA64_COMPAT_LIB)
//   ./gradlew :compat-x86pixels:jar -Pra64.compatX86Lib=/abs/path/...                (RA64_COMPAT_X86_LIB)
//
// The NOTICE file next to the library (CMake output) or THIRD_PARTY_NOTICES (release layout) goes
// in as META-INF/THIRD_PARTY_NOTICES; ra64.sdk35Notice, ra64.compatNotice, ra64.compatX86Notice
// (RA64_SDK35_NOTICE, ...) name another file. A jar cannot be built without its library, so
// publishing cannot produce an empty one.
//
// Versions: <android-all build>-<our build number> for the SDK libraries,
// <nativeruntime-dist-compat version>-<our build number> for compat.
plugins {
    `java-library`
    `maven-publish`
}

group = "io.github.lavishsonbhurra"

val sdk = findProperty("library.sdk")?.toString()
val androidAll = findProperty("library.androidAll")?.toString()
val aospTag = findProperty("library.aospTag")?.toString()
val x86Pixels = project.name == "compat-x86pixels"
// In the property and environment names: ra64.sdk35Lib, RA64_SDK35_LIB.
val settingName = if (sdk != null) "sdk$sdk" else if (x86Pixels) "compatX86" else "compat"
val envName = if (sdk != null) "SDK$sdk" else if (x86Pixels) "COMPAT_X86" else "COMPAT"

val artifactName = when {
    sdk != null -> "robolectric-nativeruntime-sdk$sdk-linux-aarch64"
    x86Pixels -> "robolectric-nativeruntime-compat-linux-aarch64-x86pixels"
    else -> "robolectric-nativeruntime-compat-linux-aarch64"
}
val resourceDir = when {
    sdk != null -> "native/linux/aarch64/sdk$sdk"
    x86Pixels -> "native/linux/aarch64/x86-pixels"
    else -> "native/linux/aarch64"
}
val libraryName = if (sdk != null) "libandroid_runtime.so" else "librobolectric-nativeruntime.so"
base { archivesName.set(artifactName) }

java {
    withSourcesJar()
    withJavadocJar()
    // There is no bytecode here, so no consumer's Java version should rule these jars out. Without
    // this, Gradle's module metadata would say "needs the JDK that ran the build".
    targetCompatibility = JavaVersion.VERSION_1_8
}

fun pathSetting(property: String, env: String): Provider<File> =
    providers.gradleProperty(property).orElse(providers.environmentVariable(env)).map {
        val f = File(it)
        if (f.isAbsolute) f else gradle.startParameter.currentDir.resolve(it)
    }

val library: Provider<File> = pathSetting("ra64.${settingName}Lib", "RA64_${envName}_LIB")
val libraryNotice: Provider<File> =
    pathSetting("ra64.${settingName}Notice", "RA64_${envName}_NOTICE").orElse(
        library.map { lib ->
            lib.resolveSibling("NOTICE").takeIf { it.isFile } ?: lib.resolveSibling("THIRD_PARTY_NOTICES")
        },
    )

val checkLibrary by tasks.registering {
    description = "Checks that the library to bundle is a Linux aarch64 ELF file with a NOTICE file."
    val lib = library.map { it.path }.orElse("")
    val notice = libraryNotice.map { it.path }.orElse("")
    val setting = "ra64.${settingName}Lib / RA64_${envName}_LIB"
    inputs.property("library", lib)
    inputs.property("libraryNotice", notice)
    doLast {
        val so = File(lib.get())
        require(lib.get().isNotEmpty() && so.isFile) { "$setting: no such file: $so" }
        val head = so.inputStream().use { it.readNBytes(20) }
        val elf = head.size == 20 && head[0] == 0x7f.toByte() && String(head, 1, 3, Charsets.US_ASCII) == "ELF"
        // e_ident[EI_CLASS] = 2 (64-bit), e_ident[EI_DATA] = 1 (little endian), e_machine = 183 (EM_AARCH64).
        val aarch64 = elf && head[4] == 2.toByte() && head[5] == 1.toByte() &&
            (head[18].toInt() and 0xff) == 183 && head[19] == 0.toByte()
        require(aarch64) { "$so is not a 64-bit little-endian aarch64 ELF file" }
        require(File(notice.get()).isFile) { "No notices file at ${notice.get()}; set the notice property" }
    }
}

tasks.named<ProcessResources>("processResources") {
    dependsOn(checkLibrary)
    inputs.property("library", library.map { it.path }.orElse(""))
    from(library) {
        into(resourceDir)
        rename { libraryName }
    }
    from(libraryNotice) {
        into("META-INF")
        rename { "THIRD_PARTY_NOTICES" }
    }
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    // Not the modes of the files on disk, which follow the umask of the checkout.
    filePermissions { unix("644") }
    dirPermissions { unix("755") }
    metaInf {
        filePermissions { unix("644") }
        from(rootProject.layout.projectDirectory.file("LICENSE"))
        from(rootProject.layout.projectDirectory.file("NOTICE"))
    }
}

val libraryAttributes: Map<String, Any?> =
    if (sdk != null) {
        mapOf("Android-All-Version" to androidAll, "Android-Sdk-Level" to sdk)
    } else {
        mapOf("Nativeruntime-Dist-Compat-Version" to "1.0.19", "Ra64-Pixels" to if (x86Pixels) "x86" else "native")
    }

tasks.named<Jar>("jar") {
    manifest {
        attributes(mapOf("Implementation-Title" to artifactName, "Implementation-Version" to project.version))
        attributes(libraryAttributes)
    }
}

// There is no code here, so the sources and javadoc jars say where the sources are. An SDK
// library's own SOURCES.txt names its AOSP tag.
listOf("sourcesJar", "javadocJar").forEach { name ->
    tasks.named<Jar>(name) {
        val own = layout.projectDirectory.file("SOURCES.txt")
        from(if (own.asFile.isFile) own else rootProject.layout.projectDirectory.file("SOURCES.txt"))
    }
}

// Sentences the notices require in the documentation. Check them against the top of
// THIRD_PARTY_NOTICES when a library changes (config/notices-extra.toml, [[attribution]]).
val dngNotice = "This product includes DNG technology under license by Adobe Systems Incorporated."
val gainMapNotice = "This product includes Gain Map technology under license by Adobe."
val unofficial = "Unofficial; not affiliated with Google or the Robolectric project."

val pomName = when {
    sdk != null -> "Robolectric SDK $sdk native runtime for Linux aarch64 (unofficial)"
    x86Pixels -> "Robolectric SDK <= 34 native runtime for Linux aarch64, x86 pixels (unofficial)"
    else -> "Robolectric SDK <= 34 native runtime for Linux aarch64 (unofficial)"
}
val pomDescription = if (sdk != null) {
    "libandroid_runtime.so for Linux aarch64, built from AOSP $aospTag for Robolectric SDK $sdk " +
        "(android-all $androidAll). Load it with the plugin in " +
        "robolectric-nativeruntime-linux-aarch64. $unofficial Library sources: the AOSP tag plus " +
        "the build scripts in the project repository. " +
        // MPL-2.0 section 3.2: recipients of the binary are told where the source is.
        (if (sdk == "37") "Eigen is included under the Mozilla Public License 2.0; its source is " +
            "external/eigen at the same AOSP tag. " else "") +
        "$dngNotice $gainMapNotice"
} else {
    "librobolectric-nativeruntime.so for Linux aarch64, built from AOSP " +
        "android12-hostruntime-dev at the source of org.robolectric:nativeruntime-dist-compat 1.0.19" +
        (if (x86Pixels) ", with Skia's x86 code paths so that images match the x86_64 build" else "") +
        ". Load it with the plugin in robolectric-nativeruntime-linux-aarch64. $unofficial $dngNotice"
}

publishing {
    repositories {
        maven {
            name = "staging"
            url = uri(rootProject.layout.projectDirectory.dir("build/central-staging"))
        }
    }
    publications {
        create<MavenPublication>("maven") {
            artifactId = artifactName
            from(components["java"])
            pom {
                name.set(pomName)
                description.set(pomDescription)
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
