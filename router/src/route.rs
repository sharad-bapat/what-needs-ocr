//! Routing: from a page's map (where-are-the-regions) to the parts whose text has to be read from
//! pixels. Each route is a box, where it came from, a decision and a confidence with its reasons:
//!
//!   image   every image the page draws. `text_layer` when invisible words cover it (an OCR layer: it's
//!           been read already); otherwise its structure score from regions (size, pixels, DPI, visible
//!           text over it) times its pixel evidence that it holds text, `ocr` at or above CUT and `skip`
//!           below. An image whose pixels can't be read (a codec regions doesn't decode, a colour space
//!           named from the page's resources) is judged on structure alone.
//!   vector  a cluster of paths regions calls outlined text (letters drawn as shapes), grouped into blocks;
//!           and a cluster of another kind, such as a chart or a table, that holds at least LETTERS letter
//!           shapes in word-like runs, whole. Always `ocr`.
//!   words   a font's text layer that doesn't decode: when at least half of a font's visible words hold
//!           unmapped, control, private-use or U+FFFD characters, its undecodable words are grouped into
//!           boxes, each `ocr`.
//!
//! Nothing here reads pixels itself or runs OCR; the same file always gives the same routes.

use regions::{kind, pixels, vkind, Page, Region};

/// At or above it, OCR an image. Tuned on govdocs1 005: images whose pixels show some text (a has-text
/// above regions' floor of 0.05) reach 0.15 to 0.33 there, and the constructed set's photos, logos and blank
/// sheets stay at 0.05.
pub const CUT: f64 = 0.1;
/// A vector cluster of another kind (a chart, a table) with at least this many letter-shaped paths in
/// word-like runs holds outlined text too, and is OCR'd whole: govdocs1 005's charts draw their labels so.
pub const LETTERS: u32 = 3;
/// Invisible words over at least this share of an image make it an OCR layer.
pub const LAYER: f64 = 0.3;
/// A font's text layer is garbage when at least this share of its visible words don't decode.
pub const GARBAGE: f64 = 0.5;

#[derive(Debug, Clone)]
pub struct Route {
    pub x0: f64, pub y0: f64, pub x1: f64, pub y1: f64,
    pub source: &'static str,
    /// Index into the page's images, the font for words, or how many outlined clusters a vector block holds.
    pub index: usize,
    pub decision: &'static str,
    pub confidence: f64,
    /// An image's effective resolution (pixels per inch, the coarser side), so a crop can be read at the
    /// image's own resolution; 0 for vectors and words.
    pub dpi: f64,
    pub reasons: Vec<(&'static str, f64)>,
}

/// An image's decision from regions' structural region and, when its pixels could be read, its kind:
/// (kind, kind confidence, has_text).
pub fn image_decision(r: &Region, kind: Option<(&'static str, f64, f64)>) -> (&'static str, f64, Vec<(&'static str, f64)>) {
    if r.layer_cover >= LAYER {
        return ("text_layer", r.layer_cover.min(1.0), vec![("layer_cover", r.layer_cover)]);
    }
    let mut reasons = r.reasons.clone();
    // regions' structure score starts a plain image at its BASE: scaled so that a plain image with clear
    // pixel evidence of text reaches 1
    let s = (r.confidence / regions::ocr::BASE).min(1.0);
    let c = match kind {
        Some((k, kc, has_text)) => {
            reasons.push((k, kc));
            reasons.push(("has_text", has_text));
            s * has_text
        }
        None => {
            reasons.push(("no_pixels", 0.0));
            r.confidence
        }
    };
    (if c >= CUT { "ocr" } else { "skip" }, c, reasons)
}

/// A word whose text doesn't decode to real characters: unmapped, U+FFFD, private use, or a control
/// character, C0 or C1 (005448 in govdocs1 thread 005 decodes to C1 controls among Latin-1 letters).
pub fn undecodable(text: &str, unmapped: usize) -> bool {
    unmapped > 0 || text.chars().any(|c| c == '\u{fffd}' || ('\u{e000}'..='\u{f8ff}').contains(&c) || (c.is_control() && !c.is_whitespace()))
}

/// Boxes grouped into blocks: a box joins a block when it comes within `gap` times its own height
/// of it. Boxes are taken top to bottom, so a block grows down a column of lines.
pub fn blocks(boxes: &[[f64; 4]], gap: f64) -> Vec<[f64; 4]> {
    let mut order: Vec<usize> = (0..boxes.len()).collect();
    order.sort_by(|&a, &b| boxes[a][1].total_cmp(&boxes[b][1]).then(boxes[a][0].total_cmp(&boxes[b][0])));
    let mut out: Vec<[f64; 4]> = Vec::new();
    for i in order {
        let b = boxes[i];
        let g = gap * (b[3] - b[1]).max(1.0);
        match out.iter_mut().find(|o| b[0] <= o[2] + g && b[2] >= o[0] - g && b[1] <= o[3] + g && b[3] >= o[1] - g) {
            Some(o) => *o = [o[0].min(b[0]), o[1].min(b[1]), o[2].max(b[2]), o[3].max(b[3])],
            None => out.push(b),
        }
    }
    // a block that grew can now reach another: merge until none does
    loop {
        let mut merged = false;
        'outer: for i in 0..out.len() {
            for j in i + 1..out.len() {
                let (a, b) = (out[i], out[j]);
                let g = gap * (a[3] - a[1]).min(b[3] - b[1]).max(1.0);
                if b[0] <= a[2] + g && b[2] >= a[0] - g && b[1] <= a[3] + g && b[3] >= a[1] - g {
                    out[i] = [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])];
                    out.remove(j);
                    merged = true;
                    break 'outer;
                }
            }
        }
        if !merged { return out; }
    }
}

