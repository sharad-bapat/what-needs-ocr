# The pipeline against the baselines, tune split

tools/score_ocr.py scores four word lists per page on the 300 tune cases, against each case's whole truth (its file words and its regions' words). Matching and the measures are described in the script: words compare by letters and digits only, recall is one to one at the truth word's place, reads of words the crop edge cut are set aside, and word error compares bags of words page by page. All OCR is Tesseract v5.4.0.20240606 with the same settings (`-l eng --psm 3`, one thread per call, 4 calls at a time); the routed crops and the whole pages were read back to back in one session, so their seconds compare.

| Method | Recall | Precision | Word error | Recall in regions that need OCR | Page area OCR'd | Megapixels | Tesseract calls | Tesseract seconds |
|---|---|---|---|---|---|---|---|---|
| routed (the pipeline) | 99.75% | 99.80% | 0.45% | 99.06% | 21.64% | 378.0 | 440 | 276 |
| every page | 98.09% | 99.19% | 2.66% | 98.82% | 100.00% | 2,562.3 | 300 | 951 |
| skip text | 84.32% | 99.89% | 15.76% | 33.15% | 9.95% | 255.1 | 30 | 85 |
| file text | 76.57% | 99.96% | 23.46% | 0.00% | 0.00% | 0.0 | 0 | 0 |

Recall and word error by kind:

| Kind | routed | every page | skip text | file text |
|---|---|---|---|---|
| text | 99.79%, 0.42% | 97.10%, 3.72% | 75.37%, 24.65% | 75.37%, 24.65% |
| text_ocr | 99.92%, 0.16% | 97.61%, 3.26% | 99.92%, 0.16% | 99.92%, 0.16% |
| full_scan | 98.69%, 2.18% | 99.14%, 1.64% | 99.14%, 1.64% | 0.00%, 100.00% |
| outlined | 99.79%, 0.29% | 99.24%, 1.21% | 81.38%, 18.62% | 81.38%, 18.62% |
| garbled | 99.80%, 0.26% | 98.44%, 2.59% | 72.57%, 27.43% | 72.57%, 27.43% |
| photo | 99.74%, 0.76% | 99.15%, 1.65% | 99.74%, 0.52% | 99.74%, 0.52% |
| logo | 100.00%, 0.00% | 99.56%, 0.92% | 100.00%, 0.00% | 100.00%, 0.00% |
| blank | 100.00%, 0.00% | 99.27%, 1.18% | 100.00%, 0.00% | 100.00%, 0.00% |
| control | 100.00%, 0.17% | 99.40%, 1.05% | 100.00%, 0.00% | 100.00%, 0.00% |

The pipeline's word error is lower than OCR'ing every page: it keeps the file's own words, which are exact, and OCR's misreads of born-digital text (3.72% word error on the text pages) never enter. It sends 85% fewer pixels and spends 71% less Tesseract time. The one kind where it's behind is the full-page scan, read at the scan's own resolution (150 to 300 dpi here) where every-page reads at 300 dpi: 98.69% against 99.14%. Skip-text reads only the 30 full-page scans and misses everything pasted into pages that have text.

The plan's targets for the constructed held-out set, checked here on tune only: recall in regions that need OCR at least 98% (99.06%), and word error no worse than OCR'ing every page by more than a point (0.45% against 2.66%). Every timing above is a sum of each call's wall time with four running at once; the two OCR runs were made under the same load.
