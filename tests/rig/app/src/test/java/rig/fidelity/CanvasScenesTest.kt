package rig.fidelity

import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.BlendMode
import android.graphics.BlendModeColorFilter
import android.graphics.BlurMaskFilter
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.ColorSpace
import android.graphics.ComposePathEffect
import android.graphics.ComposeShader
import android.graphics.CornerPathEffect
import android.graphics.DashPathEffect
import android.graphics.DiscretePathEffect
import android.graphics.LightingColorFilter
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathDashPathEffect
import android.graphics.Picture
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Region
import android.graphics.Shader
import android.graphics.SumPathEffect
import android.graphics.SweepGradient
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Canvas primitives, paths, strokes, gradients, blend modes and shaders, one PNG each, on a
 * software canvas. (AGSL RuntimeShader is hardware-only; it is in ComposeScenesTest.graphics.)
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [Config.ALL_SDKS], qualifiers = SCREEN)
class CanvasScenesTest {
    private fun paint(color: Int, aa: Boolean = true, style: Paint.Style = Paint.Style.FILL) =
        Paint().apply {
            this.color = color
            isAntiAlias = aa
            this.style = style
        }

    @Test
    fun shapesAntiAlias() = Out.scene("canvas-shapes-aa", 320, 240) {
        for ((row, aa) in listOf(false, true).withIndex()) {
            save()
            translate(0f, row * 120f)
            rotate(7f, 160f, 60f)
            drawRect(10f, 10f, 60f, 60f, paint(Color.RED, aa))
            drawRoundRect(RectF(70f, 10f, 130f, 60f), 12f, 8f, paint(Color.BLUE, aa))
            drawCircle(165f, 35f, 25.5f, paint(Color.rgb(0, 140, 0), aa))
            drawOval(RectF(200f, 12f, 250f, 58f), paint(Color.MAGENTA, aa))
            drawArc(RectF(255f, 10f, 310f, 60f), 30f, 250f, true, paint(Color.rgb(255, 128, 0), aa))
            drawArc(RectF(10f, 65f, 60f, 115f), -45f, 200f, false, paint(Color.BLACK, aa, Paint.Style.STROKE).apply { strokeWidth = 3f })
            drawRect(70.3f, 70.3f, 130.7f, 110.7f, paint(Color.DKGRAY, aa, Paint.Style.STROKE).apply { strokeWidth = 1.5f })
            drawPoints(FloatArray(40) { i -> if (i % 2 == 0) 140f + i * 4f else 90f + (i % 7) }, paint(Color.BLACK, aa).apply { strokeWidth = 3f; strokeCap = Paint.Cap.ROUND })
            restore()
        }
    }

    @Test
    fun strokes() = Out.scene("canvas-strokes", 320, 260) {
        val caps = Paint.Cap.values()
        val widths = floatArrayOf(0f, 1f, 2.5f, 6f, 12f)
        for ((i, w) in widths.withIndex()) {
            for ((j, cap) in caps.withIndex()) {
                val p = paint(Color.BLACK, style = Paint.Style.STROKE).apply { strokeWidth = w; strokeCap = cap }
                val y = 15f + i * 22f
                drawLine(15f + j * 100f, y, 85f + j * 100f, y + 6f, p)
            }
        }
        for ((j, join) in Paint.Join.values().withIndex()) {
            val p = paint(Color.rgb(30, 60, 200), style = Paint.Style.STROKE).apply {
                strokeWidth = 10f
                strokeJoin = join
                strokeMiter = 3f
            }
            val path = Path().apply {
                moveTo(20f + j * 100f, 240f); lineTo(50f + j * 100f, 140f); lineTo(80f + j * 100f, 240f)
                moveTo(20f + j * 100f, 200f); lineTo(80f + j * 100f, 190f); lineTo(25f + j * 100f, 175f)
            }
            drawPath(path, p)
        }
    }

