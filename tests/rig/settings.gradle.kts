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

// rig.artifactRepo: a Maven repository with the published artifacts (build/central-staging of the
// root build), for runs that resolve them the way a user does. See rig.artifact in app/.
val artifactRepo: String? = providers.gradleProperty("rig.artifactRepo").orNull

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (artifactRepo != null) {
            maven {
                url = uri(artifactRepo)
                content { includeGroup("io.github.lavishsonbhurra") }
            }
        }
        google()
        mavenCentral()
    }
}

rootProject.name = "robolectric-arm64-rig"
include(":app", ":loader")
project(":loader").projectDir = file("../../loader")
