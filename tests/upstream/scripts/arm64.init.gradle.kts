// Gradle init script: makes any Robolectric 4.17 build load a Linux arm64
// libandroid_runtime.so for SDK 36 tests, without editing the build.
//
//   gradle -I arm64.init.gradle.kts \
//     -Parm64.loaderJar=/abs/loader.jar \
//     -Parm64.nativeLibrary=/abs/libandroid_runtime.so  ...
//
// It adds the loader plugin jar (robolectricarm64.LinuxArm64NativeRuntimeLoader, found by
// Robolectric's NativeRuntimeLoader ServiceLoader lookup) to every testRuntimeOnly
// configuration, Java and Android modules alike, and passes the library path to every Test
// task as -Drobolectric.arm64.nativeLibrary.
val props = gradle.startParameter.projectProperties
val loaderJar = props["arm64.loaderJar"] ?: error("set -Parm64.loaderJar=/abs/path/loader.jar")
val nativeLibrary = props["arm64.nativeLibrary"]

gradle.allprojects {
    val p = this
    configurations.matching { it.name == "testRuntimeOnly" }.configureEach {
        dependencies.add(p.dependencies.create(p.files(loaderJar)))
    }
    tasks.withType<Test>().configureEach {
        if (nativeLibrary != null) systemProperty("robolectric.arm64.nativeLibrary", nativeLibrary)
    }
}
