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
