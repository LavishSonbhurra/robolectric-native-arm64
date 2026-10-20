// SPDX-License-Identifier: Apache-2.0
//
// The root build holds only the published jar (:loader). The fidelity rig in tests/rig is a
// separate Android build that includes the same loader project: ./gradlew -p tests/rig ...

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "robolectric-native-arm64"
include(":loader")
