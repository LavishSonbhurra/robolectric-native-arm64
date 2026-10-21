package rig.fidelity

import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.text.LineBreaker
import android.os.LocaleList
import android.text.Layout
import android.text.SpannableString
import android.text.Spanned
import android.text.StaticLayout
import android.text.TextDirectionHeuristics
import android.text.TextPaint
import android.text.style.BackgroundColorSpan
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.text.style.UnderlineSpan
import java.util.Locale
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Fonts, sizes, scripts, RTL, emoji, hyphenation and line breaking, text effects. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [Config.ALL_SDKS], qualifiers = SCREEN)
class TextScenesTest {
    private fun tp(size: Float, tf: Typeface? = null, color: Int = Color.BLACK) = TextPaint().apply {
        isAntiAlias = true
        textSize = size
        typeface = tf
        this.color = color
    }

    private fun layout(text: CharSequence, paint: TextPaint, width: Int, block: StaticLayout.Builder.() -> Unit = {}) =
        StaticLayout.Builder.obtain(text, 0, text.length, paint, width).apply(block).build()

    @Test
    fun fontFamilies() = Out.scene("text-font-families", 360, 560) {
        val families = listOf(
            "sans-serif", "sans-serif-thin", "sans-serif-light", "sans-serif-medium", "sans-serif-black",
            "sans-serif-condensed", "sans-serif-condensed-light", "serif", "monospace", "serif-monospace",
            "casual", "cursive", "sans-serif-smallcaps",
        )
        var y = 24f
        for (f in families) {
            drawText("$f: The quick brown fox", 6f, y, tp(17f, Typeface.create(f, Typeface.NORMAL)))
            y += 25f
        }
        for (style in listOf(Typeface.BOLD, Typeface.ITALIC, Typeface.BOLD_ITALIC)) {
            drawText("style $style: Sphinx of black quartz", 6f, y, tp(17f, Typeface.create(Typeface.SERIF, style)))
            y += 25f
        }
        for (w in listOf(100, 300, 500, 700, 900)) {
            drawText("weight $w Roboto", 6f, y, tp(17f, Typeface.create(Typeface.DEFAULT, w, w >= 700)))
            y += 25f
        }
    }

    @Test
    fun sizesAndPaintFlags() = Out.scene("text-sizes", 400, 520) {
        var y = 4f
        for (s in listOf(6f, 8f, 9.5f, 11f, 12f, 14f, 18f, 24f, 32f, 48f, 64f)) {
            y += s * 1.2f
            drawText("Hamburgefonstiv 0123 ${s}px", 4f, y, tp(s))
        }
        y += 28f
        val variants = listOf<Pair<String, TextPaint.() -> Unit>>(
            "subpixel" to { isSubpixelText = true },
            "linear" to { isLinearText = true },
            "no AA" to { isAntiAlias = false },
            "fake bold" to { isFakeBoldText = true },
            "skewX -0.25" to { textSkewX = -0.25f },
            "scaleX 1.4" to { textScaleX = 1.4f },
            "spacing 0.2" to { letterSpacing = 0.2f },
            "smcp onum 1234" to { fontFeatureSettings = "'smcp', 'onum'" },
            "wght 800 wdth 75" to { fontVariationSettings = "'wght' 800, 'wdth' 75" },
        )
        for ((label, setup) in variants) {
            drawText("Typeface $label", 4f + 0.33f, y, tp(15f).apply(setup))
            y += 19f
        }
    }

