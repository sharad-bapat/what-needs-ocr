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

## A page floor (5 October 2026)

After the fix above, the router ran over all 478 files of the Sodir sample (43,045 pages, 83% of them scans). 695 scanned pages still had every image skipped. Of a random 24 checked by eye, 14 held printed text: 10 sparse section headings ("SECTION A GEOLOGY", "4.7 Bit record"), a contents page, two dense tables and a table scanned sideways. One was handwriting, 3 were charts with axis labels and 6 were log strips or near-blank. Skipping such a page loses it whole, while reading a blank scan costs one OCR call that finds nothing.

So a page with no text of its own (no word the file draws, an invisible OCR layer included) and nothing routed now has its largest image read when that image covers at least half the page (`FLOOR`, router/src/route.rs `page_floor`). The route keeps its own confidence and gains the reason `page_floor`. The rule was set from the Sodir sample, not tuned on any test set.

All 24 sampled pages get a floor route, and Tesseract reads them: "SECTION A GEOLOGY", the contents page, the depth table, "4.7 Bit record". Every constructed and govdocs1 page has text of its own, so the floor can't fire there: routing on the constructed tune and held-out splits is unchanged (the same numbers as results/routing-tune.md and results/heldout.md), and the real-page results stand. Relocked at where-are-the-regions 8774fff.

## Faster thumbnails (5 October 2026)

where-are-the-regions now indexes a file once for all its thumbnails and averages one-component images through a table (62c1645, its results/speed.md); `route_page` takes that indexed file (`pixels::Source`). The output is the same: on 15 Sodir files, 1,469 of 1,493 pages give identical routes and the other 24 differ only by the page floor, which those runs predate. The router took 39 s on those files, against 188 s. Relocked at where-are-the-regions 62c1645; held-out routing is unchanged.

## Has-text on scanned reports (5 October 2026)

where-are-the-regions' kind layer changed for scanned reports (78d5f50, its results/kinds-sparse.md): polarity chosen by glyph count on images about half dark, wider thumbnails for long thin images, sideways text counted, and has-text on nearly empty pages with a heading. Its own held-out run found 149 of 157 Sodir pages with text, against 40, and held 9 more images without text on govdocs1 004. The router takes the new has-text as it is. Relocked at 78d5f50. Routing on the constructed tune and held-out splits is unchanged; the real-page OCR runs (005 to 007) weren't repeated.
