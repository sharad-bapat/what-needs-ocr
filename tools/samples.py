"""Make the demo's sample PDFs. All content is made up; the same files come out every run.

  contract.pdf  three pages: plain text; a signature block pasted in as a scan, beside a photo; and an
                annex scanned with an invisible OCR text layer already on it
  poster.pdf    a landscape page: a title drawn as letter outlines, a bar chart whose labels are letter
                outlines too, a logo made of shapes, and a paragraph of real text
  notice.pdf    a letter whose body is real text in a font with a garbage ToUnicode map: it looks right,
                but its text copies out as private-use characters

The drawing helpers come from tools/build_ocr_set.py, so the samples are made the way the constructed set's
cases are. The demo can't run Tesseract, so after making the PDFs, run the crops through it once and keep
the results beside them (tools/ocr_crops.py, then this script's --split step):

  python tools/samples.py demo/samples
  router/target/release/router-cli ... is not needed; ocr_crops.py routes the files itself:
  python tools/ocr_crops.py <list of the three PDFs> --out=demo/samples/ocr.jsonl
  python tools/samples.py --split demo/samples/ocr.jsonl     one <name>.ocr.json per PDF, then ocr.jsonl goes

usage: python tools/samples.py [out dir, default demo/samples]
       python tools/samples.py --split <ocr.jsonl>
"""
import json
import os
import random
import sys
from pathlib import Path

import fitz
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from build_ocr_set import VERA, draw_garbled, draw_outlined, encode, ocr_pdf, scanner, synth_image

SEED = 20261004
A4 = (595.0, 842.0)
HELV = fitz.Font("helv")
BODY = [
    "This agreement is made between Example Ltd (the Client) and Sample Services Ltd (the Supplier) for the",
    "cleaning and upkeep of the Client's offices at 1 Example Street. The Supplier will provide the services",
    "set out in Schedule 1 from 1 February 2026 for twelve months, and either party may end this agreement",
    "with three months' notice in writing. The Client will pay each invoice within thirty days of receiving it.",
    "The Supplier will keep the Client's keys and access cards safe, and will return them on the last day.",
]


def words_on_line(x, base, text, size):
    """The word boxes of one line of Helvetica text at its baseline: (x0, y0, x1, y1, word) each."""
    out = []
    space = HELV.text_length(" ", fontsize=size)
    for w in text.split():
        wd = HELV.text_length(w, fontsize=size)
        out.append((x, base - HELV.ascender * size, x + wd, base - HELV.descender * size, w))
        x += wd + space
    return out


def typed(lines, px_w, px_h, size, margin=60, gap=1.5):
    """Lines of typed text on a white sheet, as a scanner would have seen it."""
    img = Image.new("L", (px_w, px_h), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(VERA), size)
    y = margin
    for line in lines:
        d.text((margin, y), line, fill=20, font=font)
        y += int(size * gap)
    return img, d, y


def contract(path, rng):
    doc = fitz.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((72, 90), "Services agreement", fontname="hebo", fontsize=18)
    y = 130
    for para in range(3):
        for line in BODY:
            p.insert_text((72, y), line, fontname="helv", fontsize=8.6)
            y += 12.5
        y += 10
    p.insert_text((72, 800), "Page 1 of 3", fontname="helv", fontsize=8)

    # page 2: a signature block pasted in as a scan, and a photo that holds no text
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((72, 90), "Schedule 2: signatures", fontname="hebo", fontsize=14)
    for k, line in enumerate(BODY[2:4]):
        p.insert_text((72, 120 + 12.5 * k), line, fontname="helv", fontsize=8.6)
    img, d, y = typed(["Signed for and on behalf of Example Ltd", "", "Name: A. N. Example", "Title: Director",
                       "Date: 15 January 2026"], 1300, 560, 34)
    pts = [(700 + 18 * k, 150 + int(30 * ((k * 7919) % 11) / 11) - 15) for k in range(18)]
    d.line(pts, fill=30, width=5)  # a scrawl where the signature goes
    img, _ = scanner(rng, img, bitonal=False)
    p.insert_image(fitz.Rect(72, 170, 72 + 1300 * 72 / 200, 170 + 560 * 72 / 200), stream=encode(img, jpeg=True))
    p.insert_image(fitz.Rect(72, 400, 312, 560), stream=encode(synth_image(rng, "photo", 600, 400), jpeg=True))
    p.insert_text((72, 574), "Site photo, north wall, taken at the start of the contract.", fontname="helv", fontsize=8)
    p.insert_text((72, 800), "Page 2 of 3", fontname="helv", fontsize=8)

    # page 3: an annex scanned and OCR'd before it got here, so it has an invisible text layer
    rooms = ["offices and meeting rooms", "kitchen and break area", "stairs and landings", "toilets and showers",
             "reception and front door", "windows, inside only", "bins and recycling"]
    lines = ["Annex A: cleaning schedule", ""]
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        lines += [day] + [f"    {r}, {6 + k % 2} to {8 + k % 3} am" for k, r in enumerate(rooms[:4 + len(day) % 4])] + [""]
    img, _, _ = typed(lines, 1240, 1754, 30, margin=120, gap=1.3)
    img, _ = scanner(rng, img, bitonal=True)
    doc.insert_pdf(fitz.open("pdf", ocr_pdf(img, 150)))
    save(doc, path)


