"""Build the constructed OCR set: one-page PDFs where the text that only exists as pixels is known.

Each case starts from a real digital NDA page (ContractNLI, CC BY 4.0). Most get one pasted image at a
known box; what is pasted decides what OCR should find there:

  text        a crop of another contract page, rasterised: its words are the truth for that box
  text_ocr    the same, with Tesseract's invisible text layer on it (control: the layer is already there)
  full_scan   the whole page rasterised, image only: every word on it is truth
  outlined    a crop's words redrawn as glyph outlines (Vera, the font reportlab ships), one filled path
              per letter, as converters that outline text do: no text layer, so OCR must read them
  garbled     a crop's words redrawn as real Helvetica text with a ToUnicode map that sends every code to
              a private-use or a control character: the page looks right but its text layer is garbage
  photo       smooth random blobs, no text (negative)
  logo        flat geometric shapes, no letters (negative)
  blank       a blank scanned sheet: paper grey plus noise (negative)
  control     nothing pasted (all the text is the file's own)

The truth for a pasted crop is the source page's words that lie wholly inside the crop, moved into the
new page: scaled to the box and turned by the scan's small rotation, each given as the axis-aligned box
of its turned corners. For outlined and garbled text the crop's words are redrawn at their places, each
sized to fit its own box, and the truth box is the line-height box of what was drawn. Words the crop edge cuts are left out of the truth and listed as "cut" boxes,
since part of each shows in the image and an OCR engine may read it or not. Each case also lists the
file's own words (the page's digital text, as PyMuPDF reads it before anything is pasted), so a case's
whole truth is file_words plus every region's words.

Placement, wraps (one image, strips, a form XObject, an inline image) and scanner damage (DPI, JPEG or
lossless, greyscale or bitonal, noise, a rotation of up to 1.5 degrees) follow where-are-the-regions'
tools/build_set.py, which this is adapted from; the outline pen follows its tools/build_vectors.py, and
the ToUnicode writer wordbox's tools/garble.py. The split (tune or held-out) is by the same hash of the
source file, so the held-out sources are where-are-the-regions' held-out sources too.

Boxes are in PDF points with the origin at the top left of the page (PyMuPDF's convention).

usage: python tools/build_ocr_set.py <contract-nli raw dir> <labels-real.json> <outdir> [cases=600] [seed]
labels-real.json is scan-or-text's (data/labels-real.json); only pages it labels plain text are used.
"""
import hashlib
import io
import json
import math
import random
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import fitz
import numpy as np
import reportlab
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter

SEED = 20261003
KINDS = ["text"] * 8 + ["text_ocr"] * 2 + ["full_scan"] * 2 + ["outlined"] * 2 + ["garbled"] * 2 + ["photo", "logo", "blank", "control"]
WRAPS = ["image", "image", "strips", "form", "inline"]
DPIS = [150, 200, 300]
MIN_WORDS = 25  # a text crop must hold at least this many whole words from its source
VERA = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
CONTROL = [c for c in range(1, 32) if c not in (9, 10, 13)]


def split_of(source):
    return "heldout" if hashlib.sha256(source.encode()).digest()[0] % 2 else "tune"


def words_of(page, within=None):
    """The page's words as [x0, y0, x1, y1, text]; with `within`, only those wholly inside it, plus the
    boxes of those it cuts."""
    ws = [[w[0], w[1], w[2], w[3], w[4]] for w in page.get_text("words")]
    # tested at full precision, written to 2 decimals (a hundredth of a point)
    out = lambda vs: [[round(v, 2) for v in w[:4]] + w[4:] for w in vs]
    if within is None:
        return out(ws), []
    r = fitz.Rect(within)
    inside = [w for w in ws if fitz.Rect(w[:4]) in r]
    cut = [w[:4] for w in ws if fitz.Rect(w[:4]).intersects(r) and fitz.Rect(w[:4]) not in r]
    return out(inside), out(cut)


def move(box, clip, dest, angle):
    """A box in the source page's clip, moved to dest: scaled, then turned by the scan's rotation about
    dest's centre (PIL turns the image anticlockwise on screen by `angle` degrees, keeping its size)."""
    sx, sy = dest.width / clip.width, dest.height / clip.height
    cx, cy = dest.x0 + dest.width / 2, dest.y0 + dest.height / 2
    a = math.radians(angle)
    pts = []
    for x, y in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])):
        px, py = dest.x0 + (x - clip.x0) * sx - cx, dest.y0 + (y - clip.y0) * sy - cy
        # anticlockwise on screen, with y pointing down
        pts.append((cx + px * math.cos(a) + py * math.sin(a), cy - px * math.sin(a) + py * math.cos(a)))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


