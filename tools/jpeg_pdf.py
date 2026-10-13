"""Omkoda en raster-PDF:s bilder till JPEG q92 i full upplösning, för Drive-uppladdningens 10 MB-tak.

Användning: python tools/jpeg_pdf.py <in.pdf> <ut.pdf>
(minnet classroom-uppladdning: 1100 px och 256 färger syntes, full upplösning q92 gör det inte)."""
import io, sys
import pikepdf
from pikepdf import PdfImage, Name
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
pdf = pikepdf.open(src)
n = 0
for page in pdf.pages:
    for name, raw in list(page.images.items()):
        if raw.get('/Filter') == Name.DCTDecode:
            continue
        try:
            im = PdfImage(raw).as_pil_image()
        except Exception:
            continue
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        smask = raw.get('/SMask')
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=92)
        raw.write(buf.getvalue(), filter=Name.DCTDecode)
        raw.ColorSpace = Name.DeviceRGB if im.mode == 'RGB' else Name.DeviceGray
        raw.BitsPerComponent = 8
        for k in ('/DecodeParms', '/Predictor'):
            if k in raw:
                del raw[k]
        n += 1
pdf.save(dst, compress_streams=True)
import os
print(n, 'bilder', os.path.getsize(src) // 1024, '->', os.path.getsize(dst) // 1024, 'kB')