    @Test
    fun paths() = Out.scene("canvas-paths", 320, 320) {
        val curve = Path().apply {
            moveTo(10f, 80f)
            cubicTo(40f, 0f, 90f, 160f, 150f, 30f)
            quadTo(120f, 120f, 60f, 140f)
            arcTo(RectF(20f, 90f, 70f, 150f), 90f, 180f, false)
            close()
        }
        drawPath(curve, paint(Color.argb(160, 0, 120, 255)))
        drawPath(curve, paint(Color.BLACK, style = Paint.Style.STROKE).apply { strokeWidth = 2f })

        val star = Path().apply {
            for (k in 0 until 5) {
                val a = Math.toRadians((-90 + k * 144).toDouble())
                val x = 240f + 60f * Math.cos(a).toFloat()
                val y = 80f + 60f * Math.sin(a).toFloat()
                if (k == 0) moveTo(x, y) else lineTo(x, y)
            }
            close()
        }
        for ((i, ft) in listOf(Path.FillType.WINDING, Path.FillType.EVEN_ODD).withIndex()) {
            save(); translate(-60f + i * 80f, 80f); scale(0.6f, 0.6f, 240f, 80f)
            star.fillType = ft
            drawPath(star, paint(Color.rgb(200, 30, 30)))
            restore()
        }
        val a = Path().apply { addCircle(60f, 250f, 40f, Path.Direction.CW) }
        val b = Path().apply { addRoundRect(RectF(60f, 220f, 130f, 290f), floatArrayOf(4f, 4f, 20f, 20f, 0f, 0f, 30f, 10f), Path.Direction.CW) }
        for ((i, op) in Path.Op.values().withIndex()) {
            val r = Path()
            r.op(a, b, op)
            save(); translate(i * 52f - 40f, 0f); scale(0.5f, 0.5f, 95f, 255f)
            drawPath(r, paint(Color.rgb(20, 150, 90)))
            restore()
        }
    }

    @Test
    fun pathEffects() = Out.scene("canvas-path-effects", 320, 260) {
        val wave = Path().apply {
            moveTo(10f, 20f)
            for (k in 0 until 6) rQuadTo(25f, if (k % 2 == 0) -15f else 15f, 50f, 0f)
        }
        val stamp = Path().apply { addCircle(0f, 0f, 3f, Path.Direction.CW) }
        val effects = listOf(
            DashPathEffect(floatArrayOf(12f, 6f, 2f, 6f), 3f),
            CornerPathEffect(20f),
            DiscretePathEffect(6f, 3f),
            PathDashPathEffect(stamp, 10f, 0f, PathDashPathEffect.Style.ROTATE),
            ComposePathEffect(DashPathEffect(floatArrayOf(20f, 8f), 0f), CornerPathEffect(10f)),
            SumPathEffect(DashPathEffect(floatArrayOf(5f, 5f), 0f), DiscretePathEffect(4f, 2f)),
        )
        for ((i, e) in effects.withIndex()) {
            save(); translate(0f, 15f + i * 40f)
            drawPath(wave, paint(Color.BLACK, style = Paint.Style.STROKE).apply { strokeWidth = 3f; pathEffect = e })
            restore()
        }
    }

    @Test
    fun gradients() = Out.scene("canvas-gradients", 320, 320) {
        val colors = intArrayOf(Color.RED, Color.YELLOW, Color.GREEN, Color.CYAN, Color.BLUE, Color.MAGENTA)
        val p = Paint()
        p.shader = LinearGradient(10f, 0f, 150f, 0f, Color.BLACK, Color.WHITE, Shader.TileMode.CLAMP)
        drawRect(10f, 10f, 150f, 50f, p)
        p.shader = LinearGradient(170f, 10f, 310f, 50f, colors, floatArrayOf(0f, .1f, .3f, .6f, .9f, 1f), Shader.TileMode.CLAMP)
        drawRect(170f, 10f, 310f, 50f, p)
        for ((i, mode) in Shader.TileMode.values().withIndex()) {
            p.shader = LinearGradient(0f, 0f, 25f, 0f, Color.rgb(255, 80, 0), Color.rgb(0, 40, 160), mode).also {
                it.setLocalMatrix(Matrix().apply { setRotate(30f); postTranslate(10f + i * 76f, 0f) })
            }
            drawRect(10f + i * 76f, 60f, 80f + i * 76f, 130f, p)
        }
        for ((i, mode) in Shader.TileMode.values().withIndex()) {
            p.shader = RadialGradient(45f + i * 76f, 175f, 20f, intArrayOf(Color.WHITE, Color.rgb(0, 128, 255), Color.BLACK), null, mode)
            drawRect(10f + i * 76f, 140f, 80f + i * 76f, 210f, p)
        }
        p.shader = SweepGradient(80f, 265f, colors + colors[0], null)
        drawCircle(80f, 265f, 45f, p.apply { isAntiAlias = true })
        p.shader = RadialGradient(230f, 265f, 50f, intArrayOf(Color.argb(255, 255, 0, 0), Color.argb(0, 255, 0, 0)), null, Shader.TileMode.CLAMP)
        drawCircle(230f, 265f, 50f, p)
        // Long gradients show banding and dithering differences.
        p.shader = LinearGradient(0f, 0f, 320f, 0f, Color.rgb(40, 40, 40), Color.rgb(60, 60, 60), Shader.TileMode.CLAMP)
        p.isDither = true
        drawRect(0f, 312f, 320f, 320f, p)
    }

