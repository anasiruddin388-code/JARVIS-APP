"""Draws text with Android's own text engine (correct Bengali shaping,
Latin letters and emoji). render() returns PNG bytes, or None on failure;
the reason is kept in LAST_ERR."""
LAST_ERR = ""

try:
    from jnius import autoclass
    _OK = True
except Exception as _e:
    _OK = False
    LAST_ERR = "no jnius: " + repr(_e)


def render(text, width_px, size_px, argb):
    global LAST_ERR
    if not _OK:
        return None
    try:
        TextPaint = autoclass("android.text.TextPaint")
        Builder = autoclass("android.text.StaticLayout$Builder")
        Alignment = autoclass("android.text.Layout$Alignment")
        Bitmap = autoclass("android.graphics.Bitmap")
        Config = autoclass("android.graphics.Bitmap$Config")
        Fmt = autoclass("android.graphics.Bitmap$CompressFormat")
        Canvas = autoclass("android.graphics.Canvas")
        Baos = autoclass("java.io.ByteArrayOutputStream")

        n16 = len(text.encode("utf-16-le")) // 2   # Java string length
        paint = TextPaint(1)
        paint.setTextSize(float(size_px))
        if argb >= 2 ** 31:
            argb -= 2 ** 32
        paint.setColor(argb)
        width = max(int(width_px), 50)
        layout = Builder.obtain(text, 0, n16, paint, width).build()
        height = max(int(layout.getHeight()), 1)
        bmp = Bitmap.createBitmap(width, height, Config.ARGB_8888)
        layout.draw(Canvas(bmp))
        out = Baos()
        bmp.compress(Fmt.PNG, 100, out)
        data = out.toByteArray()
        return bytes((b & 0xFF) for b in data)
    except Exception as e:
        LAST_ERR = "render: " + repr(e)[:200]
        return None
