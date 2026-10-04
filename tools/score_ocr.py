"""Score the whole pipeline's word lists on the constructed set, against three baselines.

Each method gives one word list per page:

  routed      the pipeline: router-cli --merge with results/ocr-<split>.jsonl (the file's own words, and
              Tesseract's words in the routed crops)
  every page  Tesseract over each whole page (results/ocr-pages-<split>.jsonl), the file's text ignored,
              as OCR'ing every page does (ocrmypdf --force-ocr)
  skip text   the file's own words on a page that has any, Tesseract over the whole page on one that has
              none, as ocrmypdf --skip-text does
  file text   the file's own words alone (router-cli --merge with no OCR results)

Words are compared by their letters and digits, any case (punctuation and underscores dropped; a word
with none is ignored). The truth is the case's file words plus every region's words.

  recall      truth words found at their place: matched one to one with an output word of the same text
              whose centre lies in the truth word's box (1 pt of slack across, 2 pt up and down; Tesseract's
              boxes are tight, the truth's are line high)
  precision   output words that matched, out of all output words except the reads of words the crop edge
              cut, which are set aside (part of each shows, so a read is neither right nor wrong)
  word error  per page, truth words missing plus output words extra, as bags of words (reading order
              isn't part of this), over the truth words; summed over pages
  region      the recall of the words in regions that need OCR alone
  cost        page area OCR'd (the routes' boxes), Megapixels sent, Tesseract calls and seconds

On the real set (--real), the truth is the thread's reference (tools/build_real.py), so the numbers are
agreement with it, not accuracy; there are no cut words, and every picked page has a usable text layer,
so "skip text" is the file's text there.

usage: python tools/score_ocr.py [--split=tune]
       python tools/score_ocr.py --real=005 --root=<govdocs1 dir>
Held-out data is refused unless tools/check_frozen.py passes.
"""
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from check_frozen import require_frozen

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "router" / "target" / "release" / "router-cli.exe"
SET = ROOT / "data" / "constructed"
METHODS = ["routed", "every page", "skip text", "file text"]
MIN_CONF = []  # ["--min-conf", "<x>"] from --min-conf=<x>: the merge's OCR-confidence cutoff, for the routed list


def norm(s):
    return re.sub(r"[^0-9a-z]", "", s.lower())


