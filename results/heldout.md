# Held-out runs

The router, the tools and the set manifests were frozen at 2f9ff66 (results/frozen.sha256, with where-are-the-regions pinned at 57ef3a5), and tools/check_frozen.py passed before each run below. Each run was made once. The targets were fixed in the plan before any held-out data was used.

## 1. Routing on the constructed held-out split (4 October 2026)

python tools/score_route.py --split=heldout: 300 cases, none of them used in tuning.

| Kind | Cases | Truth words inside an ocr route | Regions with at least 90% |
|---|---|---|---|
| text | 120 | 15,026 of 15,026 (100.0%) | 120 of 120 |
| full_scan | 30 | 10,958 of 10,958 (100.0%) | 30 of 30 |
| outlined | 30 | 3,914 of 3,934 (99.5%) | 30 of 30 |
| garbled | 30 | 4,288 of 4,289 (100.0%) | 30 of 30 |
| all | 210 | 34,186 of 34,207 (99.9%) | 210 of 210 |

The target was at least 98% of the regions that hold text routed: all 210 are. None of the 30 already-OCR'd crops and none of the 45 photos, logos and blank sheets was sent to OCR. Routes cover 22.0% of the page area; the regions that need it cover 23.6%. Of the ocr routes at confidence 0.9 or more, 316 of 324 lie in a truth region (97.5%); the one between 0.4 and 0.9 does too.

Two of the 15 untouched pages got a route the scorer counts as wrong, and 11 routes fell on the source pages' own drawings and were counted apart. Looked at afterwards, by eye: o0359's footer ("Tel.: 91 504 61 41 ... 28009 Madrid - España") is letters drawn as outlines with no text layer under them, so the router is right and the truth doesn't list it, as with the outlined logos on o0119 ("thoughtbot") and o0439. o0199's two routes are a real mistake: two bullets stored as a private-use character (U+F0B7), the only two words in their font, sent to OCR as an undecodable layer. Each is a crop of about 4 by 11 pt.
