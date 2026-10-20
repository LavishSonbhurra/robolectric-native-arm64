// integration_tests/ctesque (sharedTest) from the 4.17 tag, against published Robolectric 4.17.
plugins { id("com.android.library") }
val upstream: File by rootProject.extra
val mod = File(upstream, "integration_tests/ctesque")
android {
    compileSdk = 36   // upstream: 37
    namespace = "org.robolectric.integrationtests.ctesque"
    defaultConfig { minSdk = 23 }
    lint { abortOnError = false }
    testOptions {
        targetSdk = 36
        unitTests {
            isIncludeAndroidResources = true
            all { it.systemProperty("robolectric.graphicsMode", "NATIVE") }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    androidResources { noCompress.add("txt") }
    sourceSets {
        getByName("main") {
            manifest.srcFile(File(mod, "src/main/AndroidManifest.xml"))
            java.setSrcDirs(listOf(File(mod, "src/main/java")))
            res.setSrcDirs(listOf(File(mod, "src/main/res")))
            assets.setSrcDirs(listOf(File(mod, "src/main/assets")))
        }
        getByName("test") {
            java.setSrcDirs(listOf(File(mod, "src/sharedTest/java"), rootProject.file("probe/java")))
            resources.setSrcDirs(listOf(File(mod, "src/sharedTest/resources")))
        }
    }
}
dependencies {
    implementation(project(":testapp"))
    testCompileOnly("org.robolectric:android-all:16-robolectric-13921718")
    testImplementation("org.robolectric:robolectric:4.17")
    testImplementation("junit:junit:4.13.2")
    testImplementation("androidx.test:monitor:1.8.0")
    testImplementation("androidx.test:runner:1.7.0")
    testImplementation("androidx.test:rules:1.7.0")
    testImplementation("androidx.test.ext:junit:1.3.0")
    testImplementation("androidx.test.ext:truth:1.7.0")
    testImplementation("androidx.test:core:1.7.0")
    testImplementation("androidx.test.espresso:espresso-core:3.7.0")
    testImplementation("com.google.truth:truth:1.4.5")
    testImplementation("com.google.guava:guava:33.6.0-jre")
}
tasks.withType<Test>().configureEach { onlyIf { name.lowercase().contains("debug") } }
