# The constructed OCR set

tools/build_ocr_set.py builds 600 one-page PDFs from ContractNLI's digital NDAs (CC BY 4.0), half tune and half held-out, split by a hash of the source file (the same split as where-are-the-regions' constructed set, so its held-out sources are held out here too). The PDFs are rebuilt from the sources and aren't committed; data/constructed/manifest.json is, with each file's sha256. Two builds of 40 cases gave byte-identical manifests, and so byte-identical files.

Per split, 300 pages:

| Kind | Pages | What OCR should find |
|---|---|---|
| text: a rasterised text crop pasted in, from a stamp-sized 2% of the page to half of it | 120 | the crop's words |
| text_ocr: the same with Tesseract's invisible text layer on it | 30 | nothing new (a control) |
| full_scan: the whole page rasterised, image only | 30 | every word |
| outlined: a crop's words redrawn as glyph outlines, one filled path per letter | 30 | the crop's words |
| garbled: a crop's words redrawn as Helvetica text whose ToUnicode map is garbage | 30 | the crop's words |
| photo, logo, blank: an image with no text pasted in | 15 each | nothing |
| control: the page as it was | 15 | nothing |

Tune has 36,837 truth words in its regions and 105,277 words of the files' own text; held-out has 38,238 and 107,654.

Outlined text uses Vera (the font reportlab ships) through fontTools; garbled text is PyMuPDF's Helvetica with a ToUnicode map that sends every code to a private-use character or to a control character, chosen per case. PyMuPDF 1.24.9 ignores ToUnicode entries that map to control characters and falls back to the font's encoding, so it reads the control-character pages as clean text (wordbox's results/chunk4-reference-dev.txt notes the same); wordbox and where-are-the-regions read the control characters the file gives. A baseline built on PyMuPDF's text will get those words right without OCR.

The pasted region is usually a small part of a page, so a garbled region doesn't make the page's verdict garbled: on a 40-case trial build, case o0029's page was `text` to both wordbox and where-are-the-regions, with 267 of its 829 words holding control characters. Routing has to judge each region, not the page.

## How the truth was checked

A region's truth is the source page's words that lie wholly inside the crop, scaled to the pasted box and turned by the scan's rotation; for outlined and garbled text, the line-height box of each word as redrawn. tools/check_truth.py renders each region from the built page at 300 dpi, runs Tesseract 5.4.0 over it, and looks for each truth word among Tesseract's words, by text (letters and digits, any case) and by centre. All 240 tune cases with truth words:

| Kind | Truth words | Same text found | Of those, centre within 3 pt |
|---|---|---|---|
| text | 14,754 | 99.3% | 99.1% |
| text_ocr | 3,583 | 99.6% | 99.3% |
| full_scan | 11,107 | 98.7% | 99.2% |
| outlined | 3,099 | 98.6% | 99.8% |
| garbled | 4,189 | 98.9% | 99.7% |
| all | 36,732 | 99.1% | 99.3% |

The misses within 3 pt are a box convention, not a placement error. On an early 32-case build, all but one of the 17 misses were within 0.3 pt along x and 3.0 to 3.4 pt low along y, and none grew with the distance from the crop's centre: words with descenders and no ascenders ("any", "way", "agrees"), where Tesseract's tight box sits lower than PyMuPDF's line-height box. The scorer will have to allow for that, for example by counting a word as found when its centre is inside the truth box.
