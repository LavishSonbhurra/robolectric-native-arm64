// SPDX-License-Identifier: Apache-2.0
//
// The published jar: a Robolectric NativeRuntimeLoader plugin and its ServiceLoader file, with no
// native library. The libraries are artifacts of their own (libraries/build.gradle.kts); the POM
// depends on them at runtime scope, so this one dependency covers SDK 26 to 37. The x86-pixels
// compat build is left out: it is opt-in.
//
//   ./gradlew :loader:jar
//
// This project is also included by tests/rig (see tests/rig/settings.gradle.kts), where the
// library projects do not exist, so it must not use a version catalog or declare repositories.
plugins {
    `java-library`
    `maven-publish`
}

group = "io.github.lavishsonbhurra"
version = "4.17-1"

val artifactName = "robolectric-nativeruntime-linux-aarch64"
// The loader reflects into this Robolectric release; see DefaultNativeRuntimeLoader.
val robolectricVersion = "4.17"

base { archivesName.set(artifactName) }

java {
    withSourcesJar()
    withJavadocJar()
}

// The level of Robolectric's own jars. Gradle consumers match it against their compile target, so a
// test project that targets Java 11 could not resolve a loader built for 17, though it runs fine.
tasks.withType<JavaCompile>().configureEach { options.release.set(11) }

dependencies {
    // Provided by Robolectric at test time; never bundled and not in the POM.
    compileOnly("org.robolectric:nativeruntime:$robolectricVersion")
    compileOnly("org.robolectric:pluginapi:$robolectricVersion")
    compileOnly("org.robolectric:utils:$robolectricVersion")
    compileOnly("org.robolectric:shadowapi:$robolectricVersion")
    compileOnly("javax.annotation:javax.annotation-api:1.3.2")
    // Real dependencies, not POM text, so Gradle's module metadata gets them too: Gradle consumers
    // read that file and never see the POM.
    listOf(":sdk35", ":sdk36", ":sdk37", ":compat").mapNotNull { findProject(it) }.forEach { runtimeOnly(it) }
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    // Not the modes of the files on disk, which follow the umask of the checkout.
    filePermissions { unix("644") }
    dirPermissions { unix("755") }
    metaInf {
        filePermissions { unix("644") }
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
        )
    }
}

tasks.named<Javadoc>("javadoc") {
    (options as StandardJavadocDocletOptions).addBooleanOption("Xdoclint:all,-missing", true)
}

publishing {
    repositories {
        maven {
            name = "staging"
            url = uri(layout.projectDirectory.dir("../build/central-staging"))
        }
    }
    publications {
        create<MavenPublication>("maven") {
            artifactId = artifactName
            from(components["java"])
            pom {
                name.set("Robolectric native runtime for Linux aarch64 (unofficial)")
                description.set(
                    "A NativeRuntimeLoader plugin for Robolectric $robolectricVersion that loads " +
                        "native runtime libraries built from AOSP source for Linux aarch64. It holds " +
                        "no library: its dependencies are the libraries for SDK 26 to 34, 35, 36 and " +
                        "37. On every other platform the stock loader is used. Unofficial; not " +
                        "affiliated with Google or the Robolectric project.",
                )
                url.set("https://github.com/LavishSonbhurra/robolectric-native-arm64")
                licenses {
                    license {
                        name.set("Apache-2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                        comments.set("Build scripts and loader. The library artifacts this one depends on are under the licenses in their META-INF/THIRD_PARTY_NOTICES.")
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
