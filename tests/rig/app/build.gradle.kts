plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "rig.fidelity"
    compileSdk = 36

    defaultConfig {
        applicationId = "rig.fidelity"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "1"
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all { configureRig(it) }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

/**
 * Every knob comes in as a Gradle property so scripts/run.sh can switch JVM and library:
 *   rig.java      test JVM (must be Java 21: SDK 36's android-all is class file 65)
 *   rig.out       output directory for the PNGs
 *   rig.nativeLib absolute path of a libandroid_runtime to force through the arm64 loader
 *   rig.stock     leave the arm64 loader jar off the classpath (pure upstream baseline)
 *   rig.loaderJar use this prebuilt loader jar instead of the :loader project (for example
 *                 the release jar with the library bundled)
 *   rig.heap      test JVM heap (default 1280m)
 *   rig.tmp       java.io.tmpdir for the test JVM (default .work/tmp, on disk)
 *   rig.sdk       SDK level to run (default 36; tests say sdk = ALL_SDKS, this filters)
 *   rig.nativeLibSdk SDK level rig.nativeLib was built for (default 36; below 35 means the
 *                 SDK <= 34 compat library, librobolectric-nativeruntime)
 *   rig.compatJar also put these compat jars (comma-separated; the SDK <= 34 library as a
 *                 classpath resource) on the test classpath (tests the release artifacts; leave
 *                 rig.nativeLib unset)
 *   rig.compatPixels native or x86: which compat jar the loader takes when both are present
 */
fun configureRig(test: Test) {
    val p = providers
    test.maxParallelForks = 1
    test.maxHeapSize = p.gradleProperty("rig.heap").getOrElse("1280m")
    p.gradleProperty("rig.java").orNull?.let { test.executable = it }
    // Robolectric's FileDescriptor interceptor and friends reach into java.base on JDK 17+.
    test.jvmArgs(
        "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED",
    )
    System.getenv("QEMU_LD_PREFIX")?.let { test.environment("QEMU_LD_PREFIX", it) }
    // Robolectric extracts the library, fonts and ICU data (about 60 MB) under java.io.tmpdir;
    // keep that on disk rather than a RAM-backed /tmp.
    val tmp = p.gradleProperty("rig.tmp").getOrElse(rootProject.file(".work/tmp").path)
    test.doFirst { file(tmp).mkdirs() }
    test.systemProperty("java.io.tmpdir", tmp)
    test.systemProperty("robolectric.graphicsMode", "NATIVE")
    test.systemProperty("robolectric.pixelCopyRenderMode", "hardware")
    test.systemProperty("roborazzi.test.record", "true")
    test.systemProperty("rig.out.dir", p.gradleProperty("rig.out").getOrElse(layout.buildDirectory.dir("rig-out").get().asFile.path))
    p.gradleProperty("rig.nativeLib").orNull?.let { test.systemProperty("robolectric.arm64.nativeLibrary", it) }
    test.systemProperty("robolectric.enabledSdks", p.gradleProperty("rig.sdk").getOrElse("36"))
    p.gradleProperty("rig.nativeLibSdk").orNull?.let { test.systemProperty("robolectric.arm64.nativeLibrarySdk", it) }
    p.gradleProperty("rig.compatPixels").orNull?.let { test.systemProperty("robolectric.arm64.compatPixels", it) }
    test.testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
    // Pictures are the output; always render again.
    test.outputs.upToDateWhen { false }
}

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    // Registers ComponentActivity for createAndroidComposeRule.
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
    if (!providers.gradleProperty("rig.stock").isPresent) {
        val loaderJar = providers.gradleProperty("rig.loaderJar")
        if (loaderJar.isPresent) {
            testRuntimeOnly(files(loaderJar.get()))
        } else {
            // The library is bundled only if ra64.nativeLib or RA64_NATIVE_LIB is set.
            testRuntimeOnly(project(":loader"))
        }
        providers.gradleProperty("rig.compatJar").orNull?.let { jars ->
            testRuntimeOnly(files(jars.split(',').filter { it.isNotBlank() }))
        }
    }
}
