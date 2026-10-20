// SPDX-License-Identifier: Apache-2.0
//
// The fidelity rig: an Android app module whose unit tests render the scenes. The loader is
// the repository's own loader/ project, included here so the rig always tests the current
// sources. Run from the repository root with ./gradlew -p tests/rig ..., or use scripts/run.sh.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "robolectric-arm64-rig"
include(":app", ":loader")
project(":loader").projectDir = file("../../loader")
