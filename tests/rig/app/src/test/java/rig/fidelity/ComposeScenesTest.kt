package rig.fidelity

import androidx.activity.ComponentActivity
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.CutCornerShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import android.graphics.RuntimeShader
import android.os.Build
import androidx.compose.runtime.remember
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.Hyphens
import androidx.compose.ui.text.style.LineBreak
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.github.takahirom.roborazzi.captureRoboImage
import com.github.takahirom.roborazzi.captureScreenRoboImage
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Jetpack Compose screens (Material 3, static colour schemes), captured with a window
 * PixelCopy (hardware renderer) and saved through the native PNG encoder. captureToImage is
 * not used: its forceRedraw waits at most 2 s of wall time, too short under qemu. The lazy
 * list also goes through Roborazzi (node and screen capture), the usual screenshot-test flow.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [Config.ALL_SDKS], qualifiers = SCREEN)
class ComposeScenesTest {
    @Suppress("DEPRECATION")
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun shoot(name: String, content: @Composable () -> Unit) {
        compose.setContent(content)
        compose.waitForIdle()
        Out.save(name, pixelCopy(compose.activity))
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun MaterialScreen() {
        Scaffold(
            topBar = { TopAppBar(title = { Text("Fidelity rig") }) },
            bottomBar = {
                NavigationBar {
                    NavigationBarItem(selected = true, onClick = {}, icon = { Icon(Icons.Filled.Home, null) }, label = { Text("Home") })
                    NavigationBarItem(selected = false, onClick = {}, icon = { Icon(Icons.Filled.Star, null) }, label = { Text("Starred") })
                    NavigationBarItem(selected = false, onClick = {}, icon = { Icon(Icons.Filled.Settings, null) }, label = { Text("Settings") })
                }
            },
            floatingActionButton = { FloatingActionButton(onClick = {}) { Icon(Icons.Filled.Add, null) } },
        ) { inner ->
            Column(Modifier.padding(inner).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Headline", style = MaterialTheme.typography.headlineSmall)
                Text("Body text in the default Material 3 typography, long enough to wrap onto a second line.", style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {}) { Text("Button") }
                    OutlinedButton(onClick = {}) { Text("Outlined") }
                    FilledTonalButton(onClick = {}) { Text("Tonal") }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Switch(checked = true, onCheckedChange = {})
                    Switch(checked = false, onCheckedChange = {})
                    Checkbox(checked = true, onCheckedChange = {})
                    Checkbox(checked = false, onCheckedChange = {})
                }
                Slider(value = 0.35f, onValueChange = {})
                LinearProgressIndicator(progress = { 0.6f }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = "Typed value", onValueChange = {}, label = { Text("Label") }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AssistChip(onClick = {}, label = { Text("Assist") }, leadingIcon = { Icon(Icons.Filled.Favorite, null) })
                    FilterChip(selected = true, onClick = {}, label = { Text("Filter") })
                }
                Card(Modifier.fillMaxWidth()) {
                    ListItem(headlineContent = { Text("Card list item") }, supportingContent = { Text("Supporting text") }, leadingContent = { Icon(Icons.Filled.Star, null) })
                }
            }
        }
    }

    @Test
    fun materialLight() = shoot("compose-material-light") {
        MaterialTheme(colorScheme = lightColorScheme()) { MaterialScreen() }
    }

    @Test
    fun materialDark() = shoot("compose-material-dark") {
        MaterialTheme(colorScheme = darkColorScheme()) { MaterialScreen() }
    }