def centre(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def near(t, c):
    return t[0] - 1 <= c[0] <= t[2] + 1 and t[1] - 2 <= c[1] <= t[3] + 2


def merged(files, ocr):
    """router-cli --merge over the files: per (file name, page number), the page's words as (box, text)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(str(p.resolve()).replace("\\", "/") for p in files))
        lst = f.name
    out = subprocess.run([str(CLI), "--merge", str(ocr), *MIN_CONF, "--list", lst], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    Path(lst).unlink()
    res = {}
    for d in map(json.loads, out.splitlines()):
        for p in d.get("pages", []):
            res[(Path(d["file"]).name, p["n"])] = [([w["x0"], w["y0"], w["x1"], w["y1"]], w["t"]) for w in p["words"]]
    return res


def ocr_results(path):
    """An OCR results file: per (file name, page number), (the page's crops, their words as (box, text))."""
    res = {}
    for d in map(json.loads, open(path, encoding="utf-8")):
        for p in d.get("pages", []):
            res[(Path(d["file"]).name, p["n"])] = (p["crops"], [(w[:4], w[4]) for c in p["crops"] for w in c["words"]])
    return res


def score(truth, region_ids, cuts, out):
    """One page: (truth words, matched, region words, region matched, output words counted, missing, extra)."""
    T = [(t[:4], norm(t[4]), i) for i, t in enumerate(truth) if norm(t[4])]
    O = [(b, norm(s)) for b, s in out if norm(s)]
    used = [False] * len(O)
    matched = set()
    for tb, tt, i in T:
        tc = centre(tb)
        best = None
        for j, (ob, ot) in enumerate(O):
            if used[j] or ot != tt or not near(tb, centre(ob)):
                continue
            d = abs(centre(ob)[0] - tc[0]) + abs(centre(ob)[1] - tc[1])
            if best is None or d < best[0]:
                best = (d, j)
        if best:
            used[best[1]] = True
            matched.add(i)
    aside = {j for j, (ob, ot) in enumerate(O) if not used[j] and any(near(c, centre(ob)) for c in cuts)}
    kept = [ot for j, (ob, ot) in enumerate(O) if j not in aside]
    tb, ob = Counter(t[1] for t in T), Counter(kept)
    missing = sum(max(0, n - ob[w]) for w, n in tb.items())
    extra = sum(max(0, n - tb[w]) for w, n in ob.items())
    reg = [t for t in T if t[2] in region_ids]
    return len(T), len(matched), len(reg), sum(1 for t in reg if t[2] in matched), len(kept), missing, extra


def area_share(boxes, w, h, step=4.0):
    if not boxes:
        return 0.0
    n = hit = 0
    y = step / 2
    while y < h:
        x = step / 2
        while x < w:
            n += 1
            hit += any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)
            x += step
        y += step
    return hit / n


def main():
    opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if "min-conf" in opt:
        MIN_CONF[:] = ["--min-conf", opt["min-conf"]]
    if "real" in opt:
        # the real set: one thread's picked pages, against its reference (data/real/<thread>.json)
        thread, root = opt["real"], Path(opt["root"])
        man = json.loads((ROOT / "data" / "real" / f"{thread}.json").read_text(encoding="utf-8"))
        split, items = man["items"][0]["split"] if man["items"] else "tune", man["items"]
        if split != "tune":
            require_frozen()
        files = sorted({root / i["file"] for i in items})
        path_of = lambda i: root / i["file"]
        label = f"govdocs1 {thread} ({split}), agreement with the reference"
        tag = f"real-{thread}"
    else:
        split = opt.get("split", "tune")
        if split != "tune":
            require_frozen()
        items = [i for i in json.loads((SET / "manifest.json").read_text(encoding="utf-8"))["items"] if i["split"] == split]
        files = [SET / i["file"] for i in items]
        path_of = lambda i: SET / i["file"]
        label = f"{split} split"
        tag = split
    routed_ocr, pages_ocr = ROOT / "results" / f"ocr-{tag}.jsonl", ROOT / "results" / f"ocr-pages-{tag}.jsonl"
    routed = merged(files, routed_ocr)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        empty = f.name
    file_only = merged(files, empty)
    Path(empty).unlink()
    crops, pages = ocr_results(routed_ocr), ocr_results(pages_ocr)

    tot = {m: defaultdict(Counter) for m in METHODS}
    cost = {m: Counter() for m in METHODS}
    for it in items:
        name = (path_of(it).name, it.get("page", 1))
        truth, region_ids = list(it["file_words"]), set()
        for reg in it["regions"]:
            for wd in reg["words"]:
                if reg["expect"] == "ocr":
                    region_ids.add(len(truth))
                truth.append(wd)
        cuts = [c for r in it["regions"] for c in r.get("cut", [])]
        page_crops, page_words = pages.get(name, ([], []))
        has_text = bool(file_only[name])
        outs = {"routed": routed[name], "every page": page_words, "skip text": file_only[name] if has_text else page_words, "file text": file_only[name]}
        w, h = (it["width"], it["height"]) if "width" in it else (page_crops[0]["box"][2], page_crops[0]["box"][3])
        sent = {"routed": crops.get(name, ([], []))[0], "every page": page_crops, "skip text": [] if has_text else page_crops, "file text": []}
        for m in METHODS:
            r = score(truth, region_ids, cuts, outs[m])
            for k, key in enumerate(("truth", "found", "region", "region_found", "counted", "missing", "extra")):
                tot[m][it["kind"]][key] += r[k]
                tot[m]["all"][key] += r[k]
            cs = sent[m]
            cost[m]["area"] += area_share([c["box"] for c in cs], w, h) * w * h
            cost[m]["page_area"] += w * h
            cost[m]["px"] += sum(c["px"][0] * c["px"][1] for c in cs)
            cost[m]["calls"] += len(cs)
            cost[m]["secs"] += sum(c["secs"] for c in cs)

    pct = lambda a, b: f"{100 * a / b:.2f}%" if b else "-"
    print(f"{label}, {len(items)} pages")
    print(f"{'method':<11} {'recall':>8} {'precision':>9} {'word error':>10} {'region':>8}   {'area OCRd':>9} {'Mpx':>7} {'calls':>5} {'secs':>6}")
    for m in METHODS:
        a, c = tot[m]["all"], cost[m]
        print(f"{m:<11} {pct(a['found'], a['truth']):>8} {pct(a['found'], a['counted']):>9} {pct(a['missing'] + a['extra'], a['truth']):>10} "
              f"{pct(a['region_found'], a['region']):>8}   {pct(c['area'], c['page_area']):>9} {c['px'] / 1e6:7.1f} {c['calls']:>5} {c['secs']:6.0f}")
    print("\nrecall and word error by kind:")
    kinds = sorted(k for k in tot["routed"] if k != "all")
    print(f"{'kind':<10} " + " ".join(f"{m:>22}" for m in METHODS))
    for k in kinds:
        print(f"{k:<10} " + " ".join(f"{pct(tot[m][k]['found'], tot[m][k]['truth']):>10} {pct(tot[m][k]['missing'] + tot[m][k]['extra'], tot[m][k]['truth']):>11}" for m in METHODS))


if __name__ == "__main__":
    main()
