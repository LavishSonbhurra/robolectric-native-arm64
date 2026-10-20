package rig.fidelity

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapRegionDecoder
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageDecoder
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Bitmap scaling filters, decoders (PNG, JPEG, WebP), encoders and pixel configs. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [36], qualifiers = SCREEN)
class BitmapScenesTest {
    private fun bytes(name: String): ByteArray =
        checkNotNull(javaClass.classLoader!!.getResourceAsStream("images/$name")) { "missing images/$name" }.readBytes()

    private fun decode(name: String, opts: BitmapFactory.Options? = null): Bitmap {
        val b = bytes(name)
        return checkNotNull(BitmapFactory.decodeByteArray(b, 0, b.size, opts)) { "decode failed: $name" }
    }

    /** 16 x 16 pattern with hard edges, a gradient and a one-pixel grid: shows every filter. */
    private fun pattern(): Bitmap = Bitmap.createBitmap(16, 16, Bitmap.Config.ARGB_8888).apply {
        for (y in 0 until 16) for (x in 0 until 16) {
            val c = when {
                x == 0 || y == 0 -> Color.BLACK
                x < 8 && y < 8 -> if ((x + y) % 2 == 0) Color.RED else Color.WHITE
                x >= 8 && y < 8 -> Color.rgb(x * 16, y * 30, 255 - x * 16)
                x < 8 -> Color.argb(64 + y * 10, 0, 160, 0)
                else -> if (x == y) Color.BLUE else Color.rgb(250, 250, 200)
            }
            setPixel(x, y, c)
        }
    }

    @Test
    fun scalingFilters() = Out.scene("bitmap-scaling-filters", 320, 320) {
        val src = pattern()
        drawBitmap(src, null, RectF(0f, 0f, 150f, 150f), Paint().apply { isFilterBitmap = false })
        drawBitmap(src, null, RectF(160f, 0f, 310f, 150f), Paint().apply { isFilterBitmap = true })
        // Fractional, rotated draw with filtering.
        save(); translate(80f, 235f); rotate(20f); scale(4.3f, 4.3f)
        drawBitmap(src, -8f, -8f, Paint().apply { isFilterBitmap = true; isAntiAlias = true })
        restore()
        // Downscale a big stripe pattern: aliasing vs. filtering vs. mipmaps.
        val big = Bitmap.createBitmap(256, 256, Bitmap.Config.ARGB_8888)
        Canvas(big).apply {
            drawColor(Color.WHITE)
            val p = Paint().apply { color = Color.BLACK; strokeWidth = 1f }
            for (i in 0 until 256 step 3) drawLine(i.toFloat(), 0f, 0f, i.toFloat(), p)
        }
        drawBitmap(big, null, RectF(170f, 170f, 234f, 234f), Paint().apply { isFilterBitmap = false })
        drawBitmap(big, null, RectF(246f, 170f, 310f, 234f), Paint().apply { isFilterBitmap = true })
        big.setHasMipMap(true)
        drawBitmap(big, null, RectF(170f, 246f, 234f, 310f), Paint().apply { isFilterBitmap = true })
        drawBitmap(Bitmap.createScaledBitmap(big, 64, 64, true), 246f, 246f, null)
    }

    @Test
    fun decodeFormats() {
        val names = listOf(
            "photo-rgba.png", "photo-palette.png", "photo-gray.png", "photo-q90-420.jpg",
            "photo-q75-444-progressive.jpg", "photo-lossy.webp", "photo-lossless.webp",
        )
        Out.scene("bitmap-decode-bitmapfactory", 2 * 96 + 30, names.size * 70) {
            for ((i, n) in names.withIndex()) {
                val b = decode(n)
                drawBitmap(b, 5f, i * 70f + 3f, null)
                drawBitmap(b, null, RectF(110f, i * 70f + 3f, 110f + 96f * 1.15f, i * 70f + 3f + 64f), Paint().apply { isFilterBitmap = true })
            }
        }
        Out.scene("bitmap-decode-imagedecoder", 96 + 10, names.size * 70) {
            for ((i, n) in names.withIndex()) {
                val src = ImageDecoder.createSource(ByteBuffer.wrap(bytes(n)))
                val b = ImageDecoder.decodeBitmap(src) { d, _, _ -> d.allocator = ImageDecoder.ALLOCATOR_SOFTWARE }
                drawBitmap(b, 5f, i * 70f + 3f, null)
            }
        }
    }