def poster(path, rng):
    doc = fitz.open()
    p = doc.new_page(width=842, height=595)
    font = TTFont(str(VERA))
    draw_outlined(p, words_on_line(60, 90, "Quarterly water report", 34), font)
    for k, line in enumerate(["Use at the depot fell in the second quarter after the new taps went in, and rose",
                              "again over the summer. The figures are read from the main meter each month."]):
        p.insert_text((60, 130 + 13 * k), line, fontname="helv", fontsize=10)
    # a bar chart drawn as paths, its labels drawn as outlines too
    x0, base = 100, 500
    sh = p.new_shape()
    sh.draw_line((x0, base), (x0 + 420, base))
    sh.draw_line((x0, base), (x0, 220))
    sh.finish(color=(0.2, 0.2, 0.2), width=1)
    for k, v in enumerate([210, 160, 170, 240]):
        sh.draw_rect(fitz.Rect(x0 + 30 + 100 * k, base - v, x0 + 90 + 100 * k, base))
        sh.finish(fill=(0.25, 0.45, 0.7), color=None)
    sh.commit()
    labels = []
    for k, q in enumerate(["Jan to Mar", "Apr to Jun", "Jul to Sep", "Oct to Dec"]):
        labels += words_on_line(x0 + 26 + 100 * k, base + 16, q, 9)
    labels += words_on_line(x0, 210, "Thousand litres", 9)
    draw_outlined(p, labels, font)
    # a logo made of shapes, no letters
    sh = p.new_shape()
    for k, c in enumerate([(0.85, 0.3, 0.2), (0.95, 0.7, 0.2), (0.3, 0.6, 0.4)]):
        sh.draw_circle((680 + 40 * k, 330), 34)
        sh.finish(fill=c, color=None)
    sh.commit()
    p.insert_text((60, 560), "Example Ltd, facilities team. Made-up figures for a demo.", fontname="helv", fontsize=8)
    save(doc, path)


def notice(path, rng):
    doc = fitz.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((72, 90), "Notice of renewal", fontname="tiro", fontsize=20)
    p.insert_text((72, 112), "15 January 2026", fontname="tiro", fontsize=10)
    body = BODY + ["Unless either party gives notice by 1 December 2026, this agreement renews for another",
                   "twelve months on the same terms. Please keep this letter with your copy of the agreement."]
    words = []
    for k, line in enumerate(body):
        words += words_on_line(72, 150 + 14 * k, line, 9.5)
    draw_garbled(doc, p, words, "pua")
    p.insert_text((72, 800), "Sample Services Ltd, 2 Example Road", fontname="tiro", fontsize=8)
    save(doc, path)


def save(doc, path):
    doc.set_metadata({})
    doc.save(path, garbage=3, deflate=True, no_new_id=True)


def split(results):
    """One <name>.ocr.json per PDF beside it: that file's pages from ocr_crops.py, as merge_json takes them."""
    results = Path(results)
    for line in results.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out = results.parent / (Path(d["file"]).stem + ".ocr.json")
            out.write_text(json.dumps(d["pages"], separators=(",", ":")), encoding="utf-8")
            print(out)


def main():
    if sys.argv[1:2] == ["--split"]:
        split(sys.argv[2])
        return
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/samples")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["OMP_THREAD_LIMIT"] = "1"
    for name, make in [("contract", contract), ("poster", poster), ("notice", notice)]:
        make(out / f"{name}.pdf", random.Random(f"{SEED}-{name}"))
        print(out / f"{name}.pdf")


if __name__ == "__main__":
    main()
