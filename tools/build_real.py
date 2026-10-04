"""Build the real set: pages from a govdocs1 thread, each with a reference word list made without the router.

Pages: every page with a usable text layer (at least 20 visible words that decode, and decodable words at
least half of all its words), and of those, per file, up to 2 that draw an image or a vector graphic and
up to 2 that don't, picked by a seed. Pages with no usable layer (whole scans) aren't the question here:
they get OCR'd whole by any method.

Reference, per page, from PyMuPDF and Tesseract, never from where-are-the-regions or the router:
  file words    PyMuPDF's words that are visible (not drawn invisibly, as an OCR layer is) and decode (no
                private-use, control or U+FFFD characters)
  pixel words   words that exist only as pixels or paths: the whole page (annotations left out) at 400
                dpi read by Tesseract, words at a confidence of 85 or more with a letter or digit in them,
                less those whose centre lands on a visible file word (its box grown by 2 pt), which are
                that word read again
  garbled words the same OCR's words whose centre lands on a visible file word that doesn't decode
  untrusted     a text layer can decode to ordinary characters and still be wrong (005448's reads ",f",
                "¼,G": no character test catches it). So every picked page is OCR'd and compared with its
                layer (layer_agreement: OCR words that land on file words, matched by text or inside the
                layer's text along the line). Where at least 20 are compared and fewer than half agree,
                the layer is untrusted, and the page's reference is its OCR words alone, as one region.
                Each page records its agreement.
Pages are read turned so their own text runs left to right (ocr_crops.turned), and the boxes are turned back.
(Removing the text layer by redaction and reading what's left was tried first and dropped: on 005331 the
body text survived it, apparently inside form XObjects, and on 005721 some words did.)
It's an agreement measure, not truth: Tesseract at 400 dpi is careful, not right, and is checked by eye
on a sample (results/real-reference-check.md).

Boxes are in points from the top left of the page as displayed (after /Rotate), as the router's are.
Tesseract runs as tools/ocr_crops.py runs it, cached the same way.

usage: python tools/build_real.py <govdocs1 dir> <thread> [seed]      writes data/real/<thread>.json
The thread's split is in the manifest: 005 is tune, 006 is held out.
"""
import hashlib
import json
import random
import re
import sys
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import fitz
from rich.progress import MofNCompleteColumn, Progress, TimeElapsedColumn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_crops import ARGS, CACHE, read, tesseract_version, turned  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPLITS = {"005": "tune", "006": "heldout"}
SEED = 20261004
DPI = 400
MIN_WORDS = 20
MIN_CONF = 85
PER_FILE = 2


def undecodable(s):
    """U+FFFD, private use, or a control character, C0 or C1."""
    return any(c == "\ufffd" or "\ue000" <= c <= "\uf8ff" or (unicodedata.category(c) == "Cc" and not c.isspace()) for c in s)


def norm(s):
    return re.sub(r"[^0-9a-z]", "", s.lower())


def displayed(page, b):
    r = fitz.Rect(b) * page.rotation_matrix
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


def file_words(page):
    """(visible decodable words, boxes of visible undecodable words, all words), boxes as displayed."""
    hidden = [fitz.Rect(s["bbox"]) for s in page.get_texttrace() if s["type"] == 3]
    good, bad = [], []
    words = page.get_text("words")
    for w in words:
        c = fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
        if any(c in h for h in hidden):
            continue
        (bad if undecodable(w[4]) else good).append(displayed(page, w[:4]) + ([w[4]] if not undecodable(w[4]) else []))
    return good, bad, words


def render(page, dpi):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False, annots=False)
    return pix.tobytes("png"), pix


def upright(doc, pno):
    """The page rendered turned so its own text runs left to right (ocr_crops.turned), and the matrix from
    that render's points to the page as displayed."""
    page, _, back, keep = turned(doc[pno])
    return render(page, DPI)[0], back


def shown(rot, b):
    r = fitz.Rect(b) * rot
    return [round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)]


def layer_agreement(ws, good):
    """How well the text layer says what the page shows: of the OCR words of 3 or more letters and digits
    that land within 6 pt of a file word, how many agree with the layer, either as a file word of the same
    text there, or inside the layer's text along that line (the layer and OCR break words differently:
    "341 4," against "3414,"). Returns (words compared, words that agree)."""
    c = lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    on, agree = 0, 0
    for w in ws:
        t = norm(w[4])
        if len(t) < 3:
            continue
        wx, wy = c(w)
        hits = [g for g in good if g[0] - 6 <= wx <= g[2] + 6 and g[1] - 6 <= wy <= g[3] + 6]
        if not hits:
            continue
        on += 1
        if any(norm(g[4]) == t for g in hits):
            agree += 1
            continue
        g = min(hits, key=lambda g: abs(c(g)[0] - wx) + 2 * abs(c(g)[1] - wy))
        gy, gh = c(g)[1], g[3] - g[1]
        line = sorted((h for h in good if abs(c(h)[1] - gy) <= 0.5 * gh and abs(c(h)[0] - wx) <= 200), key=lambda h: h[0])
        agree += t in "".join(norm(h[4]) for h in line)
    return on, agree