    @Test
    fun blendModes() = Out.scene("canvas-blend-modes", 312, 312) {
        val modes = BlendMode.values()
        val cell = 52f
        for ((i, mode) in modes.withIndex()) {
            val x = (i % 6) * cell
            val y = (i / 6) * cell
            val layer = saveLayer(x, y, x + cell, y + cell, null)
            drawCircle(x + 20f, y + 20f, 16f, paint(Color.rgb(30, 90, 230)))
            val src = paint(Color.argb(200, 240, 40, 30)).apply { blendMode = mode }
            drawRect(x + 18f, y + 18f, x + 46f, y + 46f, src)
            restoreToCount(layer)
        }
    }

    @Test
    fun colorFilters() = Out.scene("canvas-color-filters", 320, 200) {
        val base = Paint().apply {
            shader = LinearGradient(0f, 0f, 60f, 60f, intArrayOf(Color.RED, Color.GREEN, Color.BLUE), null, Shader.TileMode.MIRROR)
        }
        val sepia = ColorMatrix().apply { setSaturation(0f); postConcat(ColorMatrix(floatArrayOf(1f, 0f, 0f, 0f, 40f, 0f, 1f, 0f, 0f, 20f, 0f, 0f, 1f, 0f, -20f, 0f, 0f, 0f, 1f, 0f))) }
        val filters = listOf(
            null,
            ColorMatrixColorFilter(sepia),
            ColorMatrixColorFilter(ColorMatrix().apply { setSaturation(0f) }),
            LightingColorFilter(Color.rgb(200, 255, 120), Color.rgb(0, 0, 60)),
            PorterDuffColorFilter(Color.argb(128, 255, 200, 0), PorterDuff.Mode.SRC_ATOP),
            BlendModeColorFilter(Color.rgb(0, 160, 160), BlendMode.MULTIPLY),
            BlendModeColorFilter(Color.rgb(255, 0, 200), BlendMode.HUE),
            BlendModeColorFilter(Color.rgb(90, 90, 90), BlendMode.DIFFERENCE),
        )
        for ((i, f) in filters.withIndex()) {
            base.colorFilter = f
            drawRect(10f + (i % 4) * 78f, 10f + (i / 4) * 95f, 80f + (i % 4) * 78f, 95f + (i / 4) * 95f, base)
        }
    }

    @Test
    fun shaders() = Out.scene("canvas-shaders", 320, 210) {
        val tile = Bitmap.createBitmap(12, 12, Bitmap.Config.ARGB_8888).apply {
            for (y in 0 until 12) for (x in 0 until 12) {
                setPixel(x, y, if ((x / 6 + y / 6) % 2 == 0) Color.rgb(250, 120, 0) else Color.argb(120, 0, 90, 200))
            }
        }
        val p = Paint().apply { isAntiAlias = true }
        val modes = Shader.TileMode.values()
        for ((i, m) in modes.withIndex()) {
            p.shader = BitmapShader(tile, m, modes[(i + 1) % modes.size]).also {
                it.setLocalMatrix(Matrix().apply { setScale(2.5f, 2.5f); postRotate(15f); postTranslate(20f + i * 76f, 20f) })
            }
            drawRoundRect(RectF(10f + i * 76f, 10f, 80f + i * 76f, 100f), 10f, 10f, p)
        }
        p.shader = ComposeShader(
            LinearGradient(0f, 110f, 0f, 200f, Color.WHITE, Color.BLUE, Shader.TileMode.CLAMP),
            RadialGradient(160f, 155f, 80f, Color.YELLOW, Color.RED, Shader.TileMode.CLAMP),
            BlendMode.MULTIPLY,
        )
        drawRect(10f, 110f, 310f, 200f, p)
    }

    @Test
    fun maskFiltersAndShadows() = Out.scene("canvas-blur-shadow", 320, 240) {
        for ((i, s) in BlurMaskFilter.Blur.values().withIndex()) {
            drawCircle(40f + i * 78f, 50f, 28f, paint(Color.rgb(200, 0, 120)).apply { maskFilter = BlurMaskFilter(8f, s) })
        }
        drawRoundRect(RectF(20f, 110f, 150f, 200f), 14f, 14f, paint(Color.rgb(250, 250, 250)).apply { setShadowLayer(10f, 4f, 6f, Color.argb(140, 0, 0, 0)) })
        drawText("Shadow", 175f, 170f, paint(Color.rgb(0, 100, 200)).apply { textSize = 36f; setShadowLayer(3f, 2f, 2f, Color.GRAY) })
    }