    @Test
    fun rtlAndBidi() = Out.scene("text-rtl-bidi", 360, 300) {
        val p = tp(20f)
        val samples = listOf(
            "مرحبا بالعالم، هذا اختبار.",
            "שלום עולם, זו בדיקה.",
            "abc مرحبا 123 def שלום 4.5%",
            "(١٢٣) فارسی: سلام دنیا",
        )
        var y = 8f
        for (s in samples) {
            val l = layout(s, p, 340) {
                setTextDirection(TextDirectionHeuristics.FIRSTSTRONG_LTR)
                setAlignment(Layout.Alignment.ALIGN_NORMAL)
            }
            save(); translate(10f, y); l.draw(this); restore()
            y += l.height + 14f
        }
        val forced = layout("Forced RTL: abc 123 مرحبا", p, 340) { setTextDirection(TextDirectionHeuristics.RTL) }
        save(); translate(10f, y); forced.draw(this); restore()
        y += forced.height + 10f
        val adv = p.getRunAdvance("عربي abc", 0, 8, 0, 8, true, 8)
        drawText("run advance %.3f".format(Locale.US, adv), 10f, y + 20f, tp(14f))
    }

    @Test
    fun scripts() = Out.scene("text-scripts", 360, 380) {
        val samples = listOf(
            "Ελληνικά: Γειά σου κόσμε",
            "Кириллица: Привет, мир",
            "देवनागरी: नमस्ते दुनिया",
            "বাংলা: হ্যালো বিশ্ব",
            "தமிழ்: வணக்கம் உலகம்",
            "ไทย: สวัสดีชาวโลก",
            "中文: 你好，世界",
            "日本語: こんにちは世界",
            "한국어: 안녕하세요 세계",
            "Tiếng Việt: Xin chào thế giới",
            "ქართული: გამარჯობა",
            "Combining: é ä ñ Z̵̶",
        )
        var y = 26f
        for (s in samples) {
            drawText(s, 8f, y, tp(19f))
            y += 29f
        }
    }

    @Test
    fun emoji() = Out.scene("text-emoji", 380, 260) {
        val line = "😀😂🥲👍🏽🇯🇵👨‍👩‍👧‍👦❤️‍🔥🧑🏿‍🚀🏳️‍🌈"
        var y = 10f
        for (s in listOf(12f, 20f, 32f, 56f)) {
            y += s * 1.3f
            drawText(line, 6f, y, tp(s))
        }
        drawText("Text with emoji 🎉 inline ✔︎ ✔️", 6f, y + 30f, tp(18f))
    }

    @Test
    fun hyphenationAndLineBreaking() = Out.scene("text-hyphenation", 520, 620) {
        val en = "Internationalization and pneumonoultramicroscopicsilicovolcanoconiosis are unquestionably extraordinary words for narrow columns of typographically demanding text."
        val de = "Die Donaudampfschifffahrtsgesellschaftskapitänsmütze liegt neben der Rindfleischetikettierungsüberwachungsaufgabe."
        val p = tp(15f)
        val configs = listOf(
            Triple("simple none", LineBreaker.BREAK_STRATEGY_SIMPLE, Layout.HYPHENATION_FREQUENCY_NONE),
            Triple("high full", LineBreaker.BREAK_STRATEGY_HIGH_QUALITY, Layout.HYPHENATION_FREQUENCY_FULL),
            Triple("balanced normal", LineBreaker.BREAK_STRATEGY_BALANCED, Layout.HYPHENATION_FREQUENCY_NORMAL),
        )
        val lines = StringBuilder()
        for ((col, cfg) in configs.withIndex()) {
            var y = 4f
            for ((text, locale) in listOf(en to "en-US", de to "de-DE")) {
                val tpLocale = TextPaint(p).apply { textLocales = LocaleList.forLanguageTags(locale) }
                val l = layout(text, tpLocale, 160) {
                    setBreakStrategy(cfg.second)
                    setHyphenationFrequency(cfg.third)
                    if (col == 1) setJustificationMode(LineBreaker.JUSTIFICATION_MODE_INTER_WORD)
                }
                save(); translate(8f + col * 172f, y); l.draw(this); restore()
                lines.append("${cfg.first} $locale lines=${l.lineCount} ends=${(0 until l.lineCount).joinToString(",") { l.getLineEnd(it).toString() }}\n")
                y += l.height + 20f
            }
        }
        Out.text("text-hyphenation-breaks", lines.toString())
    }

