// SPDX-License-Identifier: Apache-2.0
//
// The root build holds the published jars: :loader (plugin + SDK 36 library), :compat (the
// SDK <= 34 library, native arm64 pixels) and :compat-x86pixels (the same library built with
// RA64_PIXELS=x86). Both compat projects use compat/build.gradle.kts. The fidelity rig in tests/rig is a
// separate Android build that includes the same loader project: ./gradlew -p tests/rig ...

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "robolectric-native-arm64"
include(":loader")
include(":compat")
include(":compat-x86pixels")
project(":compat-x86pixels").projectDir = file("compat/x86pixels")
project(":compat-x86pixels").buildFileName = "../build.gradle.kts"
