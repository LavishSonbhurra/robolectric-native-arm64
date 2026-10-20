package rig.fidelity

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import java.util.concurrent.atomic.AtomicReference
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.nativeruntime.DefaultNativeRuntimeLoader

/**
 * Records which NativeRuntimeLoader Robolectric picked and which library file it loaded
 * (_loader.txt). On a machine with no usable library this test fails during sandbox setup,
 * and the failure message is the evidence of what the loader looked for.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [36])
class LoaderProbeTest {
    @Test
    fun recordLoader() {
        val field = DefaultNativeRuntimeLoader::class.java.getDeclaredField("nativeRuntimeLoader").apply { isAccessible = true }
        val chosen = (field.get(null) as AtomicReference<*>).get()
        val lines = listOf(
            "loader=${chosen?.javaClass?.name}",
            "loadedFrom=${System.getProperty("robolectric.arm64.loadedFrom")}",
            "os.arch=${System.getProperty("os.arch")}",
            "java.version=${System.getProperty("java.version")}",
        )
        java.io.File(Out.dir, "_loader.txt").writeText(lines.joinToString("\n", postfix = "\n"))
        // One native draw, so a library that loads but cannot render also shows up here.
        val b = Bitmap.createBitmap(4, 4, Bitmap.Config.ARGB_8888)
        Canvas(b).drawCircle(2f, 2f, 2f, Paint().apply { color = Color.RED; isAntiAlias = true })
        check(b.getPixel(2, 2) == Color.RED) { "native draw gave ${Integer.toHexString(b.getPixel(2, 2))}" }
    }
}
