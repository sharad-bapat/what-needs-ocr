# OCR of the routes on the tune split

tools/ocr_crops.py renders every `ocr` route of the 300 tune cases from its page with PyMuPDF, in grey and with 6 pt of the page round it (an image at its own resolution between 150 and 400 dpi, outlined and garbled text at 300 dpi), reads each crop with Tesseract v5.4.0.20240606 (`-l eng --psm 3`, one thread), and maps the words back to points on the page. The words are in results/ocr-tune.jsonl. Each crop's TSV is cached by a hash of the crop and the settings; a rerun of the whole split, every crop from the cache (45 seconds, the rendering), gave a byte-identical results/ocr-tune.jsonl.

440 crops, 2 minutes 8 seconds with 4 at a time. 16 crops gave no words.

A first check against the truth, before the scorer of chunk 6: a truth word counts as read when an OCR word has the same letters and digits (any case, punctuation and underscores dropped) and its centre lies in the truth word's box, give or take 2 pt up and down.

| Kind | Truth words read |
|---|---|
| text | 14,633 of 14,735 (99.3%) |
| full_scan | 10,899 of 11,046 (98.7%) |
| outlined | 3,041 of 3,075 (98.9%) |
| garbled | 4,146 of 4,179 (99.2%) |
| all | 32,719 of 33,035 (99.0%) |

The 6 pt of white space matters: cut tight, small crops (a "1.1" in a garbled page's numbering, 37 by 29 pixels) came back empty. On 18 trial cases padding took outlined text from 180 to 183 words of 183 and a garbled page from 230 to 241 of 243. The already-OCR'd crops aren't routed, so their words come from the file's own text layer, in the merge (chunk 5). Words like "Signature:____" in the truth keep their underscores where Tesseract reads only the label; the scorer will have to drop underscores before comparing.
