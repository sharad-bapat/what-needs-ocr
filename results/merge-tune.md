# Merging on the tune split

router-cli --merge (router/src/merge.rs) gives one word list per page: the file's visible words (`file`), an invisible text layer already in the file (`file_ocr_layer`), and the words Tesseract read in the routed crops (`ocr`, with Tesseract's confidence). Words nobody sees (off the page, hidden by a clip, painted white) are left out; garbled words inside a crop made for them give way to the OCR; an OCR word whose centre falls on a kept file word is dropped, the file's own text being exact; and a word read twice where crops overlap is kept once. Merging the 300 tune cases with results/ocr-tune.jsonl takes 2.3 seconds: 105,262 file words, 4,012 from OCR layers already in the files and 35,053 from OCR.

A first check against each case's whole truth (the file's own words and every region's words), matched as in results/ocr-tune.md:

| Kind | Truth words in the merged list |
|---|---|
| text | 59,819 of 59,946 (99.8%) |
| text_ocr | 14,579 of 14,591 (99.9%) |
| full_scan | 10,901 of 11,046 (98.7%) |
| outlined | 16,480 of 16,514 (99.8%) |
| garbled | 15,203 of 15,234 (99.8%) |
| photo, logo, blank, control | 23,841 of 23,852 |
| all | 140,823 of 141,183 (99.75%) |

2,653 merged words match no truth word. 2,280 of them lie on words the crop edge cut, which the truth leaves out on purpose (part of each shows); 188 are misreads where a truth word is (181 by OCR, 7 in the OCR layers the set put on its controls); 31 are the file's own words that don't match the truth's spelling of them; and 67 lie where the truth has nothing, among them the source page's own outlined logo on o0078 ("SHIFTING THE LIMITS"), which is real text. The last 87 are an artefact of this check: in print so small that lines sit 4.5 pt apart, a word on the next line falls within the 2 pt allowance of its neighbour's truth box, which another word has already matched. Scoring these properly, with cut words set aside, is chunk 6.
