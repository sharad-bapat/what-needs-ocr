# Routing on the tune split

router-cli (router/src/route.rs) turns each page's map from where-are-the-regions into routes: images (`ocr`, `skip` or `text_layer`), blocks of outlined text, and blocks of words whose font doesn't decode. tools/score_route.py compares the `ocr` routes with the truth of the 300 tune cases of data/constructed, without running any OCR.

| Kind | Cases | Truth words inside an ocr route | Regions with at least 90% |
|---|---|---|---|
| text | 120 | 14,827 of 14,827 (100.0%) | 120 of 120 |
| full_scan | 30 | 11,123 of 11,123 (100.0%) | 30 of 30 |
| outlined | 30 | 3,060 of 3,101 (98.7%) | 29 of 30 |
| garbled | 30 | 4,194 of 4,194 (100.0%) | 30 of 30 |
| all | 210 | 33,204 of 33,245 (99.9%) | 209 of 210 |

Wrongly sent to OCR: none of the 30 already-OCR'd crops (each is a `text_layer` route), none of the 15 untouched pages, and 12 of the 45 photos, logos and blank sheets. All 12 are inline images: regions reads no pixels from an inline image, so the router has only structure to go on, and structure alone can't tell a photo from a scanned paragraph. Every other negative is skipped on its pixels.

Routes cover 22.8% of the page area; the regions that need OCR cover 23.5% (they include the crops' empty margins). Of the ocr routes at confidence 0.9 or more, 405 of 408 lie in a truth region; of those between 0.4 and 0.9, 27 of 39, the 12 inline negatives among the misses.

Five routes fall outside every truth region but on the source page's own drawings, and the scorer counts them apart. ContractNLI pages can draw outlined text of their own: o0078, an untouched page, has its header ("/ Perfect Welding / Solar Energy / Perfect Charging") and the Fronius logo as vector paths with no text layer, checked by eye. The router is right to send them; the truth doesn't list them.

Two changes came out of this chunk. Outlined text arrives from regions as many small vector clusters (a word or a letter each; 12,365 routes on the first run, 80.0% of words found), so the router now groups them into blocks the way it groups garbled words, and a short word regions didn't call letters is covered by its neighbours. And a standard font with a garbage ToUnicode had zero-width words in regions and wordbox, because built-in widths were looked up by the ToUnicode character; both now look them up by the glyph the encoding names (where-are-the-regions e322094, wordbox a925fbb).
