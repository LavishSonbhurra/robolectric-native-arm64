// integration_tests/nativegraphics from the 4.17 tag, against published Robolectric 4.17.
plugins { id("com.android.library") }

val upstream: File by rootProject.extra
val mod = File(upstream, "integration_tests/nativegraphics")

android {
    compileSdk = 36   // upstream: 37; only SDK 36 runs here
    namespace = "org.robolectric.shadows"
    defaultConfig { minSdk = 26 }
    testOptions {
        targetSdk = 36
        unitTests {
            isIncludeAndroidResources = true
            all {
                it.systemProperty("robolectric.graphicsMode", "NATIVE")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    sourceSets {
        getByName("main") {
            manifest.srcFile(File(mod, "src/main/AndroidManifest.xml"))
            res.setSrcDirs(listOf(File(mod, "src/main/res")))
            assets.setSrcDirs(listOf(File(mod, "src/main/assets")))
        }
        getByName("test") {
            java.setSrcDirs(listOf(File(mod, "src/test/java"), rootProject.file("probe/java")))
        }
    }
}

dependencies {
    testCompileOnly("org.robolectric:android-all:16-robolectric-13921718")
    testImplementation("org.robolectric:robolectric:4.17")
    testImplementation("androidx.core:core:1.18.0")
    testImplementation("androidx.test.ext:junit:1.3.0")
    testImplementation("com.google.truth:truth:1.4.5")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.mockito:mockito-core:5.23.0")
    testImplementation("org.mockito:mockito-subclass:5.23.0")
    testImplementation("com.google.guava:guava-testlib:33.6.0-jre")
}

tasks.withType<Test>().configureEach { onlyIf { name.lowercase().contains("debug") } }
