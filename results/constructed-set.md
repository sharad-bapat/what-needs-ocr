# The constructed OCR set

tools/build_ocr_set.py builds 600 one-page PDFs from ContractNLI's digital NDAs (CC BY 4.0), half tune and half held-out, split by a hash of the source file (the same split as where-are-the-regions' constructed set, so its held-out sources are held out here too). The PDFs are rebuilt from the sources and aren't committed; data/constructed/manifest.json is, with each file's sha256. Two builds of 32 cases gave the same manifest and byte-identical files.

Per split: 152 pages with a rasterised text crop pasted in (from a stamp-sized 2% of the page to half of it), 38 with the same crop plus Tesseract's invisible text layer (already OCR'd, a control), 38 full-page scans, 18 each with a photo, a logo or a blank scanned sheet pasted in (no text), and 18 left as they were. Tune has 35,415 truth words in its regions and 96,572 words of the files' own text; held-out has 40,914 and 103,936.

## How the truth was checked

A region's truth is the source page's words that lie wholly inside the crop, scaled to the pasted box and turned by the scan's rotation. tools/check_truth.py renders each such region from the built page at 300 dpi, runs Tesseract 5.4.0 over it, and looks for each truth word among Tesseract's words, by text and by centre. On 60 tune cases (9,327 truth words), Tesseract read the same text for 99.0% of them, and 98.3% of those were within 3 pt of the truth box.

The misses within that are a box convention, not a placement error. On the first 8 cases, all but one of the 17 misses were within 0.3 pt along x and 3.0 to 3.4 pt low along y, and none grew with the distance from the crop's centre: words with descenders and no ascenders ("any", "way", "agrees"), where Tesseract's tight box sits lower than PyMuPDF's line-height box. The scorer will have to allow for that, for example by counting a word as found when its centre is inside the truth box.
