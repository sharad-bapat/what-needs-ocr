"""Sheets for checking the real set's reference by eye: for a seeded sample of pages with reference OCR
words, the region's part of the page as displayed (after /Rotate, annotations left out), each reference
word boxed in red with its text above it, saved as PNGs to look at.

usage: python tools/check_real.py <govdocs1 dir> <thread> <out dir> [pages=20] [seed]
Only the tune thread (005) is checked; the held-out thread is left alone.
"""
import json
import random
import sys
from pathlib import Path

import io

import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    root, thread, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    if thread != "005":
        sys.exit("only the tune thread is checked by eye")
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else 20261004
    items = json.loads((ROOT / "data" / "real" / f"{thread}.json").read_text(encoding="utf-8"))["items"]
    with_words = [i for i in items if i["regions"]]
    sample = random.Random(seed).sample(with_words, min(n, len(with_words)))
    out.mkdir(parents=True, exist_ok=True)
    z = 110 / 72
    for it in sample:
        page = fitz.open(root / it["file"])[it["page"] - 1]
        # the page as displayed (after /Rotate), drawn on directly: the reference's boxes are in that frame
        full = Image.open(io.BytesIO(page.get_pixmap(matrix=fitz.Matrix(z, z), annots=False).tobytes("png"))).convert("RGB")
        for r in it["regions"]:
            im = full.copy()
            d = ImageDraw.Draw(im)
            for w in r["words"]:
                d.rectangle([w[0] * z, w[1] * z, w[2] * z, w[3] * z], outline=(220, 0, 0), width=2)
                d.text((w[0] * z, max(0, w[1] * z - 11)), w[4], fill=(220, 0, 0))
            b = [max(0, (r["box"][0] - 12) * z), max(0, (r["box"][1] - 12) * z), min(im.width, (r["box"][2] + 12) * z), min(im.height, (r["box"][3] + 12) * z)]
            if b[2] <= b[0] or b[3] <= b[1]:
                continue
            name = it["id"].replace("/", "_").replace("#", "_p") + f"_{r['why']}.png"
            im.crop(b).save(out / name)
            print(name, len(r["words"]), "words:", " ".join(w[4] for w in r["words"][:40]))

if __name__ == "__main__":
    main()