/// The routes for one page of the file `bytes`.
pub fn route_page(bytes: &[u8], page: &Page) -> Vec<Route> {
    let mut out = Vec::new();
    for r in &page.regions {
        let img = &page.images[r.image];
        // turned to how it shows on the page, so text on a rotated page reads as text (where-are-the-regions results/kinds-turn.md)
        let thumb = pixels::placed_thumbnail(bytes, img, kind::KIND_THUMB).ok();
        let k = thumb.map(|t| kind::classify(t.w, t.h, &t.grey)).map(|k| (k.kind, k.confidence, k.has_text));
        let (decision, confidence, reasons) = image_decision(r, k);
        out.push(Route { x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1, source: "image", index: r.image, decision, confidence, dpi: r.dpi, reasons });
    }
    // outlined text comes as many small clusters (a word, a letter): grouped into blocks like lines of
    // words, so a short word regions didn't call letters is covered by its neighbours' block
    let kinds = vkind::classify_page(&page.vectors, &page.paths);
    let (mut boxes, mut conf) = (Vec::new(), 0.0f64);
    for (i, (v, k)) in page.vectors.iter().zip(&kinds).enumerate() {
        if v.white || v.hidden || v.offpage { continue; }
        if k.kind == "outlined_text" {
            boxes.push([v.x0, v.y0, v.x1, v.y1]);
            conf = conf.max(k.confidence);
        } else if k.features.glyphs >= LETTERS {
            out.push(Route { x0: v.x0, y0: v.y0, x1: v.x1, y1: v.y1, source: "vector", index: i, decision: "ocr",
                             confidence: k.has_text.max(0.5), dpi: 0.0, reasons: vec![(k.kind, k.confidence), ("letters", k.features.glyphs as f64)] });
        }
    }
    for b in blocks(&boxes, 1.5) {
        let n = boxes.iter().filter(|v| v[0] >= b[0] && v[2] <= b[2] && v[1] >= b[1] && v[3] <= b[3]).count();
        out.push(Route { x0: b[0], y0: b[1], x1: b[2], y1: b[3], source: "vector", index: n, decision: "ocr",
                         confidence: conf, dpi: 0.0, reasons: vec![("outlined_clusters", n as f64)] });
    }
    let shown = |w: &&regions::Word| !(w.invisible || w.white || w.hidden || w.offpage);
    let mut fonts: Vec<u32> = page.words.iter().filter(shown).map(|w| w.font).collect();
    fonts.sort_unstable();
    fonts.dedup();
    for f in fonts {
        let ws: Vec<&regions::Word> = page.words.iter().filter(shown).filter(|w| w.font == f).collect();
        let bad: Vec<[f64; 4]> = ws.iter().filter(|w| undecodable(&w.text, w.unmapped)).map(|w| [w.x0, w.y0, w.x1, w.y1]).collect();
        let share = bad.len() as f64 / ws.len() as f64;
        if share < GARBAGE { continue; }
        for b in blocks(&bad, 1.5) {
            out.push(Route { x0: b[0], y0: b[1], x1: b[2], y1: b[3], source: "words", index: f as usize, decision: "ocr",
                             confidence: share, dpi: 0.0, reasons: vec![("undecodable", share), ("font_words", ws.len() as f64)] });
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(confidence: f64, layer_cover: f64) -> Region {
        Region { x0: 0.0, y0: 0.0, x1: 100.0, y1: 100.0, image: 0, obj: 1, dpi: 300.0, share: 0.1, text_cover: 0.0, layer_cover,
                 text_words: 0, layer_words: 0, confidence, reasons: Vec::new(), mask: false, annot: false, small: false }
    }

    #[test]
    fn an_image_is_judged_by_its_pixels_when_it_can_be() {
        // a plain image (regions' BASE) with text in its pixels goes to OCR, a photo doesn't
        assert_eq!(image_decision(&region(0.8, 0.0), Some(("text", 0.9, 1.0))).0, "ocr");
        assert_eq!(image_decision(&region(0.8, 0.0), Some(("photo", 0.9, 0.0))).0, "skip");
        // an OCR layer over it: already read
        assert_eq!(image_decision(&region(0.1, 0.9), Some(("text", 0.9, 1.0))).0, "text_layer");
        // no pixels (an image that doesn't decode): structure alone
        let (d, c, r) = image_decision(&region(0.8, 0.0), None);
        assert!(d == "ocr" && (c - 0.8).abs() < 1e-9 && r.iter().any(|x| x.0 == "no_pixels"));
    }

    #[test]
    fn undecodable_words_are_control_private_use_or_unmapped() {
        assert!(undecodable("\u{1c}\u{11}", 0) && undecodable("\u{e041}b", 0) && undecodable("ok", 1) && undecodable("a\u{fffd}", 0));
        assert!(!undecodable("Party", 0) && !undecodable("a b", 0));
        assert!(undecodable("}\u{8f}\u{be}", 0) && !undecodable("caf\u{e9}", 0));
    }

    #[test]
    fn nearby_word_boxes_make_one_block() {
        // two lines of words 12 pt tall, 4 pt apart, and a word far below
        let b = blocks(&[[10.0, 10.0, 50.0, 22.0], [60.0, 10.0, 90.0, 22.0], [10.0, 26.0, 80.0, 38.0], [10.0, 300.0, 40.0, 312.0]], 1.5);
        assert_eq!(b, vec![[10.0, 10.0, 90.0, 38.0], [10.0, 300.0, 40.0, 312.0]]);
        // two blocks that only meet once one has grown (the third box joins the first, then reaches the second)
        let b = blocks(&[[10.0, 10.0, 20.0, 20.0], [100.0, 12.0, 110.0, 22.0], [24.0, 14.0, 96.0, 24.0]], 0.5);
        assert_eq!(b, vec![[10.0, 10.0, 110.0, 24.0]]);
    }

    #[test]
    fn a_text_layer_that_decodes_to_private_use_is_routed() {
        // Helvetica whose ToUnicode sends codes 32-126 to U+E020-U+E07E: the page reads as garbage
        let cmap = "/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfrange <20> <7E> <E020> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end";
        let content = "BT /F1 12 Tf 72 700 Td (Garbled words on a line) Tj ET";
        let objs = [
            "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_string(),
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".to_string(),
            format!("<< /Length {} >>\nstream\n{}\nendstream", content.len(), content),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding /ToUnicode 6 0 R >>".to_string(),
            format!("<< /Length {} >>\nstream\n{}\nendstream", cmap.len(), cmap),
        ];
        let mut pdf = String::from("%PDF-1.4\n");
        for (k, o) in objs.iter().enumerate() { pdf += &format!("{} 0 obj\n{}\nendobj\n", k + 1, o); }
        pdf += "trailer << /Root 1 0 R >>\n%%EOF\n";
        let doc = regions::extract(pdf.as_bytes());
        let routes = route_page(pdf.as_bytes(), &doc.pages[0]);
        assert_eq!(routes.len(), 1, "{routes:?}");
        assert!(routes[0].source == "words" && routes[0].decision == "ocr" && routes[0].confidence >= 0.99);
        assert!(routes[0].x0 >= 71.0 && routes[0].x1 > 150.0 && routes[0].y0 > 80.0 && routes[0].y1 < 100.0, "{:?}", routes[0]);
    }
}