def tess_words(png, settings):
    """Tesseract over a whole rendered page: words as [x0, y0, x1, y1, text, conf] in points."""
    key = hashlib.sha256(png + b"|" + settings + b"|" + str(DPI).encode()).hexdigest()[:24]
    tsv, _ = read(png, DPI, key)
    s, out = 72 / DPI, []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) == 12 and f[0] == "5" and f[11].strip():
            x, y, w, h = (int(v) for v in f[6:10])
            out.append([round(x * s, 2), round(y * s, 2), round((x + w) * s, 2), round((y + h) * s, 2), f[11], round(float(f[10]), 1)])
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    root, thread = Path(sys.argv[1]), sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else SEED
    CACHE.mkdir(parents=True, exist_ok=True)
    settings = "|".join([tesseract_version(), *ARGS]).encode()
    pdfs = sorted((root / thread).glob("*.pdf"))
    items, jobs, skipped = [], [], {"unreadable": 0, "no usable text layer": 0}
    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn(), transient=True) as bar:
        task = bar.add_task(f"pages of {thread}", total=len(pdfs))
        for path in pdfs:
            bar.advance(task)
            try:
                doc = fitz.open(path)
                if doc.needs_pass:
                    raise ValueError("encrypted")
                pages = []
                for pno in range(doc.page_count):
                    good, bad, words = file_words(doc[pno])
                    if len(good) >= MIN_WORDS and len(good) >= 0.5 * len(words):
                        marks = bool(doc[pno].get_image_info()) or bool(doc[pno].get_drawings())
                        pages.append((pno, marks, good, bad))
                    else:
                        skipped["no usable text layer"] += 1
            except Exception:
                skipped["unreadable"] += 1
                continue
            rng = random.Random(f"{seed}:{path.name}")
            with_marks = [p for p in pages if p[1]]
            without = [p for p in pages if not p[1]]
            picked = rng.sample(with_marks, min(PER_FILE, len(with_marks))) + rng.sample(without, min(PER_FILE, len(without)))
            for pno, marks, good, bad in sorted(picked):
                page = doc[pno]
                item = {"id": f"{thread}/{path.stem}#{pno + 1}", "file": f"{thread}/{path.name}", "page": pno + 1, "split": SPLITS.get(thread, "other"),
                        "kind": "real_marks" if marks else "real_plain", "width": round(page.rect.width if page.rotation % 180 == 0 else page.rect.height, 2),
                        "height": round(page.rect.height if page.rotation % 180 == 0 else page.rect.width, 2), "file_words": good, "regions": []}
                items.append(item)
                jobs.append((item, path, pno, good, bad))
        bar.update(task, description=f"tesseract, {thread}", completed=0, total=len(jobs))

        def one(item, png, rot, good, bad_boxes):
            # read upright (the page with /Rotate taken off), then boxes onto the page as displayed
            ws = [shown(rot, w[:4]) + w[4:] for w in tess_words(png, settings) if w[5] >= MIN_CONF and re.search(r"[0-9A-Za-z]", w[4])]
            good_boxes = [g[:4] for g in good]
            on = lambda w, boxes: any(b[0] - 2 <= (w[0] + w[2]) / 2 <= b[2] + 2 and b[1] - 2 <= (w[1] + w[3]) / 2 <= b[3] + 2 for b in boxes)
            on_layer, agree = layer_agreement(ws, good)
            item["agreement"] = round(agree / on_layer, 3) if on_layer else None
            if on_layer >= 20 and agree < 0.5 * on_layer:
                item["file_words"] = []
                groups = {"untrusted": ws}
            else:
                groups = {"garbled": [w for w in ws if on(w, bad_boxes) and not on(w, good_boxes)],
                          "pixels": [w for w in ws if not on(w, bad_boxes) and not on(w, good_boxes)]}
            for why, g in groups.items():
                if g:
                    box = [min(w[0] for w in g), min(w[1] for w in g), max(w[2] for w in g), max(w[3] for w in g)]
                    item["regions"].append({"box": box, "expect": "ocr", "why": why, "words": [w[:5] for w in g], "conf": [w[5] for w in g], "cut": []})
            bar.advance(task)

        # pages are rendered here, on this thread (PyMuPDF isn't thread-safe), just before their OCR, with
        # at most 8 waiting, so the 400 dpi renders never pile up in memory
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = set()
            for item, path, pno, good_boxes, bad_boxes in jobs:
                with fitz.open(path) as doc:
                    png, rot = upright(doc, pno)
                pending.add(pool.submit(one, item, png, rot, good_boxes, bad_boxes))
                if len(pending) >= 8:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for f in done:
                        f.result()
            for f in pending:
                f.result()
    for it in items:
        it["regions"].sort(key=lambda r: r["why"])
    out = ROOT / "data" / "real"
    out.mkdir(parents=True, exist_ok=True)
    head = json.dumps({"thread": thread, "seed": seed, "dpi": DPI, "min_conf": MIN_CONF, "box_convention": "PDF points, origin top left of the displayed page",
                       "dataset": "govdocs1 (Digital Corpora), US government files", "skipped_pages": skipped}, separators=(",", ":"))[:-1]
    body = ",\n".join(json.dumps(i, separators=(",", ":"), ensure_ascii=False) for i in items)
    (out / f"{thread}.json").write_text(head + ',"items":[\n' + body + "\n]}\n", encoding="utf-8")
    px = sum(len(r["words"]) for i in items for r in i["regions"] if r["why"] == "pixels")
    gb = sum(len(r["words"]) for i in items for r in i["regions"] if r["why"] == "garbled")
    un = [i for i in items if any(r["why"] == "untrusted" for r in i["regions"])]
    print(f"{thread}: {len(pdfs)} PDFs, {len(items)} pages picked ({sum(i['kind'] == 'real_marks' for i in items)} with images or drawings); "
          f"{sum(len(i['file_words']) for i in items)} file words, {px} pixel words, {gb} garbled words; "
          f"{len(un)} pages with an untrusted text layer ({sum(len(r['words']) for i in un for r in i['regions'])} OCR words); skipped {skipped}")


if __name__ == "__main__":
    main()
