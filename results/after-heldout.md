# Changes after the held-out runs

The held-out results in results/heldout.md are the frozen pipeline's and stay as they are. Each change below was made later, chosen on tune data only, relocked (results/frozen.sha256, tools/check_frozen.py), and measured apart.

## An OCR-confidence cutoff in the merge (4 October 2026)

On govdocs1 006 the pipeline's word error was higher than the file's text alone (2.09% against 1.68%), and most of the OCR words that matched nothing in the reference had a Tesseract confidence under 85 (2,087 of 2,699, 1,554 under 60). The merge now leaves out OCR words under a confidence of 0.5 (router/src/merge.rs MIN_CONF; router-cli --merge ... --min-conf 0 keeps them all).

The cutoff was chosen by a rule written before any test: the lowest summed word error over the constructed tune split (exact truth) and govdocs1 005 (agreement with its reference), keeping the constructed region recall at 98% or more.

| Cutoff | Constructed tune: word error | Region recall | govdocs1 005: word error | Pixel-only words found |
|---|---|---|---|---|
| none | 0.47% | 99.18% | 1.44% | 77.42% |
| 0.3 | 0.42% | 99.03% | 1.33% | 77.08% |
| 0.5 | 0.45% | 98.80% | 1.25% | 76.84% |
| 0.6 | 0.49% | 98.60% | 1.22% | 76.55% |
| 0.7 | 0.56% | 98.27% | 1.19% | 76.11% |
| 0.8 | 0.67% | 97.75% | 1.15% | 75.39% |
| 0.85 | 0.78% | 97.26% | 1.14% | 74.85% |
| 0.9 | 1.03% | 96.16% | 1.13% | 72.34% |

On the constructed set a low cutoff drops junk and a high one starts dropping true words that Tesseract was unsure of; on 005 the word error keeps falling as the cutoff rises, partly because the reference itself keeps only words at 85 or more. 0.5 has the lowest sum (1.70).

006 has been used, so the cutoff is tested once on fresh pages, govdocs1 thread 007, built and scored the same way (below).

### The test on govdocs1 007 (4 October 2026)

613 pages from 231 files of thread 007, each with a usable text layer, 404 with images or drawings (data/real/007.json, built the same way as 005 and 006 and committed and pinned before any run). As before, the numbers are agreement with the reference, not accuracy.

| Method | Recall | Precision | Word error | Recall of pixel-only words | Page area OCR'd | Megapixels | Tesseract calls | Tesseract seconds |
|---|---|---|---|---|---|---|---|---|
| routed, cutoff 0.5 | 98.97% | 99.56% | 1.42% | 83.60% | 2.35% | 166.6 | 315 | 92 |
| routed, no cutoff | 98.98% | 99.31% | 1.65% | 83.87% | 2.35% | 166.6 | 315 | 92 |
| every page | 96.12% | 96.77% | 6.90% | 91.91% | 98.25% | 5,150.0 | 613 | 1,738 |
| file text | 98.32% | 99.82% | 1.85% | 9.56% | 0.00% | 0.0 | 0 | 0 |

The cutoff lowers the word error from 1.65% to 1.42% for 0.01 points of recall, and with it the pipeline's word error is lower than the file's text alone (1.42% against 1.85%), where on 006 without it it was higher. Against OCR'ing every page it OCRs 2.35% of the area against 98.25% and its word error is 5.48 points lower, the plan's real-page target met again on pages no choice was made on.

## Images read as they show on the page (5 October 2026)

where-are-the-regions' kind layer read each image as stored, not as shown, so a scan stored on its side and turned by the page's /Rotate was called a graphic with no text, and the router skipped it. On the first 10 files of a sample of scanned well reports from the Norwegian Offshore Directorate, 323 of 1,105 image regions were skipped. The fix is in where-are-the-regions (8019e6d, its results/kinds-turn.md); the router now takes thumbnails from `pixels::placed_thumbnail`. On the same 10 files, 17 regions are skipped.

Relocked at where-are-the-regions 8019e6d. Routing on the constructed held-out split (tools/score_route.py --split=heldout) gives the same numbers as results/heldout.md: 210 of 210 regions routed, none of the 45 photos, logos and blank sheets sent to OCR, 22.0% of the page area against 23.6% that needs it, and 316 of 324 routes at 0.9 or more right. The OCR runs weren't repeated.
