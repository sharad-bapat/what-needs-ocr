# Held-out runs

The router, the tools and the set manifests were frozen at 9cef13b (results/frozen.sha256, with where-are-the-regions pinned at 57ef3a5), and tools/check_frozen.py passed before each run below. Each run was made once. The targets were fixed in the plan before any held-out data was used.

## 1. Routing on the constructed held-out split (4 October 2026)

python tools/score_route.py --split=heldout: 300 cases, none of them used in tuning.

| Kind | Cases | Truth words inside an ocr route | Regions with at least 90% |
|---|---|---|---|
| text | 120 | 15,026 of 15,026 (100.0%) | 120 of 120 |
| full_scan | 30 | 10,958 of 10,958 (100.0%) | 30 of 30 |
| outlined | 30 | 3,914 of 3,934 (99.5%) | 30 of 30 |
| garbled | 30 | 4,288 of 4,289 (100.0%) | 30 of 30 |
| all | 210 | 34,186 of 34,207 (99.9%) | 210 of 210 |

The target was at least 98% of the regions that hold text routed: all 210 are. None of the 30 already-OCR'd crops and none of the 45 photos, logos and blank sheets was sent to OCR. Routes cover 22.0% of the page area; the regions that need it cover 23.6%. Of the ocr routes at confidence 0.9 or more, 316 of 324 lie in a truth region (97.5%); the one between 0.4 and 0.9 does too.

Two of the 15 untouched pages got a route the scorer counts as wrong, and 11 routes fell on the source pages' own drawings and were counted apart. Looked at afterwards, by eye: o0359's footer ("Tel.: 91 504 61 41 ... 28009 Madrid - España") is letters drawn as outlines with no text layer under them, so the router is right and the truth doesn't list it, as with the outlined logos on o0119 ("thoughtbot") and o0439. o0199's two routes are a real mistake: two bullets stored as a private-use character (U+F0B7), the only two words in their font, sent to OCR as an undecodable layer. Each is a crop of about 4 by 11 pt.

## 2. The whole pipeline on the constructed held-out split (4 October 2026)

tools/ocr_crops.py --split=heldout OCR'd the routed crops and then, back to back, every whole page (results/ocr-heldout.jsonl, results/ocr-pages-heldout.jsonl); tools/score_ocr.py --split=heldout scored both and the two text-only baselines.

| Method | Recall | Precision | Word error | Recall in regions that need OCR | Page area OCR'd | Megapixels | Tesseract calls | Tesseract seconds |
|---|---|---|---|---|---|---|---|---|
| routed (the pipeline) | 99.70% | 99.80% | 0.49% | 99.06% | 21.95% | 584.5 | 336 | 299 |
| every page | 98.93% | 99.26% | 1.76% | 98.66% | 100.00% | 2,545.6 | 300 | 922 |
| skip text | 83.87% | 99.91% | 16.20% | 31.47% | 9.97% | 253.8 | 30 | 81 |
| file text | 76.49% | 99.97% | 23.52% | 0.00% | 0.00% | 0.0 | 0 | 0 |

Recall and word error by kind, routed against every page: text 99.84% and 0.31% against 98.94% and 1.96%; already-OCR'd crops 99.48% and 0.59% against 98.48% and 2.10%; full scans 98.61% and 2.09% for both; outlined text 99.63% and 0.71% against 98.93% and 1.57%; garbled text 99.74% and 0.38% against 98.96% and 1.48%; photos, logos, blank sheets and untouched pages 100.00%, 99.97% and word error 0.38% or less, against 99.00% to 99.64% and up to 1.79%.

The target was word error no more than a point worse than OCR'ing every page: the pipeline's is 1.27 points lower (0.49% against 1.76%), for 77% fewer pixels and 68% less Tesseract time. Full scans read exactly as well as with every-page OCR, both at 300 dpi now.

## 3. The whole pipeline on govdocs1 006 (4 October 2026)

636 pages from 235 files of thread 006, each with a usable text layer, 425 with images or drawings (data/real/006.json, built before any run and not looked at beyond its summary). The truth is the reference tools/build_real.py made without the router, so these numbers are agreement with it, not accuracy (results/real-reference-check.md: where the reference has a word it's right about 92% of the time, and it misses many small labels on maps and charts).

The first run of tools/ocr_crops.py --real=006 stopped with an error before writing anything: when the same crop came up twice in one run, two threads shared a cache entry and one read the other's half-written time file. The fix (149913b) reads each distinct crop once and writes the cache through temporary files; it changes no OCR word (the tune split's output from the cache was identical crop by crop, and only the time counted twice for duplicates went, 317 to 315 seconds). The source was relocked (230ef7e) and the run made again; the every-page run had finished under the old code, which has no duplicate crops to race on, and was kept.

| Method | Recall | Precision | Word error | Recall of pixel-only words | Page area OCR'd | Megapixels | Tesseract calls | Tesseract seconds |
|---|---|---|---|---|---|---|---|---|
| routed (the pipeline) | 99.19% | 98.64% | 2.09% | 78.18% | 5.50% | 342.5 | 243 | 118 |
| every page | 96.90% | 96.65% | 6.17% | 88.40% | 98.78% | 5,628.6 | 636 | 1,946 |
| skip text | 98.58% | 99.77% | 1.64% | 0.79% | 0.24% | 15.1 | 2 | 3 |
| file text | 98.53% | 99.77% | 1.68% | 0.69% | 0.00% | 0.0 | 0 | 0 |

By kind, routed against every page: pages with images or drawings 98.89% recall and 2.94% word error against 96.26% and 7.38%; plain pages 99.88% and 0.18% against 98.34% and 3.45%.

The target for real pages was at least 70% less page area sent to OCR than OCR'ing every page, with no more than a point more word error: the pipeline OCRs 5.50% of the area against 98.78% (94% less), and its word error is 4.08 points lower.

Against the file's text alone, the pipeline finds more of the reference (99.19% against 98.53%) but its word error is higher (2.09% against 1.68%; on 005 it was lower, 1.44% against 1.55%). The difference is the words OCR adds that the reference doesn't hold: 2,699 of them, 2,087 with a Tesseract confidence under 85 (1,554 under 60), where the reference keeps only words at 85 or more. The merged list carries each OCR word's confidence, so a user can cut there; a cutoff in the merge itself would be chosen on tune data and tested on new pages, not on these.
