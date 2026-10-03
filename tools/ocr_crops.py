"""OCR the routes: crop every `ocr` route router-cli gives and read it with Tesseract, caching each result.

For each route, the page is rendered with PyMuPDF over the route's box and 6 pt round it, in grey: an image route at
the image's own resolution (its dpi from the router, kept between 150 and 400), outlined and garbled text
at 300 dpi. Tesseract reads the crop (TSV output, one word per line with its box and confidence), and the
words' boxes are mapped back to points on the page as displayed (after /Rotate, like the router's).
Tesseract runs with OMP_THREAD_LIMIT=1, so the same crop always gives the same words, and its TSV is
cached under data/ocr-cache by a hash of the crop's PNG and the Tesseract settings: a rerun that renders
the same crops calls Tesseract for none of them.

Output, one JSON line per file:
  {"file": ..., "pages": [{"n": 1, "crops": [{"route": 0, "source": "image", "box": [x0, y0, x1, y1],
    "dpi": 200, "px": [w, h], "cache": "<hash>", "words": [[x0, y0, x1, y1, "text", conf], ...]}]}]}

usage: python tools/ocr_crops.py <list.txt> --out=<file.jsonl> [--jobs=4]
       python tools/ocr_crops.py --split=tune --out=<file.jsonl> [--jobs=4]    the constructed set's split
Held-out cases are refused until the router is frozen.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
from rich.progress import MofNCompleteColumn, Progress, TimeElapsedColumn

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "router" / "target" / "release" / "router-cli.exe"
CACHE = ROOT / "data" / "ocr-cache"
SET = ROOT / "data" / "constructed"
ARGS = ["-l", "eng", "--psm", "3"]
TEXT_DPI = 300
# white space added round each crop, in points: Tesseract finds little on a crop cut tight to its letters
PAD = 6
DPI_RANGE = (150, 400)


def tesseract_version():
    out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout
    return out.split("\n", 1)[0].strip()


def routes_of(files):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(str(Path(p).resolve()).replace("\\", "/") for p in files))
        lst = f.name
    out = subprocess.run([str(CLI), "--list", lst], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    Path(lst).unlink()
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def crop(page, box, dpi):
    """The route's box rendered in grey at dpi, and where the crop's top-left pixel sits on the displayed
    page, in pixels at that dpi."""
    clip = (fitz.Rect(box[0] - PAD, box[1] - PAD, box[2] + PAD, box[3] + PAD) * page.derotation_matrix) & page.rect
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png"), pix.width, pix.height, pix.x, pix.y


def read(png, dpi, key):
    """Tesseract's TSV for the crop, from the cache when it's there."""
    path = CACHE / f"{key}.tsv"
    if path.exists():
        return path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "c.png"
        img.write_bytes(png)
        env = dict(os.environ, OMP_THREAD_LIMIT="1")
        tsv = subprocess.run(["tesseract", str(img), "stdout", "--dpi", str(dpi), *ARGS, "tsv"], capture_output=True,
                             text=True, encoding="utf-8", env=env, check=True).stdout
    path.write_text(tsv, encoding="utf-8")
    return tsv


def words_of(tsv, ox, oy, dpi):
    """Word lines of Tesseract's TSV, their pixel boxes moved to points on the displayed page."""
    s = 72 / dpi
    out = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) == 12 and f[0] == "5" and f[11].strip():
            x, y, w, h = (int(v) for v in f[6:10])
            out.append([round((ox + x) * s, 2), round((oy + y) * s, 2), round((ox + x + w) * s, 2), round((oy + y + h) * s, 2),
                        f[11], round(float(f[10]), 1)])
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if "out" not in opt or (not args and "split" not in opt):
        sys.exit(__doc__)
    if "split" in opt:
        if opt["split"] != "tune":
            sys.exit("held-out cases are refused until the router is frozen")
        man = json.loads((SET / "manifest.json").read_text(encoding="utf-8"))
        files = [SET / i["file"] for i in man["items"] if i["split"] == opt["split"]]
    else:
        files = [Path(l.strip()) for l in open(args[0], encoding="utf-8") if l.strip()]
    CACHE.mkdir(parents=True, exist_ok=True)
    version = tesseract_version()
    settings = "|".join([version, *ARGS]).encode()

    # render every crop first (cheap), then read the ones not cached, several at a time
    jobs, rows = [], []
    for d in routes_of(files):
        row = {"file": d["file"], "pages": []}
        rows.append(row)
        if d.get("status") != "ok":
            row["status"] = d.get("status")
            continue
        with fitz.open(d["file"]) as doc:
            for p in d["pages"]:
                crops = []
                for i, r in enumerate(p["routes"]):
                    if r["decision"] != "ocr":
                        continue
                    dpi = round(min(max(r["dpi"], DPI_RANGE[0]), DPI_RANGE[1])) if r["source"] == "image" else TEXT_DPI
                    box = [r["x0"], r["y0"], r["x1"], r["y1"]]
                    png, w, h, ox, oy = crop(doc[p["n"] - 1], box, dpi)
                    key = hashlib.sha256(png + b"|" + settings + b"|" + str(dpi).encode()).hexdigest()[:24]
                    c = {"route": i, "source": r["source"], "box": box, "dpi": dpi, "px": [w, h], "cache": key}
                    crops.append(c)
                    jobs.append((c, png, ox, oy))
                row["pages"].append({"n": p["n"], "crops": crops})
    cached = sum(1 for c, *_ in jobs if (CACHE / f"{c['cache']}.tsv").exists())
    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn(), transient=True) as bar:
        task = bar.add_task("tesseract", total=len(jobs))

        def one(job):
            c, png, ox, oy = job
            c["words"] = words_of(read(png, c["dpi"], c["cache"]), ox, oy, c["dpi"])
            bar.advance(task)

        with ThreadPoolExecutor(max_workers=int(opt.get("jobs", 4))) as pool:
            list(pool.map(one, jobs))
    Path(opt["out"]).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    words = sum(len(c["words"]) for c, *_ in jobs)
    print(f"{len(rows)} files, {len(jobs)} crops ({cached} from the cache), {words} words; {version}, {' '.join(ARGS)}")


if __name__ == "__main__":
    main()
