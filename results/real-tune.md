# The pipeline on real pages: govdocs1 005 (tune)

668 pages from 262 files of govdocs1 thread 005, each with a usable text layer, 442 of them with images or drawings (data/real/005.json, tools/build_real.py, checked by eye in results/real-reference-check.md). The truth is a reference made without the router, so every number here is agreement with it, not accuracy: Tesseract at 400 dpi is careful, not right, and the reference misses many small labels on maps and charts, where the pipeline's extra words count against it.

tools/ocr_crops.py --real=005 OCR'd the routed crops and, back to back, every whole page; tools/score_ocr.py --real=005 scored both, and the file's text alone.

## After tuning

| Method | Recall | Precision | Word error | Recall of pixel-only words | Page area OCR'd | Megapixels | Tesseract calls | Tesseract seconds |
|---|---|---|---|---|---|---|---|---|
| routed (the pipeline) | 99.15% | 99.36% | 1.44% | 77.42% | 2.22% | 157.0 | 395 | 148 |
| every page | 96.71% | 96.62% | 6.38% | 91.30% | 98.43% | 5,557.3 | 668 | 1,895 |
| file text | 98.59% | 99.84% | 1.55% | 6.38% | 0.00% | 0.0 | 0 | 0 |

Skip-text is the file's text on these pages, which all have a usable layer (one page had no word regions reads, and was OCR'd whole). By kind: pages with images or drawings, routed 98.79% recall and 2.09% word error against every-page's 95.66% and 8.23%; plain pages, 99.84% and 0.20% against 98.73% and 2.81%.

The plan's target for real pages, fixed before any held-out run, is at least 70% less page area sent to OCR than OCR'ing every page, with no more than a point more word error. On 005 the pipeline OCRs 2.22% of the area against 98.43%, and its word error is lower (1.44% against 6.38%): it keeps the file's own words, which are exact, where every-page reads them again and misreads some.

## Tuning

| Run | Recall of pixel-only words | Word error | Page area | Tesseract seconds |
|---|---|---|---|---|
| First (chunk 3's router, crops at 150 to 400 dpi) | 74.03% | 1.32% | 1.40% | 115 |
| After tuning | 77.42% | 1.44% | 2.22% | 148 |

Three changes, each found by sorting the missed reference words by what the router put where they are:

1. Vector clusters of any kind with at least 3 letter-shaped paths in word-like runs are OCR'd whole (router LETTERS). 005945 p12 draws a chart in 5,214 paths whose labels ("ACE-FTS", "HALOE") are letter outlines inside a cluster regions calls a chart, and 005934 p15 has two tables of 418 and 446 letter paths; only clusters regions called outlined text were routed before.
2. Images are cropped at 300 dpi at least (ocr_crops DPI_RANGE, was 150): Tesseract reads small type better scaled up, as the constructed set's full scans already showed.
3. An image is OCR'd from a confidence of 0.1 (router CUT, was 0.4). Six skipped images whose pixels showed some text sat between 0.15 and 0.33; every photo, logo and blank sheet of the constructed set sits at 0.05.

On the constructed tune split the same changes leave routing as it was (no negative sent to OCR) and move the whole pipeline from 99.75% to 99.77% recall and 0.45% to 0.47% word error (results/score-tune.md).

## What's still missed

464 reference words, by what's there:

| Where | Words | Why |
|---|---|---|
| No route | 181 | mostly letters drawn as outlines in vertical axis titles ("Latitude"): regions finds letters only in horizontal runs |
| Routed and OCR'd, the crop's OCR found less | 179 | photos with text over them (005764 p4 has 43), maps, chart ticks, 40 of them in vector crops; the reference read the whole page at 400 dpi |
| Images skipped | 85 | logos and graphics with letters whose has-text is regions' floor of 0.05, the same as the constructed set's logos without any |
| Garbled crops and OCR layers already there | 19 | bullets read as "e", OCR layers whose words differ from the reference's |

Every one of these is a limit of the page map's kinds (where-are-the-regions), not of the routing rules, and none was chased further on tune data: the reference is an agreement measure, and fitting the router to it would make the held-out run say less.
