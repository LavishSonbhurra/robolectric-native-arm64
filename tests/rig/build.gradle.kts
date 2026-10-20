plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}

// Build the shared loader project under this build's directory, so a rig run never overwrites
// the jar the root build put in loader/build.
project(":loader") {
    layout.buildDirectory.set(rootProject.layout.buildDirectory.dir("loader"))
}
