// SPDX-License-Identifier: Apache-2.0
//
// The root build holds the published jars: :loader (the plugin, no library), :sdk35, :sdk36 and
// :sdk37 (libandroid_runtime.so per SDK), :compat (the SDK <= 34 library, native arm64 pixels) and
// :compat-x86pixels (the same library built with RA64_PIXELS=x86). The five library projects share
// libraries/build.gradle.kts. The fidelity rig in tests/rig is a separate Android build that
// includes the same loader project: ./gradlew -p tests/rig ...

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "robolectric-native-arm64"
include(":loader")
listOf("sdk35", "sdk36", "sdk37", "compat", "compat-x86pixels").forEach { name ->
    include(":$name")
    project(":$name").projectDir = file("libraries/$name")
    project(":$name").buildFileName = "../build.gradle.kts"
}
