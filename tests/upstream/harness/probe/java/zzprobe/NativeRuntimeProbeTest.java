package zzprobe;

import static com.google.common.truth.Truth.assertThat;

import android.database.sqlite.SQLiteDatabase;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;

/** Harness-only: records which libandroid_runtime the test JVM loaded. */
@RunWith(AndroidJUnit4.class)
@Config(sdk = 36)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class NativeRuntimeProbeTest {
  @Test
  public void reportLoadedLibrary() throws Exception {
    SQLiteDatabase db = SQLiteDatabase.create(null);
    db.execSQL("create table t(x)");
    db.close();
    Bitmap b = Bitmap.createBitmap(4, 4, Bitmap.Config.ARGB_8888);
    new Canvas(b).drawColor(Color.RED);
    assertThat(b.getPixel(1, 1)).isEqualTo(Color.RED);
    String maps = new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get("/proc/self/maps")));
    String lib = "none";
    for (String line : maps.split("\n")) {
      if (line.contains("libandroid_runtime")) { lib = line.substring(line.indexOf('/')); break; }
    }
    System.out.println("PROBE os.arch=" + System.getProperty("os.arch")
        + " java=" + System.getProperty("java.version")
        + " loadedFrom=" + System.getProperty("robolectric.arm64.loadedFrom")
        + " mapped=" + lib);
  }
}
