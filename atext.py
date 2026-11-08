"""Draws text with Android's own text engine (correct Bengali shaping + Latin),
returns a PNG as bytes. Returns None if anything fails."""
try:
    from jnius import autoclass
    _OK = True
except Exception:
    _OK = False


def render(text, width_px, size_px, argb):
    if not _OK:
        return None
    try:
        String = autoclass("java.lang.String")
        TextPaint = autoclass("android.text.TextPaint")
        Builder = autoclass("android.text.StaticLayout$Builder")
        Alignment = autoclass("android.text.Layout$Alignment")
        Bitmap = autoclass("android.graphics.Bitmap")
        Config = autoclass("android.graphics.Bitmap$Config")
        Fmt = autoclass("android.graphics.Bitmap$CompressFormat")
        Canvas = autoclass("android.graphics.Canvas")
        Baos = autoclass("java.io.ByteArrayOutputStream")

        jstr = String(text)
        paint = TextPaint(1)
        paint.setTextSize(float(size_px))
        if argb >= 2 ** 31:
            argb -= 2 ** 32
        paint.setColor(argb)
        width = max(int(width_px), 50)
        layout = Builder.obtain(jstr, 0, jstr.length(), paint, width) \
            .setAlignment(Alignment.ALIGN_NORMAL).build()
        height = max(int(layout.getHeight()), 1)
        bmp = Bitmap.createBitmap(width, height, Config.ARGB_8888)
        layout.draw(Canvas(bmp))
        out = Baos()
        bmp.compress(Fmt.PNG, 100, out)
        data = out.toByteArray()
        return bytes((b & 0xFF) for b in data)
    except Exception:
        return None