    @Test
    fun decodeOptions() = Out.scene("bitmap-decode-options", 400, 300) {
        val sampled = decode("photo-large.jpg", BitmapFactory.Options().apply { inSampleSize = 3 })
        drawBitmap(sampled, 0f, 0f, null)
        val rgb565 = decode("photo-rgba.png", BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.RGB_565 })
        drawBitmap(rgb565, 0f, 140f, null)
        val scaled = decode("photo-rgba.png", BitmapFactory.Options().apply { inDensity = 160; inTargetDensity = 240; inScaled = true })
        drawBitmap(scaled, 100f, 140f, null)
        val large = bytes("photo-large.jpg")
        val region = BitmapRegionDecoder.newInstance(large, 0, large.size)!!
        val part = region.decodeRegion(Rect(150, 60, 330, 200), BitmapFactory.Options().apply { inSampleSize = 1 })
        drawBitmap(part, 200f, 0f, null)
        val half = region.decodeRegion(Rect(0, 0, 384, 256), BitmapFactory.Options().apply { inSampleSize = 2 })
        drawBitmap(half, 250f, 150f, null)
    }

    @Test
    fun encodeRoundTrip() {
        val source = decode("photo-rgba.png")
        @Suppress("DEPRECATION")
        val formats = listOf(
            Bitmap.CompressFormat.PNG to 100,
            Bitmap.CompressFormat.JPEG to 80,
            Bitmap.CompressFormat.JPEG to 30,
            Bitmap.CompressFormat.WEBP_LOSSY to 80,
            Bitmap.CompressFormat.WEBP_LOSSLESS to 100,
        )
        val sizes = StringBuilder()
        Out.scene("bitmap-encode-roundtrip", 2 * 96 + 15, formats.size * 70) {
            for ((i, f) in formats.withIndex()) {
                val bos = ByteArrayOutputStream()
                check(source.compress(f.first, f.second, bos))
                val enc = bos.toByteArray()
                sizes.append("${f.first}@${f.second} bytes=${enc.size}\n")
                val back = BitmapFactory.decodeByteArray(enc, 0, enc.size)
                drawBitmap(back, 5f, i * 70f + 3f, null)
                // 4x crop of the striped corner, where codecs differ most.
                drawBitmap(back, Rect(0, 4, 24, 24), RectF(105f, i * 70f + 3f, 105f + 96f, i * 70f + 3f + 64f), null)
            }
        }
        Out.text("bitmap-encode-sizes", sizes.toString())
    }

    @Test
    fun configs() = Out.scene("bitmap-configs", 320, 200) {
        val src = decode("photo-rgba.png")
        val copies = listOf(
            src.copy(Bitmap.Config.ARGB_8888, false),
            src.copy(Bitmap.Config.RGB_565, false),
            src.copy(Bitmap.Config.RGBA_F16, false),
            src.copy(Bitmap.Config.ARGB_4444, false),
        )
        for ((i, b) in copies.withIndex()) drawBitmap(b, 5f + (i % 3) * 102f, 5f + (i / 3) * 70f, null)
        val alpha = src.extractAlpha()
        drawBitmap(alpha, 107f, 75f, Paint().apply { color = Color.rgb(160, 0, 200) })
        val a8 = Bitmap.createBitmap(96, 64, Bitmap.Config.ALPHA_8)
        Canvas(a8).drawCircle(48f, 32f, 28f, Paint().apply { isAntiAlias = true })
        drawBitmap(a8, 209f, 75f, Paint().apply { color = Color.rgb(0, 140, 140) })
        val pixels = IntArray(96 * 30)
        src.getPixels(pixels, 0, 96, 0, 20, 96, 30)
        val rebuilt = Bitmap.createBitmap(96, 30, Bitmap.Config.ARGB_8888)
        rebuilt.setPixels(pixels.map { it xor 0x00FFFFFF }.toIntArray(), 0, 96, 0, 0, 96, 30)
        drawBitmap(rebuilt, 5f, 150f, null)
        val erased = Bitmap.createBitmap(60, 30, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.argb(128, 255, 0, 0)) }
        drawBitmap(erased, 110f, 150f, null)
        drawBitmap(Bitmap.createBitmap(src, 30, 10, 50, 40, android.graphics.Matrix().apply { setRotate(90f) }, true), 180f, 145f, null)
    }
}
