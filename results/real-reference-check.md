# Checking the real set's reference by eye

tools/build_real.py builds a reference word list for pages of govdocs1 thread 005 without the router: PyMuPDF's visible words that decode, plus the words Tesseract reads at 400 dpi that aren't on a file word (pixel words), plus OCR in place of a text layer that doesn't say what the page shows. The thread gives 668 pages from 262 files, 442 of them with images or drawings: 277,907 file words, 1,664 pixel words, 10 garbled words, and 2 pages whose layer is untrusted (394 OCR words). 804 pages had no usable text layer and aren't in the set.

tools/check_real.py draws a seeded sample of 20 pages that have reference OCR words, each word boxed on the page as displayed, and Claude looked at every sheet.

## What the checks changed

The reference was rebuilt four times before this count, each time after looking at sheets:

1. Removing the text layer by redaction and reading what was left, the first method, left text behind: on 005331 the whole body survived (500 words of the file's own text counted as pixel words), and on 005721 some words did. Replaced by reading the whole page and dropping OCR words that land on a file word.
2. At a confidence of 60, Tesseract's readings of chart and map marks came through ("tLe", "Oo", "=a" at 60 to 80, where real pixel text scored above 90). The cutoff is 85.
3. 005448's text layer decodes to ordinary Latin-1 letters and C1 control characters (",f", "¼,G") and passed as trusted text. C1 controls now count as undecodable (here and in the router), and a page whose layer disagrees with what OCR reads on it is untrusted, its reference being the OCR words. The first agreement rule flagged 5 good layers out of 7 (word breaks differ: "341 4," against "3414,"; map labels counted against the layer; and a page with /Rotate 270 was read sideways). The second rule compares only OCR words that land on file words and accepts a match inside the layer's text along the line; tested on the 7 flagged pages, the 13 with agreement between 0.5 and 0.8 and 30 random pages before use. Only 005448's two pages are untrusted now.
4. Pages are read turned so their own text runs left to right: 005530 (/Rotate 270) reads with /Rotate taken off, 005523 and 005944 (/Rotate 90) as displayed. Rendering a crop of a turned page needs the clip in that page's own frame; the pipeline's crop code had the same mistake for rotated pages and is fixed too (results/ocr-tune.jsonl is byte-identical afterwards, as the constructed pages aren't rotated). On the three pages, agreement went from 0.0 to 1.0, 0.998 and 0.998.

## The count

Reference words that are on the page and read right, by eye:

| Page | Right | What it is |
|---|---|---|
| 005013 p2 | 10 of 10 | labels in a process diagram |
| 005164 p1 | 7 of 7 | a USDA logo (3 of its words missed) |
| 005197 p1 | 7 of 7 | a refuge's name in an image |
| 005521 p1 | 3 of 3 | "Department of Justice" in blackletter |
| 005776 p1 | 6 of 6 | publisher logos ("Crop" missed) |
| 005157 p3 | 1 of 1 | "≥2" in a figure, read as ">2" (the same letters and digits) |
| 005264 p42 | 1 of 1 | "Release" set vertically |
| 005946 p17 | 38 of 40 | chart axes and dates |
| 005946 p11 | 31 of 33 | chart axes (most colour-scale numbers missed) |
| 005937 p12 | 27 of 29 | chart ticks (most colour-scale numbers missed) |
| 005344 p9 | 30 of 32 | chart legends and axes (several ticks missed) |
| 005083 p2 | 31 of 34 | map labels (dozens more missed) |
| 005230 p6 | 6 of 7 | a hospital's header; one mark read as "L" |
| 005850 p2 | 10 of 12 | the titles on two cover thumbnails |
| 005448 p20 | 65 of 68 | the untrusted page, all OCR |
| 005225 p2 | 1 of 2 | a logo ("Group" missed, a mark read as "e") |
| 005756 p4 | 0 of 1 | letters in a diagram read as one "M\|M" |
| 005181 p8 | 0 of 3 | map markers read as "O e O" |
| 005525 p4 | 0 of 3 | garbled bullets, read as "e" |
| all but 005933 | 274 of 299 (92%) | |

005933 p16, a table set as an image, has 351 reference words, and by eye nearly all of them are right (about 330); they aren't in the total.

So the reference is mostly right where it has a word, and it misses a good share of what a page shows only as pixels: small labels on maps (005083 has dozens unboxed), the numbers on colour scales, and stylised logo words. Pipeline words in those places will count as extra against it, so precision on maps and charts reads low. Its wrong words are marks read as letters ("O", "e"), symbols read as letters (bullets as "e") and words run together ("M|M").
