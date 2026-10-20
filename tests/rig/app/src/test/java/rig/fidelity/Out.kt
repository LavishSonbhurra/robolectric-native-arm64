package rig.fidelity

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.app.Activity
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.PixelCopy
import org.robolectric.Shadows.shadowOf
import java.io.File
import java.io.FileOutputStream

/** Where the rig writes its pictures, set by the build (rig.out.dir). */
object Out {
    val dir: File = File(System.getProperty("rig.out.dir") ?: "build/rig-out").apply { mkdirs() }

    fun png(name: String): File = File(dir, "$name.png")

    /** PNG through the native encoder (Bitmap.compress), like an app would. */
    fun save(name: String, bitmap: Bitmap) {
        FileOutputStream(png(name)).use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        recordEnv()
    }

    /** Plain text output (metrics); compare.py diffs these line by line. */
    fun text(name: String, content: String) {
        File(dir, "$name.txt").writeText(content)
        recordEnv()
    }

    /**
     * A fresh white ARGB_8888 bitmap, [draw] on it, saved as [name]. White, not transparent,
     * so the PNGs are easy to look at and alpha bugs still show as colour differences.
     */
    fun scene(name: String, w: Int = 256, h: Int = 256, draw: Canvas.() -> Unit) {
        val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.WHITE)
        canvas.draw()
        save(name, bitmap)
    }

    private var envWritten = false

    /** Which library and JVM produced this directory: _env.txt. */
    private fun recordEnv() {
        if (envWritten) return
        envWritten = true
        val keys = listOf("os.name", "os.arch", "java.version", "java.vendor", "robolectric.arm64.loadedFrom")
        val lines = keys.map { "$it=${System.getProperty(it)}" } + "sdk=${Build.VERSION.SDK_INT}"
        File(dir, "_env.txt").writeText(lines.joinToString("\n", postfix = "\n"))
    }
}

/** Phone-ish screen for the View and Compose scenes, small enough for qemu: 720 x 1280 px. */
const val SCREEN = "w360dp-h640dp-port-xhdpi"

/**
 * The whole window through PixelCopy. With robolectric.pixelCopyRenderMode=hardware this is
 * Robolectric's HardwareRenderer path (RenderNodes, elevation shadows, RenderEffect, AGSL).
 */
fun pixelCopy(a: Activity): Bitmap {
    shadowOf(Looper.getMainLooper()).idle()
    val decor = a.window.decorView
    val b = Bitmap.createBitmap(decor.width, decor.height, Bitmap.Config.ARGB_8888)
    var result = -1
    PixelCopy.request(a.window, b, { result = it }, Handler(Looper.getMainLooper()))
    shadowOf(Looper.getMainLooper()).idle()
    check(result == PixelCopy.SUCCESS) { "PixelCopy result $result" }
    return b
}
