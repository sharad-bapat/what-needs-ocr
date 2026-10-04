"""Score routing on the constructed set, without any OCR.

For each case, router-cli's `ocr` routes are compared with the manifest's truth regions:

  found       a truth word is found when its centre lies inside an ocr route (a truth box has margins
              with nothing in them, so words, not area, are counted); a region is routed when at least
              90% of its words are found
  wrong       a region that should get no OCR (a text layer already there, a photo, a logo, a blank
              sheet) is wrongly routed when ocr routes cover at least half its area; on an untouched
              page, any ocr route at all is wrong
  cost        the share of page area inside ocr routes, against the share inside truth regions that
              need OCR
  precision   an ocr route is right when at least half of its area lies in a truth region that needs
              OCR, by confidence band
  source      a route outside every truth region that lies mostly on the source page's own drawings is
              counted apart: ContractNLI pages can draw outlined text of their own (o0078's header and
              logo are vector paths with no text layer), which the truth doesn't list

usage: python tools/score_route.py [--split=tune] [--worst=N]
Held-out data is refused unless tools/check_frozen.py passes.
"""
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import fitz

from check_frozen import require_frozen

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "router" / "target" / "release" / "router-cli.exe"
SET = ROOT / "data" / "constructed"


def inside(x, y, b):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def overlap(a, b):
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def covered(box, routes, step=1.0):
    """Share of box under the union of routes, on a grid of `step` points."""
    n = hit = 0
    y = box[1] + step / 2
    while y < box[3]:
        x = box[0] + step / 2
        while x < box[2]:
            n += 1
            hit += any(inside(x, y, r) for r in routes)
            x += step
        y += step
    return hit / n if n else 0.0


def main():
    opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    split, worst = opt.get("split", "tune"), int(opt.get("worst", 8))
    if split != "tune":
        require_frozen()
    man = json.loads((SET / "manifest.json").read_text(encoding="utf-8"))
    items = [i for i in man["items"] if i["split"] == split]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(str((SET / i["file"]).resolve()).replace("\\", "/") for i in items))
        lst = f.name
    out = subprocess.run([str(CLI), "--list", lst], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    Path(lst).unlink()
    routes_of = {Path(d["file"]).name: d for d in map(json.loads, out.splitlines())}

    words, found = Counter(), Counter()
    regions, routed = Counter(), Counter()
    wrong, cases = Counter(), Counter()
    page_area = cost = need = 0.0
    bands = defaultdict(lambda: [0, 0])
    on_source = Counter()
    by_source = Counter()
    misses = []
    for it in items:
        d = routes_of[Path(it["file"]).name]
        page = d["pages"][0]
        ocr = [[r["x0"], r["y0"], r["x1"], r["y1"]] for r in page["routes"] if r["decision"] == "ocr"]
        kind = it["kind"]
        cases[kind] += 1
        pa = page["width"] * page["height"]
        page_area += pa
        cost += pa * covered([0, 0, page["width"], page["height"]], ocr, step=4.0) if ocr else 0.0
        truth_ocr = [r["box"] for r in it["regions"] if r["expect"] == "ocr"]
        truth_all = [r["box"] for r in it["regions"]]
        with fitz.open(SET / it["file"]) as doc:
            drawings = [list(dr["rect"]) for dr in doc[0].get_drawings()]
        drawings = [g for g in drawings if not any(overlap(g, t) >= 0.5 * max(area(g), 1e-9) for t in truth_all)]
        source = lambda b: sum(overlap(b, g) for g in drawings) >= 0.5 * area(b)
        kept = []
        for b in ocr:
            if not any(overlap(b, t) >= 0.5 * area(b) for t in truth_ocr) and source(b):
                on_source[kind] += 1
            else:
                kept.append(b)
        ocr = kept
        need += sum(area(b) for b in truth_ocr)
        for r in page["routes"]:
            if r["decision"] != "ocr":
                continue
            by_source[r["source"]] += 1
            b = [r["x0"], r["y0"], r["x1"], r["y1"]]
            ok = any(overlap(b, t) >= 0.5 * area(b) for t in truth_ocr)
            if not ok and source(b):
                continue
            band = "0.9 and up" if r["confidence"] >= 0.9 else "0.4 to 0.9"
            bands[band][0] += 1
            bands[band][1] += ok
        if kind == "control":
            wrong[kind] += bool(ocr)
            continue
        for reg in it["regions"]:
            if reg["expect"] == "ocr":
                ws = [w for w in reg["words"]]
                n = sum(1 for w in ws if any(inside((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, r) for r in ocr))
                words[kind] += len(ws)
                found[kind] += n
                regions[kind] += 1
                ok = n >= 0.9 * len(ws)
                routed[kind] += ok
                if not ok:
                    misses.append((n / max(len(ws), 1), it["id"], kind, it.get("wrap"), len(ws)))
            else:
                bad = covered(reg["box"], ocr) >= 0.5
                wrong[kind] += bad
                if bad:
                    misses.append((0.0, it["id"], kind, it.get("wrap"), 0))

    print(f"routing on the {split} split: {len(items)} cases")
    print(f"{'kind':<10} {'cases':>5}  words found        regions routed")
    for k in ("text", "full_scan", "outlined", "garbled"):
        print(f"{k:<10} {cases[k]:>5}  {found[k]:>6} of {words[k]:<6} {100 * found[k] / max(words[k], 1):5.1f}%  {routed[k]:>3} of {regions[k]}")
    tw, tf = sum(words.values()), sum(found.values())
    print(f"{'all':<10} {sum(cases[k] for k in ('text', 'full_scan', 'outlined', 'garbled')):>5}  {tf:>6} of {tw:<6} {100 * tf / max(tw, 1):5.1f}%  {sum(routed.values()):>3} of {sum(regions.values())}")
    print("wrongly sent to OCR: " + ", ".join(f"{k} {wrong[k]} of {cases[k]}" for k in ("text_ocr", "photo", "logo", "blank", "control")))
    print(f"routes on the source pages' own drawings (left out above): {sum(on_source.values())}, " + ", ".join(f"{k} {v}" for k, v in sorted(on_source.items())))
    print(f"page area sent to OCR {100 * cost / page_area:.1f}%, area that needs it {100 * need / page_area:.1f}%")
    print("ocr routes by source: " + ", ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    print("precision by confidence: " + ", ".join(f"{b}: {v[1]} of {v[0]} right ({100 * v[1] / max(v[0], 1):.1f}%)" for b, v in sorted(bands.items())))
    print(f"worst {worst}:")
    for m in sorted(misses)[:worst]:
        print(f"  {m[1]} {m[2]} wrap {m[3]}: {100 * m[0]:.0f}% of {m[4]} words found" if m[2] in words else f"  {m[1]} {m[2]} wrap {m[3]}: wrongly routed")


if __name__ == "__main__":
    main()