    @Test
    fun effectsAndSpans() = Out.scene("text-effects", 380, 360) {
        drawText("Underline", 8f, 30f, tp(24f).apply { isUnderlineText = true })
        drawText("Strike", 160f, 30f, tp(24f).apply { isStrikeThruText = true })
        drawText("Outline", 8f, 70f, tp(30f, Typeface.DEFAULT_BOLD).apply { style = Paint.Style.STROKE; strokeWidth = 1.5f })
        drawText("Gradient", 160f, 70f, tp(30f, Typeface.DEFAULT_BOLD).apply {
            shader = LinearGradient(160f, 40f, 320f, 70f, Color.RED, Color.BLUE, Shader.TileMode.CLAMP)
        })
        val arc = Path().apply { addArc(30f, 90f, 350f, 300f, 200f, 140f) }
        drawTextOnPath("Text on a path, curving along an arc", arc, 0f, 0f, tp(18f))
        val outline = Path()
        tp(40f, Typeface.SERIF).getTextPath("Path", 0, 4, 8f, 200f, outline)
        drawPath(outline, Paint().apply { isAntiAlias = true; color = Color.rgb(0, 120, 60) })
        val span = SpannableString("Spans: bold, red, big, underlined, highlighted.").apply {
            setSpan(StyleSpan(Typeface.BOLD), 7, 11, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            setSpan(ForegroundColorSpan(Color.RED), 13, 16, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            setSpan(RelativeSizeSpan(1.6f), 18, 21, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            setSpan(UnderlineSpan(), 23, 33, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            setSpan(BackgroundColorSpan(Color.YELLOW), 35, 46, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        val l = layout(span, tp(17f), 360)
        save(); translate(8f, 230f); l.draw(this); restore()
        drawTextRun("ab שלום cd", 0, 10, 0, 10, 8f, 340f, false, tp(18f))
    }

    @Test
    fun metrics() {
        val out = StringBuilder()
        val text = "Hamburgefonstiv"
        Out.scene("text-metrics", 360, 300) {
            var y = 40f
            for ((name, f) in listOf("default" to Typeface.DEFAULT, "serif" to Typeface.SERIF, "monospace" to Typeface.MONOSPACE, "cursive" to Typeface.create("cursive", Typeface.NORMAL))) {
                val p = tp(30f, f)
                val fm = p.fontMetrics
                val w = p.measureText(text)
                val b = Rect().also { p.getTextBounds(text, 0, text.length, it) }
                val guide = Paint().apply { strokeWidth = 1f }
                guide.color = Color.rgb(255, 160, 160); drawLine(0f, y + fm.top, 360f, y + fm.top, guide)
                guide.color = Color.rgb(160, 160, 255); drawLine(0f, y + fm.ascent, 360f, y + fm.ascent, guide)
                guide.color = Color.rgb(0, 180, 0); drawLine(0f, y, 360f, y, guide)
                guide.color = Color.rgb(160, 160, 255); drawLine(0f, y + fm.descent, 360f, y + fm.descent, guide)
                drawRect(Rect(b).apply { offset(8, y.toInt()) }, Paint().apply { style = Paint.Style.STROKE; color = Color.MAGENTA })
                drawText(text, 8f, y, p)
                val widths = FloatArray(text.length).also { p.getTextWidths(text, it) }
                out.append("$name measure=%.4f bounds=%s top=%.4f ascent=%.4f descent=%.4f bottom=%.4f widths=%s\n".format(
                    Locale.US, w, b.toShortString(), fm.top, fm.ascent, fm.descent, fm.bottom,
                    widths.joinToString(",") { "%.3f".format(Locale.US, it) },
                ))
                y += 70f
            }
        }
        Out.text("text-metrics", out.toString())
    }
}