    @Test
    fun transformsAndClips() = Out.scene("canvas-transforms-clips", 320, 320) {
        val checker = Paint().apply {
            shader = BitmapShader(
                Bitmap.createBitmap(intArrayOf(Color.BLACK, Color.WHITE, Color.WHITE, Color.BLACK), 2, 2, Bitmap.Config.ARGB_8888),
                Shader.TileMode.REPEAT, Shader.TileMode.REPEAT,
            ).also { it.setLocalMatrix(Matrix().apply { setScale(10f, 10f) }) }
        }
        save()
        val m = Matrix()
        m.setPolyToPoly(floatArrayOf(0f, 0f, 140f, 0f, 140f, 140f, 0f, 140f), 0, floatArrayOf(30f, 10f, 130f, 10f, 150f, 140f, 10f, 140f), 0, 4)
        concat(m)
        drawRect(0f, 0f, 140f, 140f, checker)
        restore()
        save(); translate(230f, 75f); rotate(33f); skew(0.3f, 0f); scale(1.2f, 0.8f)
        drawRect(-40f, -40f, 40f, 40f, paint(Color.rgb(0, 160, 80)))
        restore()
        save()
        clipPath(Path().apply { addCircle(80f, 230f, 70f, Path.Direction.CW) })
        drawRect(0f, 150f, 160f, 320f, checker)
        restore()
        save()
        clipRect(180f, 160f, 310f, 310f)
        clipOutRect(210f, 190f, 280f, 280f)
        drawColor(Color.rgb(250, 160, 0))
        restore()
        val region = Region(185, 290, 250, 318)
        region.op(220, 280, 300, 310, Region.Op.XOR)
        val iter = android.graphics.RegionIterator(region)
        val r = android.graphics.Rect()
        while (iter.next(r)) drawRect(r, paint(Color.BLUE, aa = false))
    }

    @Test
    fun layersPictureColorSpace() = Out.scene("canvas-layers-picture", 320, 240) {
        val l1 = saveLayerAlpha(0f, 0f, 160f, 120f, 160)
        drawCircle(60f, 60f, 45f, paint(Color.RED))
        drawCircle(100f, 60f, 45f, paint(Color.BLUE))
        val l2 = saveLayerAlpha(30f, 30f, 150f, 110f, 128)
        drawRect(40f, 40f, 140f, 100f, paint(Color.GREEN))
        restoreToCount(l2)
        restoreToCount(l1)
        drawCircle(220f, 60f, 45f, paint(Color.argb(120, 255, 0, 0)))
        drawCircle(260f, 60f, 45f, paint(Color.argb(120, 0, 0, 255)))

        val picture = Picture()
        picture.beginRecording(100, 100).apply {
            drawRect(5f, 5f, 95f, 95f, paint(Color.rgb(255, 220, 0)))
            drawLine(5f, 5f, 95f, 95f, paint(Color.BLACK).apply { strokeWidth = 4f })
        }
        picture.endRecording()
        save(); translate(10f, 130f); drawPicture(picture); restore()
        save(); translate(120f, 130f); scale(0.5f, 1f); drawPicture(picture); restore()

        // A Display P3 bitmap drawn into sRGB: the colour conversion runs in skia.
        val p3 = Bitmap.createBitmap(80, 80, Bitmap.Config.ARGB_8888, true, ColorSpace.get(ColorSpace.Named.DISPLAY_P3))
        Canvas(p3).drawColor(Color.pack(0f, 1f, 0f, 1f, ColorSpace.get(ColorSpace.Named.DISPLAY_P3)))
        drawBitmap(p3, 220f, 140f, null)
    }

    @Test
    fun verticesAndMesh() = Out.scene("canvas-vertices-mesh", 320, 200) {
        val verts = floatArrayOf(20f, 180f, 80f, 20f, 140f, 180f)
        val colors = intArrayOf(Color.RED, Color.GREEN, Color.BLUE, 0, 0, 0)
        drawVertices(Canvas.VertexMode.TRIANGLES, 6, verts, 0, null, 0, colors, 0, null, 0, 0, Paint())
        val src = Bitmap.createBitmap(40, 40, Bitmap.Config.ARGB_8888)
        Canvas(src).apply {
            drawColor(Color.rgb(0, 120, 200))
            drawCircle(20f, 20f, 12f, paint(Color.YELLOW))
        }
        val mesh = FloatArray(4 * 4 * 2)
        var k = 0
        for (y in 0..3) for (x in 0..3) {
            mesh[k++] = 170f + x * 45f + (y * 7f)
            mesh[k++] = 20f + y * 50f + (if (x % 2 == 0) 10f else -5f)
        }
        drawBitmapMesh(src, 3, 3, mesh, 0, null, 0, Paint().apply { isFilterBitmap = true })
    }
}
