plugins {
    id("com.android.library") version "8.11.1" apply false
}

// Shared test settings, mirroring upstream build-logic TestTaskConfiguration.kt, but with a
// small heap and the robolectric.* system properties passed explicitly.
val upstream = rootProject.file("../src")
extra["upstream"] = upstream
// Android SDK location, for the robotests module (plain Java, so AGP does not resolve it).
val androidSdk: File = (System.getenv("ANDROID_HOME") ?: System.getenv("ANDROID_SDK_ROOT")
    ?: rootProject.file("local.properties").takeIf { it.isFile }?.let { f ->
        java.util.Properties().apply { f.inputStream().use { load(it) } }.getProperty("sdk.dir")
    } ?: error("set ANDROID_HOME or sdk.dir in local.properties")).let(::File)
extra["androidSdk"] = androidSdk

subprojects {
    tasks.withType<Test>().configureEach {
        maxParallelForks = 1
        // SDK 36 needs a Java 21 test JVM (android-all 16 is class file 65).
        providers.gradleProperty("suite.java").orNull?.let { executable = it }
        minHeapSize = "256m"
        maxHeapSize = providers.gradleProperty("suite.heap").getOrElse("2g")
        jvmArgs(
            "--add-opens=java.base/java.lang=ALL-UNNAMED",
            "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
            "--add-opens=java.base/java.io=ALL-UNNAMED",
            "--add-opens=java.base/java.net=ALL-UNNAMED",
            "--add-opens=java.base/java.nio=ALL-UNNAMED",
            "--add-opens=java.base/java.security=ALL-UNNAMED",
            "--add-opens=java.base/java.text=ALL-UNNAMED",
            "--add-opens=java.base/java.util=ALL-UNNAMED",
            "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
            "--add-opens=java.desktop/java.awt.font=ALL-UNNAMED",
            "-XX:ErrorFile=" + rootProject.file(".work/hs_err/hs_err_pid%p.log").path,
        )
        doFirst { rootProject.file(".work/hs_err").mkdirs() }
        // Only SDK 36 (BAKLAVA).
        systemProperty("robolectric.enabledSdks", providers.gradleProperty("suite.sdks").getOrElse("36"))
        systemProperty("robolectric.enableFrameInfoVsyncOffsetFix", "true")
        // Robolectric extracts about 60 MB per sandbox (library, fonts, ICU data) into java.io.tmpdir.
        // Keep it under .work/ rather than /tmp, which is often RAM-backed.
        val tmp = rootProject.file(".work/tmp/${project.name}")
        doFirst { tmp.mkdirs() }
        systemProperty("java.io.tmpdir", tmp.path)
        System.getenv("QEMU_LD_PREFIX")?.let { environment("QEMU_LD_PREFIX", it) }
        // Otherwise Gradle runs static inner classes like TestRunnerSequenceTest$SimpleTest
        exclude("**/*\$*")
        ignoreFailures = true
        testLogging {
            events("failed", "skipped")
            exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        }
        outputs.upToDateWhen { false }
    }
}
