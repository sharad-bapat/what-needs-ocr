//! Merge: one word list per page, from the file's own words and the words OCR read in the routed crops.
//!
//!   file            a visible word the file gives as text
//!   file_ocr_layer  a word of an invisible text layer already in the file (an earlier OCR); kept as it
//!                   is, since the router doesn't send it to OCR again
//!   ocr             a word OCR read in a crop, with OCR's confidence (0 to 1)
//!
//! Words nobody sees are left out: off the page, hidden by a clip, or painted white. A file word that
//! doesn't decode is dropped when it lies in a crop made for undecodable words, since OCR read that
//! crop instead; one outside such a crop stays, flagged by its text. An OCR word whose centre falls on
//! a kept file word is dropped (the file's own text is exact), and so is an OCR word read twice where
//! crops overlap.

pub type BoxPt = [f64; 4];

/// A word of the file's text layer, as the page map gives it.
pub struct FileWord {
    pub text: String,
    pub b: BoxPt,
    pub invisible: bool,
    /// Off the page, hidden by its clip, or painted white.
    pub unseen: bool,
    pub undecodable: bool,
}

/// One OCR'd crop: the route's box, its source ("image", "vector" or "words"), and the words read in it
/// with OCR's confidence, 0 to 100.
pub struct Crop {
    pub b: BoxPt,
    pub source: String,
    pub words: Vec<(BoxPt, String, f64)>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Word {
    pub text: String,
    pub b: BoxPt,
    pub source: &'static str,
    pub confidence: f64,
    /// For an OCR word, the index of its crop.
    pub crop: Option<usize>,
}

fn centre(b: &BoxPt) -> (f64, f64) { ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) }

fn holds(b: &BoxPt, p: (f64, f64), grow: f64) -> bool {
    p.0 >= b[0] - grow && p.0 <= b[2] + grow && p.1 >= b[1] - grow && p.1 <= b[3] + grow
}

fn letters(s: &str) -> String { s.chars().filter(|c| c.is_alphanumeric()).flat_map(char::to_lowercase).collect() }

pub fn merge(file: &[FileWord], crops: &[Crop]) -> Vec<Word> {
    let mut out: Vec<Word> = Vec::new();
    for w in file {
        if w.unseen || w.text.trim().is_empty() { continue; }
        if w.undecodable && crops.iter().any(|c| c.source == "words" && holds(&c.b, centre(&w.b), 1.0)) { continue; }
        out.push(Word { text: w.text.clone(), b: w.b, source: if w.invisible { "file_ocr_layer" } else { "file" }, confidence: 1.0, crop: None });
    }
    let kept_file = out.len();
    for (k, c) in crops.iter().enumerate() {
        for (b, text, conf) in &c.words {
            let t = text.trim();
            if t.is_empty() { continue; }
            let p = centre(b);
            if out[..kept_file].iter().any(|f| holds(&f.b, p, 1.0)) { continue; }
            if out[kept_file..].iter().any(|o| holds(&o.b, p, 0.0) && letters(&o.text) == letters(t)) { continue; }
            out.push(Word { text: t.to_string(), b: *b, source: "ocr", confidence: (conf / 100.0).clamp(0.0, 1.0), crop: Some(k) });
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fw(text: &str, b: BoxPt) -> FileWord {
        FileWord { text: text.into(), b, invisible: false, unseen: false, undecodable: false }
    }

    #[test]
    fn file_words_win_and_ocr_fills_the_rest() {
        // a page word over an image: OCR reads it too, and only the file's copy stays; the image's other
        // word is OCR's
        let file = [fw("Signed", [100.0, 100.0, 140.0, 112.0])];
        let crops = [Crop { b: [90.0, 90.0, 300.0, 200.0], source: "image".into(),
                            words: vec![([101.0, 101.0, 139.0, 111.0], "Signed".into(), 96.0), ([150.0, 150.0, 200.0, 162.0], "Witness".into(), 91.0)] }];
        let m = merge(&file, &crops);
        assert_eq!(m.len(), 2);
        assert!(m[0].source == "file" && m[0].text == "Signed");
        assert!(m[1].source == "ocr" && m[1].text == "Witness" && (m[1].confidence - 0.91).abs() < 1e-9 && m[1].crop == Some(0));
    }

    #[test]
    fn garbled_words_in_a_words_crop_give_way_to_ocr() {
        let mut bad = fw("\u{e041}\u{e042}", [10.0, 10.0, 40.0, 22.0]);
        bad.undecodable = true;
        let mut far = fw("\u{e043}", [10.0, 400.0, 30.0, 412.0]);
        far.undecodable = true;
        let crops = [Crop { b: [8.0, 8.0, 60.0, 24.0], source: "words".into(), words: vec![([10.0, 10.0, 40.0, 22.0], "AB".into(), 88.0)] }];
        let m = merge(&[bad, far], &crops);
        // the garbled word inside the crop is replaced; the one outside every crop stays as the file gives it
        assert_eq!(m.iter().map(|w| (w.text.as_str(), w.source)).collect::<Vec<_>>(), [("\u{e043}", "file"), ("AB", "ocr")]);
    }

    #[test]
    fn unseen_words_are_left_out_and_an_ocr_layer_is_kept() {
        let mut white = fw("hidden", [0.0, 0.0, 10.0, 10.0]);
        white.unseen = true;
        let mut layer = fw("scanned", [20.0, 20.0, 60.0, 30.0]);
        layer.invisible = true;
        let m = merge(&[white, layer], &[]);
        assert!(m.len() == 1 && m[0].source == "file_ocr_layer");
    }

    #[test]
    fn a_word_read_twice_where_crops_overlap_is_kept_once() {
        let w = ([50.0, 50.0, 90.0, 62.0], "Clause".to_string(), 90.0);
        let crops = [Crop { b: [0.0, 0.0, 100.0, 100.0], source: "image".into(), words: vec![w.clone()] },
                     Crop { b: [40.0, 40.0, 200.0, 100.0], source: "vector".into(), words: vec![([51.0, 50.5, 90.0, 62.0], "clause".into(), 80.0)] }];
        assert_eq!(merge(&[], &crops).len(), 1);
    }
}