    @Test
    fun graphics() = shoot("compose-graphics") {
        Column(Modifier.fillMaxSize().background(Color.White).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Canvas(Modifier.fillMaxWidth().height(160.dp)) {
                drawRect(Brush.linearGradient(listOf(Color(0xFF6200EE), Color(0xFF03DAC5), Color(0xFFFFC107))), size = Size(size.width / 2, size.height))
                drawCircle(Brush.radialGradient(listOf(Color.White, Color(0xFFE91E63)), center = Offset(size.width * 0.75f, size.height / 2), radius = 70f * density / 2), radius = 70f * density / 2, center = Offset(size.width * 0.75f, size.height / 2))
                val p = Path().apply {
                    moveTo(10f, size.height - 10f)
                    cubicTo(size.width * 0.3f, -40f, size.width * 0.6f, size.height + 40f, size.width - 10f, 20f)
                }
                drawPath(p, Color.Black, style = Stroke(width = 4.dp.toPx(), cap = StrokeCap.Round))
                drawArc(Color(0xFF4CAF50), 20f, 250f, useCenter = false, topLeft = Offset(20f, 20f), size = Size(120f, 120f), style = Stroke(8f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(72.dp).shadow(10.dp, RoundedCornerShape(16.dp)).background(Color.White))
                Box(Modifier.size(72.dp).shadow(6.dp, CircleShape).background(Color(0xFF2196F3)))
                Box(Modifier.size(72.dp).clip(CutCornerShape(18.dp)).background(Color(0xFFFF5722)))
                Box(Modifier.size(72.dp).rotate(20f).border(3.dp, Color.Black, RoundedCornerShape(8.dp)))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                Box(Modifier.size(90.dp).graphicsLayer { alpha = 0.5f; rotationZ = -12f; scaleX = 0.9f }.background(Brush.sweepGradient(listOf(Color.Red, Color.Yellow, Color.Green, Color.Blue, Color.Red))))
                Box(Modifier.size(90.dp).blur(6.dp).background(Brush.verticalGradient(listOf(Color.Black, Color(0xFF00BCD4)))))
                Box(Modifier.size(90.dp).graphicsLayer { rotationX = 30f; cameraDistance = 8f * density }.background(Color(0xFF9C27B0)))
            }
            // AGSL needs the hardware renderer; the window PixelCopy goes through it. RuntimeShader
            // is API 33 (there is no AGSL before Android 13); below it the box keeps its place
            // in the layout with a plain gradient, so the rest of the scene is the same.
            if (Build.VERSION.SDK_INT >= 33) {
                val agsl = remember { RuntimeShader(AGSL) }
                Box(Modifier.fillMaxWidth().height(90.dp).drawBehind {
                    // The array setter: at SDK 33 and 34 Robolectric 4.17 drops the scalar ones
                    // (ShadowNativeRuntimeShader no-ops them) and the uniform stays uninitialised.
                    agsl.setFloatUniform("size", floatArrayOf(size.width, size.height))
                    drawRect(ShaderBrush(agsl))
                })
            } else {
                Box(Modifier.fillMaxWidth().height(90.dp).background(
                    Brush.horizontalGradient(listOf(Color(0xFF3F51B5), Color(0xFFE91E63)))))
            }
            Surface(tonalElevation = 6.dp, shadowElevation = 6.dp, shape = RoundedCornerShape(24.dp)) {
                Text("Surface with tonal and shadow elevation", Modifier.padding(16.dp))
            }
        }
    }

    @Test
    fun text() = shoot("compose-text") {
        Column(Modifier.fillMaxSize().background(Color.White).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Default 16sp, the quick brown fox", fontSize = 16.sp)
            Text("Serif bold italic", fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold, fontStyle = FontStyle.Italic, fontSize = 18.sp)
            Text("Monospace 0O1lI {}[]", fontFamily = FontFamily.Monospace, fontSize = 15.sp)
            Text("Cursive handwriting", fontFamily = FontFamily.Cursive, fontSize = 22.sp)
            Row { for (w in listOf(100, 300, 400, 500, 700, 900)) Text("Aa ", fontWeight = FontWeight(w), fontSize = 20.sp) }
            Text("Letter spacing", letterSpacing = 4.sp, textDecoration = TextDecoration.combine(listOf(TextDecoration.Underline, TextDecoration.LineThrough)))
            Text(buildAnnotatedString {
                append("Annotated: ")
                withStyle(SpanStyle(color = Color.Red, fontWeight = FontWeight.Bold)) { append("red bold ") }
                withStyle(SpanStyle(background = Color.Yellow, fontSize = 20.sp)) { append("highlight ") }
                withStyle(SpanStyle(fontFamily = FontFamily.Serif, fontStyle = FontStyle.Italic)) { append("serif italic") }
            })
            Text("Emoji 😀👍🏽🇯🇵👨‍👩‍👧 in Compose", fontSize = 18.sp)
            Text("Ellipsized: a very long line of text that will certainly not fit on one line of this screen", maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                "Hyphenation: internationalization characteristically unquestionably extraordinarily",
                style = TextStyle(hyphens = Hyphens.Auto, lineBreak = LineBreak.Paragraph, fontSize = 17.sp),
                modifier = Modifier.padding(end = 140.dp),
            )
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                Column(Modifier.fillMaxWidth()) {
                    Text("مرحبا بالعالم - نص من اليمين إلى اليسار", fontSize = 18.sp)
                    Text("שלום עולם עם 123 ו-abc", fontSize = 18.sp)
                }
            }
            Text("中文 日本語 한국어 हिन्दी ไทย", fontSize = 18.sp)
        }
    }

    @Test
    fun lazyListAndRoborazzi() {
        compose.setContent {
            MaterialTheme(colorScheme = lightColorScheme()) {
                Surface(Modifier.fillMaxSize()) {
                    LazyColumn {
                        items(30) { i ->
                            ListItem(
                                headlineContent = { Text("Row $i") },
                                supportingContent = { Text("Item number $i in a lazy list") },
                                leadingContent = { Box(Modifier.size(40.dp).clip(CircleShape).background(Color.hsv(i * 12f, 0.6f, 0.8f))) },
                            )
                            HorizontalDivider()
                        }
                    }
                }
            }
        }
        compose.waitForIdle()
        Out.save("compose-lazy-list", pixelCopy(compose.activity))
        // Roborazzi's own capture paths (PNG written by Roborazzi, not the native encoder).
        compose.onRoot().captureRoboImage(Out.png("compose-lazy-list-roborazzi-node").path)
        captureScreenRoboImage(Out.png("compose-lazy-list-roborazzi-screen").path)
    }
}

private val AGSL = """
    uniform float2 size;
    half4 main(float2 xy) {
        float2 uv = xy / size;
        float d = distance(uv, float2(0.5, 0.5));
        half3 c = half3(uv.x, uv.y, 0.5 + 0.5 * sin(d * 30.0));
        return half4(c * step(d, 0.48), 1.0);
    }
""".trimIndent()
