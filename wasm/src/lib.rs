//! The browser build of What needs OCR?: the routes of each page, as router-cli prints them, and the
//! merged word list from crops OCR'd somewhere else (a browser can't run Tesseract here), as router-cli
//! --merge prints it. The JSON is router-cli's without its "file" key (and, merged, its "ocr" key), byte
//! for byte; tools/wasm_check.mjs compares the two.
use regions::json_str;
use router::merge::{merge, Crop, FileWord};
use router::regions;
use router::route::{route_page, undecodable};
use wasm_bindgen::prelude::*;

fn r2(v: f64) -> f64 { (v * 100.0).round() / 100.0 }

/// The routes for the bytes of one PDF: per page, its size and every route with its box, source,
/// decision, confidence, dpi and reasons.
#[wasm_bindgen]
pub fn routes_json(bytes: &[u8]) -> String {
    let doc = regions::extract(bytes);
    let pages: Vec<String> = doc.pages.iter().map(|p| {
        let routes: Vec<String> = route_page(bytes, p).iter().map(|r| {
            let reasons: Vec<String> = r.reasons.iter().map(|(k, v)| format!("[{},{}]", json_str(k), r2(*v))).collect();
            format!("{{\"x0\":{},\"y0\":{},\"x1\":{},\"y1\":{},\"source\":\"{}\",\"index\":{},\"decision\":\"{}\",\"confidence\":{},\"dpi\":{},\"reasons\":[{}]}}",
                    r2(r.x0), r2(r.y0), r2(r.x1), r2(r.y1), r.source, r.index, r.decision, r2(r.confidence), r2(r.dpi), reasons.join(","))
        }).collect();
        format!("{{\"n\":{},\"width\":{},\"height\":{},\"routes\":[{}]}}", p.n, r2(p.width), r2(p.height), routes.join(","))
    }).collect();
    format!("{{\"status\":\"{}\",\"pages\":[{}]}}", doc.status, pages.join(","))
}

/// The crops of one file as tools/ocr_crops.py writes them (its "pages" array: per page number, each
/// crop's box, source and words, [x0, y0, x1, y1, text, confidence 0 to 100]).
fn read_crops(json: &str) -> Vec<(u64, Vec<Crop>)> {
    let d: serde_json::Value = serde_json::from_str(json).unwrap_or(serde_json::Value::Null);
    let b4 = |v: &serde_json::Value| -> [f64; 4] {
        let a: Vec<f64> = v.as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default();
        if a.len() < 4 { [0.0; 4] } else { [a[0], a[1], a[2], a[3]] }
    };
    d.as_array().into_iter().flatten().map(|p| {
        let crops = p["crops"].as_array().into_iter().flatten().map(|c| Crop {
            b: b4(&c["box"]),
            source: c["source"].as_str().unwrap_or("").to_string(),
            words: c["words"].as_array().into_iter().flatten().map(|w| (b4(w), w[4].as_str().unwrap_or("").to_string(), w[5].as_f64().unwrap_or(0.0))).collect(),
        }).collect();
        (p["n"].as_u64().unwrap_or(0), crops)
    }).collect()
}

/// The merged word list for the bytes of one PDF and the OCR results for its crops (`crops`, as
/// read_crops takes them): per page, the file's visible words and the OCR words that add to them, each
/// with its source and confidence. OCR words under `min_conf` (0 to 1; router::merge::MIN_CONF is the
/// default) are left out.
#[wasm_bindgen]
pub fn merge_json(bytes: &[u8], crops: &str, min_conf: f64) -> String {
    let doc = regions::extract(bytes);
    let found = read_crops(crops);
    let none = Vec::new();
    let pages: Vec<String> = doc.pages.iter().map(|p| {
        let file: Vec<FileWord> = p.words.iter().map(|w| FileWord {
            text: w.text.clone(), b: [w.x0, w.y0, w.x1, w.y1], invisible: w.invisible,
            unseen: w.offpage || w.hidden || w.white, undecodable: undecodable(&w.text, w.unmapped),
        }).collect();
        let crops = found.iter().find(|(n, _)| *n == p.n as u64).map(|(_, c)| c).unwrap_or(&none);
        let words: Vec<String> = merge(&file, crops, min_conf).iter().map(|w| format!(
            "{{\"t\":{},\"x0\":{},\"y0\":{},\"x1\":{},\"y1\":{},\"source\":\"{}\",\"confidence\":{}{}}}",
            json_str(&w.text), r2(w.b[0]), r2(w.b[1]), r2(w.b[2]), r2(w.b[3]), w.source, r2(w.confidence),
            w.crop.map(|c| format!(",\"crop\":{c}")).unwrap_or_default())).collect();
        format!("{{\"n\":{},\"width\":{},\"height\":{},\"words\":[{}]}}", p.n, r2(p.width), r2(p.height), words.join(","))
    }).collect();
    format!("{{\"status\":\"{}\",\"pages\":[{}]}}", doc.status, pages.join(","))
}

/// The merge's default OCR-confidence cutoff, for the demo to show.
#[wasm_bindgen]
pub fn min_conf() -> f64 { router::merge::MIN_CONF }
