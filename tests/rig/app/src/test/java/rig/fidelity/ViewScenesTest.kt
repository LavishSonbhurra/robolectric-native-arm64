package rig.fidelity

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Outline
import android.graphics.drawable.GradientDrawable
import android.os.Looper
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.ViewOutlineProvider
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RatingBar
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import androidx.activity.ComponentActivity
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * A framework-widget View hierarchy, light and dark, rendered two ways: View.draw into a
 * software Canvas, and PixelCopy of the window (Robolectric's hardware renderer path, with
 * elevation shadows).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [Config.ALL_SDKS], qualifiers = SCREEN)
class ViewScenesTest {
    private fun Activity.dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics)

    private fun build(theme: Int): Activity {
        val controller = Robolectric.buildActivity(ComponentActivity::class.java)
        val a = controller.get()
        a.setTheme(theme)
        controller.setup()
        val pad = a.dp(16f).toInt()
        val root = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        fun add(v: View, h: Int = WRAP_CONTENT) = root.addView(v, LinearLayout.LayoutParams(MATCH_PARENT, h).apply { topMargin = pad / 2 })
        add(TextView(a).apply { text = "Fidelity rig"; setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f); setTypeface(typeface, android.graphics.Typeface.BOLD) })
        add(TextView(a).apply {
            text = "A long body line that is going to be ellipsized because it does not fit on a single line at all."
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        })
        add(Button(a).apply { text = "Button" }, WRAP_CONTENT)
        add(CheckBox(a).apply { text = "CheckBox"; isChecked = true })
        add(RadioButton(a).apply { text = "RadioButton"; isChecked = true })
        add(Switch(a).apply { text = "Switch"; isChecked = true })
        add(SeekBar(a).apply { max = 100; progress = 40 })
        add(ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; progress = 60; secondaryProgress = 80 })
        add(EditText(a).apply { hint = "EditText hint"; isFocusable = false })
        root.addView(RatingBar(a).apply { numStars = 5; rating = 3.5f }, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
        val row = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        row.addView(ImageView(a).apply {
            setImageDrawable(GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(Color.rgb(255, 87, 34), Color.rgb(63, 81, 181))).apply {
                cornerRadius = a.dp(12f)
                setStroke(a.dp(2f).toInt(), Color.BLACK)
            })
        }, LinearLayout.LayoutParams(a.dp(72f).toInt(), a.dp(72f).toInt()))
        row.addView(FrameLayout(a).apply {
            background = GradientDrawable().apply { setColor(Color.WHITE); cornerRadius = a.dp(16f) }
            elevation = a.dp(8f)
            outlineProvider = ViewOutlineProvider.BACKGROUND
            clipToOutline = true
            addView(TextView(a).apply { text = "Elevated card"; setTextColor(Color.BLACK); setPadding(pad, pad, pad, pad) })
        }, LinearLayout.LayoutParams(0, a.dp(72f).toInt(), 1f).apply { marginStart = pad })
        row.addView(View(a).apply {
            setBackgroundColor(Color.rgb(0, 150, 136))
            elevation = a.dp(4f)
            outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(view: View, outline: Outline) = outline.setOval(0, 0, view.width, view.height)
            }
            clipToOutline = true
        }, LinearLayout.LayoutParams(a.dp(56f).toInt(), a.dp(56f).toInt()).apply { marginStart = pad })
        add(row)
        a.setContentView(root)
        shadowOf(Looper.getMainLooper()).idle()
        return a
    }

    private fun software(a: Activity): Bitmap {
        val decor = a.window.decorView
        val b = Bitmap.createBitmap(decor.width, decor.height, Bitmap.Config.ARGB_8888)
        decor.draw(Canvas(b))
        return b
    }

    @Test
    fun viewsLight() {
        val a = build(android.R.style.Theme_Material_Light_NoActionBar)
        Out.save("view-light-software", software(a))
        Out.save("view-light-pixelcopy", pixelCopy(a))
    }

    @Test
    fun viewsDark() {
        val a = build(android.R.style.Theme_Material_NoActionBar)
        Out.save("view-dark-software", software(a))
        Out.save("view-dark-pixelcopy", pixelCopy(a))
    }
}
