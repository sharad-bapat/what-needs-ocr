"""Check the constructed set's truth with Tesseract, independently of the builder: render each region that
has truth words from the built page at 300 dpi, OCR it (TSV), and count the truth words that have a
Tesseract word with the same text (letters and digits only, any case) and with its centre within 3 pt.
Tune cases only; the held-out ones are left alone.

usage: python tools/check_truth.py [set dir=data/constructed] [max cases]"""
import json, subprocess, sys, tempfile, re
from pathlib import Path
import fitz
from PIL import Image

d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/constructed")
mx = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
norm = lambda s: re.sub(r"[^\w]", "", s).lower()
tot = hit = near_txt = 0
done = 0
for it in m["items"]:
    regs = [r for r in it["regions"] if r["words"]]
    if it["split"] != "tune" or not regs or done >= mx:
        continue
    done += 1
    page = fitz.open(d / it["file"])[0]
    for r in regs:
        box = fitz.Rect(r["box"])
        dpi = 300
        pix = page.get_pixmap(dpi=dpi, clip=box, colorspace=fitz.csGRAY)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "c.png"
            Image.frombytes("L", (pix.width, pix.height), pix.samples).save(png, dpi=(dpi, dpi))
            tsv = subprocess.run(["tesseract", str(png), "stdout", "-l", "eng", "tsv"], capture_output=True, text=True, encoding="utf-8").stdout
        s = 72 / dpi
        ocr = []
        for line in tsv.splitlines()[1:]:
            f = line.split("\t")
            if len(f) == 12 and f[11].strip():
                x, y, w, h = (int(v) for v in f[6:10])
                ocr.append((norm(f[11]), box.x0 + (x + w / 2) * s, box.y0 + (y + h / 2) * s))
        for w in r["words"]:
            t = norm(w[4])
            if not t:
                continue
            tot += 1
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            same = [o for o in ocr if o[0] == t]
            near_txt += bool(same)
            hit += any(abs(o[1] - cx) <= 3 and abs(o[2] - cy) <= 3 for o in same)
print(f"{done} tune cases, truth words {tot}: Tesseract read the same text for {near_txt} ({100*near_txt/max(tot,1):.1f}%), within 3 pt for {hit} ({100*hit/max(near_txt,1):.1f}% of those)")
