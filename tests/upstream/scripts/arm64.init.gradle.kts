// Gradle init script: makes any Robolectric 4.17 build load a Linux arm64 native runtime on
// arm64, without editing the build. Two ways to name it:
//
//   gradle -I arm64.init.gradle.kts \
//     -Parm64.artifactRepo=/abs/central-staging -Parm64.artifactVersion=4.17-1  ...
//
// resolves robolectric-nativeruntime-linux-aarch64 and its library artifacts from that Maven
// repository, as a user's build does, and adds it to every testRuntimeOnly configuration.
//
//   gradle -I arm64.init.gradle.kts \
//     -Parm64.loaderJar=/abs/loader.jar \
//     -Parm64.nativeLibrary=/abs/libandroid_runtime.so  -Parm64.nativeLibrarySdk=35 ...
//
// adds the loader plugin jar (robolectricarm64.LinuxArm64NativeRuntimeLoader, found by
// Robolectric's NativeRuntimeLoader ServiceLoader lookup) and passes the library path to every
// Test task as -Drobolectric.arm64.nativeLibrary.
val props = gradle.startParameter.projectProperties
val artifactRepo = props["arm64.artifactRepo"]
val artifactVersion = props["arm64.artifactVersion"]
val loaderJar = props["arm64.loaderJar"]
check(loaderJar != null || (artifactRepo != null && artifactVersion != null)) {
    "set -Parm64.loaderJar=/abs/path/loader.jar, or -Parm64.artifactRepo and -Parm64.artifactVersion"
}
val nativeLibrary = props["arm64.nativeLibrary"]
// The SDK level nativeLibrary was built for; 34 for the SDK <= 34 library (librobolectric-nativeruntime.so).
val nativeLibrarySdk = props["arm64.nativeLibrarySdk"]

if (artifactRepo != null) {
    gradle.beforeSettings {
        dependencyResolutionManagement.repositories.maven {
            url = uri(artifactRepo)
            content { includeGroup("io.github.lavishsonbhurra") }
        }
    }
}

gradle.allprojects {
    val p = this
    configurations.matching { it.name == "testRuntimeOnly" }.configureEach {
        val plugin: Any =
            if (artifactVersion != null) "io.github.lavishsonbhurra:robolectric-nativeruntime-linux-aarch64:$artifactVersion"
            else p.files(loaderJar)
        dependencies.add(p.dependencies.create(plugin))
    }
    tasks.withType<Test>().configureEach {
        if (nativeLibrary != null) systemProperty("robolectric.arm64.nativeLibrary", nativeLibrary)
        if (nativeLibrarySdk != null) systemProperty("robolectric.arm64.nativeLibrarySdk", nativeLibrarySdk)
    }
}