# ---- rasters ---------------------------------------------------------------------------------

def text_crop(rng, pages, w, h):
    """A w x h point box of text from a random source page with at least MIN_WORDS whole words in it."""
    for _ in range(40):
        doc, pno = rng.choice(pages)
        page = doc[pno]
        r = page.rect
        if r.width < w or r.height < h:
            continue
        x, y = rng.uniform(0, r.width - w), rng.uniform(0, r.height - h)
        clip = fitz.Rect(x, y, x + w, y + h)
        inside, cut = words_of(page, clip)
        if len(inside) >= MIN_WORDS:
            return page, clip, inside, cut
    return None


def render(page, clip, dpi):
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def synth_image(rng, kind, px_w, px_h):
    nr = np.random.default_rng(rng.randrange(1 << 30))
    if kind == "photo":
        small = nr.random((max(2, px_h // 40), max(2, px_w // 40), 3))
        img = Image.fromarray((small * 255).astype(np.uint8), "RGB").resize((px_w, px_h), Image.BICUBIC)
        return img.filter(ImageFilter.GaussianBlur(3))
    if kind == "logo":
        img = Image.new("RGB", (px_w, px_h), "white")
        d = ImageDraw.Draw(img)
        for _ in range(rng.randint(2, 5)):
            c = tuple(rng.randrange(256) for _ in range(3))
            x0, y0 = rng.randrange(px_w), rng.randrange(px_h)
            box = [x0, y0, min(px_w, x0 + rng.randint(px_w // 6, px_w // 2)), min(px_h, y0 + rng.randint(px_h // 6, px_h // 2))]
            (d.ellipse if rng.random() < 0.5 else d.rectangle)(box, fill=c)
        return img
    if kind == "blank":
        a = np.clip(236 + nr.normal(0, 4, (px_h, px_w)), 0, 255).astype(np.uint8)
        return Image.fromarray(a, "L")
    raise ValueError(kind)


def scanner(rng, img, bitonal):
    """Scanner-style damage: a small rotation, noise, and bitonal or greyscale."""
    angle = rng.uniform(-1.5, 1.5)
    img = img.convert("L").rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    a = np.asarray(img, dtype=np.float32) + np.random.default_rng(rng.randrange(1 << 30)).normal(0, 6, img.size[::-1])
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
    return (img.point(lambda v: 255 if v > 160 else 0).convert("1") if bitonal else img), angle


def encode(img, jpeg):
    buf = io.BytesIO()
    if jpeg and img.mode != "1":
        img.save(buf, "JPEG", quality=75)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


# ---- placement --------------------------------------------------------------------------------

def free_band(page, need_h):
    """Largest empty horizontal band inside the margins, as (y0, y1), or None if it's under need_h."""
    r = page.rect
    boxes = [fitz.Rect(b[:4]) for b in page.get_text("blocks")]
    boxes += [fitz.Rect(d["rect"]) for d in page.get_drawings()]
    boxes += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    ys = sorted((b.y0, b.y1) for b in boxes if not b.is_empty)
    top, bottom = r.height * 0.06, r.height * 0.94
    best, cur = None, top
    for y0, y1 in ys + [(bottom, bottom)]:
        if y0 - cur > (best[1] - best[0] if best else 0):
            best = (cur, min(y0, bottom))
        cur = max(cur, y1)
    return best if best and best[1] - best[0] >= need_h else None


def make_base(src_page, rng, box_h):
    """A new page with the source page's content and room for a box_h-high image. Returns (doc, page, band, how)."""
    out = fitz.open()
    out.insert_pdf(src_page.parent, from_page=src_page.number, to_page=src_page.number)
    page = out[0]
    band = free_band(page, box_h + 12)
    if band:
        return out, page, band, "free_band"
    # Shrink the original into the top part of a fresh page and use the rest.
    r = src_page.rect
    out = fitz.open()
    page = out.new_page(width=r.width, height=r.height)
    top = rng.random() < 0.5
    content = fitz.Rect(0, box_h + 24, r.width, r.height) if top else fitz.Rect(0, 0, r.width, r.height - box_h - 24)
    page.show_pdf_page(content, src_page.parent, src_page.number)
    band = (12, box_h + 18) if top else (r.height - box_h - 18, r.height - 6)
    return out, page, band, "shrunk_top" if top else "shrunk_bottom"


def inline_image(page, box, img):
    """Draw img into box as a BI ... ID ... EI inline image in the page's own content."""
    g = img.convert("L")
    data = zlib.compress(g.tobytes())
    r = page.rect
    x, y, w, h = box.x0, r.height - box.y1, box.width, box.height
    ops = (f"q {w:.3f} 0 0 {h:.3f} {x:.3f} {y:.3f} cm BI /W {g.width} /H {g.height} /CS /G /BPC 8 /F /Fl ID ".encode()
           + data + b"\nEI Q\n")
    xref = page.parent.get_new_xref()
    page.parent.update_object(xref, "<<>>")
    page.parent.update_stream(xref, ops)
    # Append the stream to /Contents (PyMuPDF has no public call for this).
    contents = page.get_contents()
    page.parent.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{c} 0 R" for c in contents + [xref]) + "]")


def place(rng, doc, page, box, img, jpeg, wrap):
    if wrap == "inline":
        inline_image(page, box, img)
        return
    data = encode(img, jpeg)
    if wrap == "strips":
        n = rng.randint(3, 6)
        W, H = img.size
        for i in range(n):
            a, b = H * i // n, H * (i + 1) // n
            part = encode(img.crop((0, a, W, b)), jpeg)
            y0 = box.y0 + box.height * a / H
            y1 = box.y0 + box.height * b / H
            page.insert_image(fitz.Rect(box.x0, y0, box.x1, y1), stream=part, keep_proportion=False)
        return
    if wrap == "form":
        one = fitz.open()
        p = one.new_page(width=box.width, height=box.height)
        p.insert_image(p.rect, stream=data, keep_proportion=False)
        page.show_pdf_page(box, one, 0)
        return
    page.insert_image(box, stream=data, keep_proportion=False)


def ocr_pdf(img, dpi):
    """Tesseract over img: a one-page PDF with the image and an invisible text layer."""
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "i.png"
        img.convert("L").save(png, dpi=(dpi, dpi))
        subprocess.run(["tesseract", str(png), str(Path(tmp) / "o"), "-l", "eng", "pdf"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return fitz.open(Path(tmp) / "o.pdf").tobytes()


# ---- redrawn text ---------------------------------------------------------------------------

def fit(box, width1, asc, desc):
    """A word redrawn in its box: the size that fits its height and width (width1 is the width at size 1,
    asc and desc the font's per-em ascent and descent), its baseline, and the line-height box it gets."""
    x0, y0, x1, y1 = box
    size_h = (y1 - y0) / (asc - desc)
    size = min(size_h, (x1 - x0) / width1) if width1 > 0 else size_h
    base = y1 + desc * size_h
    return size, base, [round(x0, 2), round(base - asc * size, 2), round(x0 + width1 * size, 2), round(base - desc * size, 2)]


class ShapePen(BasePen):
    """Glyph outlines into a PyMuPDF shape, in page coordinates (y down), quadratics as cubics."""

    def __init__(self, glyphset, shape, scale, x, base):
        super().__init__(glyphset)
        self.sh, self.s, self.x, self.base, self.cur, self.start = shape, scale, x, base, None, None

    def _pt(self, pt):
        return fitz.Point(self.x + pt[0] * self.s, self.base - pt[1] * self.s)

    def _moveTo(self, pt):
        self.cur = self.start = self._pt(pt)

    def _lineTo(self, pt):
        q = self._pt(pt)
        self.sh.draw_line(self.cur, q)
        self.cur = q

    def _curveToOne(self, a, b, c):
        q = self._pt(c)
        self.sh.draw_bezier(self.cur, self._pt(a), self._pt(b), q)
        self.cur = q

    def _closePath(self):
        if self.cur != self.start:
            self.sh.draw_line(self.cur, self.start)
        self.cur = self.start


def draw_outlined(page, words, font):
    """Each word's letters as filled paths, one per letter; returns the truth words."""
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    asc, desc = font["hhea"].ascent / upm, font["hhea"].descent / upm
    truth = []
    for x0, y0, x1, y1, text in words:
        glyphs = [cmap.get(ord(ch)) for ch in text]
        width1 = sum(gs[g].width for g in glyphs if g) / upm
        size, base, tbox = fit((x0, y0, x1, y1), width1, asc, desc)
        x = x0
        for g in glyphs:
            if not g:
                continue
            sh = page.new_shape()
            gs[g].draw(ShapePen(gs, sh, size / upm, x, base))
            sh.finish(fill=(0, 0, 0), color=None, even_odd=False, closePath=False)
            sh.commit()
            x += gs[g].width * size / upm
        truth.append(tbox + [text])
    return truth


def draw_garbled(doc, page, words, variant):
    """Each word as Helvetica text, then the font's ToUnicode sends every code to garbage; returns the
    truth words."""
    helv = fitz.Font("helv")
    truth = []
    for x0, y0, x1, y1, text in words:
        size, base, tbox = fit((x0, y0, x1, y1), helv.text_length(text, fontsize=1), helv.ascender, helv.descender)
        page.insert_text((x0, base), text, fontname="helv", fontsize=size)
        truth.append(tbox + [text])
    xref = next(f[0] for f in page.get_fonts(full=True) if f[4] == "helv")
    garbage = {c: chr(0xE000 + c) if variant == "pua" else chr(CONTROL[c % len(CONTROL)]) for c in range(32, 256)}
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
             "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def", "1 begincodespacerange", "<00> <FF>", "endcodespacerange"]
    items = sorted(garbage.items())
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        lines += [f"<{c:02X}> <{s.encode('utf-16-be').hex().upper()}>" for c, s in chunk]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    cm = doc.get_new_xref()
    doc.update_object(cm, "<<>>")
    doc.update_stream(cm, "\n".join(lines).encode("latin-1"))
    doc.xref_set_key(xref, "ToUnicode", f"{cm} 0 R")
    return truth


# ---- cases ------------------------------------------------------------------------------------

def build_case(rng, i, src, pno, pool_pages):
    page0 = src[pno]
    r = page0.rect
    # cases alternate between the splits, so the kind steps every two cases: each split gets every kind
    kind = KINDS[(i // 2) % len(KINDS)]
    case = {"id": f"o{i:04d}", "kind": kind, "source_page": pno, "regions": []}

    if kind == "control":
        out = fitz.open()
        out.insert_pdf(src, from_page=pno, to_page=pno)
        case.update(placement="none", file_words=words_of(out[0])[0])
        return out, case

    if kind == "full_scan":
        dpi = rng.choice(DPIS)
        bitonal = rng.random() < 0.3
        img, angle = scanner(rng, render(page0, r, dpi), bitonal)
        out = fitz.open()
        p = out.new_page(width=r.width, height=r.height)
        jpeg = rng.random() < 0.5
        p.insert_image(p.rect, stream=encode(img, jpeg), keep_proportion=False)
        words = [move(w[:4], r, r, angle) + [w[4]] for w in words_of(page0)[0]]
        case.update(placement="full_page", dpi=dpi, jpeg=jpeg, bitonal=bitonal, angle=round(angle, 3), file_words=[])
        case["regions"].append({"box": [0, 0, r.width, r.height], "expect": "ocr", "why": "full_scan", "words": words, "cut": []})
        return out, case

    # Pick a box: from a stamp (about 2% of the page) to about half of it.
    frac = rng.choice([0.02, 0.05, 0.1, 0.2, 0.35, 0.5])
    aspect = rng.uniform(0.6, 3.0)
    area = frac * r.width * r.height
    w = min(r.width * 0.85, (area * aspect) ** 0.5)
    h = min(r.height * 0.6, area / w)
    out, page, band, how = make_base(page0, rng, h)
    x0 = rng.uniform(r.width * 0.06, max(r.width * 0.06, r.width * 0.94 - w))
    y0 = rng.uniform(band[0] + 6, max(band[0] + 6, band[1] - 6 - h))
    box = fitz.Rect(x0, y0, x0 + w, y0 + h)
    dpi = rng.choice(DPIS)
    jpeg = rng.random() < 0.5
    bitonal = rng.random() < 0.25
    wrap = rng.choice(WRAPS)
    case.update(placement=how, wrap=wrap, dpi=dpi, jpeg=jpeg, frac=frac, file_words=words_of(page)[0])

    if kind in ("outlined", "garbled"):
        got = text_crop(rng, pool_pages, w, h)
        if not got:
            return None, None
        sp, clip, inside, cut = got
        words = [move(t[:4], clip, box, 0) + [t[4]] for t in inside]
        if kind == "outlined":
            truth = draw_outlined(page, words, TTFont(VERA))
            case.update(wrap="paths", dpi=None, jpeg=None)
        else:
            variant = rng.choice(["pua", "control"])
            truth = draw_garbled(out, page, words, variant)
            case.update(wrap="text", variant=variant, dpi=None, jpeg=None)
        case["regions"].append({"box": [round(v, 2) for v in box], "expect": "ocr", "why": kind, "words": truth, "cut": []})
        return out, case

    if kind in ("text", "text_ocr"):
        got = text_crop(rng, pool_pages, w, h)
        if not got:
            return None, None
        sp, clip, inside, cut = got
        img, angle = scanner(rng, render(sp, clip, dpi), bitonal)
        case.update(bitonal=bitonal, angle=round(angle, 3))
        region = {"box": [round(v, 2) for v in box], "words": [move(t[:4], clip, box, angle) + [t[4]] for t in inside],
                  "cut": [move(c, clip, box, angle) for c in cut]}
        if kind == "text_ocr":
            one = fitz.open("pdf", ocr_pdf(img, dpi))
            page.show_pdf_page(box, one, 0, keep_proportion=False)
            case["wrap"] = "form_ocr"
            region.update(expect="text_layer", why=kind)
        else:
            place(rng, out, page, box, img, jpeg, wrap)
            region.update(expect="ocr", why=kind)
        case["regions"].append(region)
    else:
        px_w, px_h = max(2, int(w / 72 * dpi)), max(2, int(h / 72 * dpi))
        img = synth_image(rng, kind, px_w, px_h)
        place(rng, out, page, box, img, jpeg, wrap)
        case["regions"].append({"box": [round(v, 2) for v in box], "expect": "none", "why": kind, "words": [], "cut": []})
    return out, case


def main():
    raw, labels, outdir, *rest = sys.argv[1:]
    cases = int(rest[0]) if rest else 600
    seed = int(rest[1]) if len(rest) > 1 else SEED
    rows = json.loads(Path(labels).read_text(encoding="utf-8"))
    names = sorted(r["file"].replace("\\", "/").split("/raw/", 1)[1] for r in rows
                   if r.get("category") == "text" and all(p["label"] == "TEXT" and p["image_frac"] == 0 for p in r["per_page"]))
    rng = random.Random(seed)
    out = Path(outdir)
    docs = {n: fitz.open(Path(raw) / n) for n in names}
    by_split = {s: [n for n in names if split_of(n) == s] for s in ("tune", "heldout")}
    pool = {s: [(docs[n], p) for n in by_split[s] for p in range(len(docs[n]))] for s in by_split}
    manifest = {"seed": seed, "cases": cases, "kinds": KINDS, "dataset": "ContractNLI raw PDFs (CC BY 4.0)",
                "box_convention": "PDF points, origin top left",
                "truth": "file_words plus each region's words; a region's cut boxes may be read or not", "items": []}
    i = 0
    while i < cases:
        split = "tune" if i % 2 == 0 else "heldout"
        name = rng.choice(by_split[split])
        src = docs[name]
        pno = rng.randrange(len(src))
        doc, case = build_case(rng, i, src, pno, pool[split])
        if doc is None:
            continue
        case.update(source=name, split=split)
        path = out / split / f"{case['id']}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        doc.set_metadata({})  # no dates, so a rebuild is byte-identical
        doc.save(path, deflate=True, garbage=3, no_new_id=True)
        case["file"] = f"{split}/{path.name}"
        case["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["items"].append(case)
        i += 1
        if i % 50 == 0:
            print(f"  {i}/{cases}", file=sys.stderr)
    # compact, one case per line: the word lists make an indented file many times larger
    head = json.dumps({k: v for k, v in manifest.items() if k != "items"}, separators=(",", ":"))[:-1]
    body = ",\n".join(json.dumps(c, separators=(",", ":")) for c in manifest["items"])
    (out / "manifest.json").write_text(head + ',"items":[\n' + body + "\n]}\n", encoding="utf-8")
    print(f"{len(manifest['items'])} cases in {out}")


if __name__ == "__main__":
    main()
