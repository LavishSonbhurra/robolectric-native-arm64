// robolectric/src/test from the 4.17 tag, compiled against the published 4.17 artifacts.
import org.gradle.api.artifacts.transform.InputArtifact
import org.gradle.api.artifacts.transform.TransformAction
import org.gradle.api.artifacts.transform.TransformOutputs
import org.gradle.api.artifacts.transform.TransformParameters
import org.gradle.api.artifacts.type.ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE
import java.util.zip.ZipFile

plugins { `java-library` }

val upstream: File by rootProject.extra
val androidSdk: File by rootProject.extra
val mod = File(upstream, "robolectric")

/** Same job as upstream's AarDepsPlugin: an AAR becomes its classes.jar. */
abstract class AarClassesJar : TransformAction<TransformParameters.None> {
    @get:InputArtifact abstract val aar: Provider<FileSystemLocation>
    override fun transform(outputs: TransformOutputs) {
        val f = aar.get().asFile
        val out = outputs.file(f.nameWithoutExtension + "-classes.jar")
        ZipFile(f).use { z ->
            val e = z.getEntry("classes.jar") ?: error("no classes.jar in $f")
            z.getInputStream(e).use { i -> out.outputStream().use { o -> i.copyTo(o) } }
        }
    }
}
dependencies.registerTransform(AarClassesJar::class) {
    from.attribute(ARTIFACT_TYPE_ATTRIBUTE, "aar")
    to.attribute(ARTIFACT_TYPE_ATTRIBUTE, "jar")
}
afterEvaluate {
    configurations.filter { it.name.endsWith("Classpath") }.forEach {
        it.attributes { attribute(ARTIFACT_TYPE_ATTRIBUTE, "jar") }
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "utf-8"
    options.compilerArgs.addAll(listOf("-Xlint:-options", "-nowarn", "-Xmaxerrs", "2000"))
}

// Files that need SDK 37 (CINNAMON_BUN) APIs; we compile against android-all 16.
val excluded = (findProperty("suite.robotests.exclude") as String? ?: "").split(",").filter { it.isNotBlank() } + listOf(
    "**/ShadowSubscriptionManagerTest.java",
    "**/ShadowPackageInstallerTest.java",
    "**/ShadowAccessibilityNodeInfoTest.java",
    "**/ShadowRemoteViewsAdapterTest.java",
    "**/ShadowAdvancedProtectionManagerTest.java",
    "**/ShadowBluetoothDeviceTest.java",
    "**/ShadowTimeManagerTest.java",
)
sourceSets {
    test {
        java.setSrcDirs(listOf(File(mod, "src/test/java"), rootProject.file("probe/java")))
        java.exclude(excluded)
        resources.setSrcDirs(listOf(File(mod, "src/test/resources")))
    }
}

dependencies {
    testImplementation("org.robolectric:robolectric:4.17")
    testImplementation("androidx.annotation:annotation:1.9.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.google.truth:truth:1.4.5")
    testImplementation("org.mockito:mockito-core:5.23.0")
    testImplementation("org.mockito:mockito-subclass:5.23.0")
    testImplementation("org.hamcrest:hamcrest:3.0")
    testImplementation("androidx.test:core:1.7.0@aar")
    testImplementation("androidx.test.ext:junit:1.3.0@aar")
    testImplementation("androidx.test.ext:truth:1.7.0@aar")
    testImplementation("androidx.test:runner:1.7.0@aar")
    testImplementation("androidx.test:monitor:1.8.0@aar")
    testImplementation("androidx.test.espresso:espresso-idling-resource:3.7.0@aar")
    testImplementation("com.google.testparameterinjector:test-parameter-injector:1.22")
    testImplementation("com.google.guava:guava:33.6.0-jre")
    testImplementation("com.google.guava:guava-testlib:33.6.0-jre")
    testImplementation("com.almworks.sqlite4java:sqlite4java:1.0.392")
    testCompileOnly("com.google.code.findbugs:jsr305:3.0.2")
    testCompileOnly("org.robolectric:android-all:16-robolectric-13921718")
    testRuntimeOnly(files(File(androidSdk, "platforms/android-36/android.jar")))
}

tasks.withType<Test>().configureEach {
    // test_config.properties paths are relative to the module directory.
    workingDir = mod
}
