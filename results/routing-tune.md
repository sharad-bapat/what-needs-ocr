# Routing on the tune split

router-cli (router/src/route.rs) turns each page's map from where-are-the-regions into routes: images (`ocr`, `skip` or `text_layer`), blocks of outlined text, and blocks of words whose font doesn't decode. tools/score_route.py compares the `ocr` routes with the truth of the 300 tune cases of data/constructed, without running any OCR.

| Kind | Cases | Truth words inside an ocr route | Regions with at least 90% |
|---|---|---|---|
| text | 120 | 14,827 of 14,827 (100.0%) | 120 of 120 |
| full_scan | 30 | 11,123 of 11,123 (100.0%) | 30 of 30 |
| outlined | 30 | 3,060 of 3,101 (98.7%) | 29 of 30 |
| garbled | 30 | 4,194 of 4,194 (100.0%) | 30 of 30 |
| all | 210 | 33,204 of 33,245 (99.9%) | 209 of 210 |

Nothing is wrongly sent to OCR: none of the 30 already-OCR'd crops (each is a `text_layer` route), none of the 45 photos, logos and blank sheets, and none of the 15 untouched pages. Routes cover 21.6% of the page area; the regions that need OCR cover 23.5% (they include the crops' empty margins). Of the ocr routes at confidence 0.9 or more, 431 of 434 lie in a truth region; the one between 0.4 and 0.9 does too. The region short of 90% is outlined text, o0584, with 29 of its 41 words inside a route.

Five routes (six since tuning on govdocs1 005 routed vector clusters holding letters) fall outside every truth region but on the source page's own drawings, and the scorer counts them apart. ContractNLI pages can draw outlined text of their own: o0078, an untouched page, has its header ("/ Perfect Welding / Solar Energy / Perfect Charging") and the Fronius logo as vector paths with no text layer, checked by eye. The router is right to send them; the truth doesn't list them.

How it got here:

| Step | Words found | Wrongly routed photos, logos, blanks | ocr routes |
|---|---|---|---|
| First run | 98.1% (outlined 80.0%) | 12 of 45 | 12,714 |
| Outlined clusters grouped into blocks | 99.9% | 12 of 45 | 452 |
| Inline images read by their pixels | 99.9% | 0 of 45 | 440 |

Outlined text arrives from regions as many small vector clusters (a word or a letter each), so the router groups them into blocks the way it groups garbled words, and a short word regions didn't call letters is covered by its neighbours. The 12 wrongly routed negatives were all inline images, whose pixels regions didn't read, so only structure was left to judge them by; where-are-the-regions now decodes inline images (57ef3a5), and the router judges them like any other image. And a standard font with a garbage ToUnicode had zero-width words in regions and wordbox, because built-in widths were looked up by the ToUnicode character; both now look them up by the glyph the encoding names (where-are-the-regions e322094, wordbox a925fbb).
