// Runs Robolectric 4.17's own native-runtime test suites (sources from ../src, the
// robolectric-4.17 tag) against the published 4.17 artifacts, at SDK 36 only.
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "robolectric-4.17-upstream-suites"
include(":robotests", ":nativegraphics", ":testapp", ":ctesque")
