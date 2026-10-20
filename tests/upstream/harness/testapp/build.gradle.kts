plugins { id("com.android.library") }
val upstream: File by rootProject.extra
val mod = File(upstream, "testapp")
android {
    compileSdk = 36   // upstream: 30
    namespace = "org.robolectric.testapp"
    defaultConfig { minSdk = 23 }
    lint { abortOnError = false }
    sourceSets {
        getByName("main") {
            manifest.srcFile(File(mod, "src/main/AndroidManifest.xml"))
            java.setSrcDirs(listOf(File(mod, "src/main/java")))
            res.setSrcDirs(listOf(File(mod, "src/main/res")))
            assets.setSrcDirs(listOf(File(mod, "src/main/assets")))
        }
    }
}
