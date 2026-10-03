//! router-cli: the routes of each page, one JSON line per file; with --merge, each page's merged word
//! list instead (router::merge), from the file's own words and the OCR results tools/ocr_crops.py wrote.
//!
//! usage: router-cli <file.pdf>...
//!        router-cli --list <list.txt>     one path per line
//!        router-cli --merge <ocr.jsonl> (<file.pdf>... | --list <list.txt>)

use std::collections::HashMap;

use router::merge::{merge, Crop, FileWord};
use router::route::{route_page, undecodable};
use regions::json_str;

fn r2(v: f64) -> f64 { (v * 100.0).round() / 100.0 }

fn file_json(path: &str) -> String {
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(e) => return format!("{{\"file\":{},\"status\":{}}}", json_str(path), json_str(&e.to_string())),
    };
    let doc = regions::extract(&bytes);
    let pages: Vec<String> = doc.pages.iter().map(|p| {
        let routes: Vec<String> = route_page(&bytes, p).iter().map(|r| {
            let reasons: Vec<String> = r.reasons.iter().map(|(k, v)| format!("[{},{}]", json_str(k), r2(*v))).collect();
            format!("{{\"x0\":{},\"y0\":{},\"x1\":{},\"y1\":{},\"source\":\"{}\",\"index\":{},\"decision\":\"{}\",\"confidence\":{},\"dpi\":{},\"reasons\":[{}]}}",
                    r2(r.x0), r2(r.y0), r2(r.x1), r2(r.y1), r.source, r.index, r.decision, r2(r.confidence), r2(r.dpi), reasons.join(","))
        }).collect();
        format!("{{\"n\":{},\"width\":{},\"height\":{},\"routes\":[{}]}}", p.n, r2(p.width), r2(p.height), routes.join(","))
    }).collect();
    format!("{{\"file\":{},\"status\":\"{}\",\"pages\":[{}]}}", json_str(path), doc.status, pages.join(","))
}

/// A path as a key: forward slashes, lower case (the OCR results hold the paths router-cli was given,
/// resolved by Python).
fn key(path: &str) -> String {
    let p = std::fs::canonicalize(path).map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|_| path.to_string());
    p.trim_start_matches(r"\\?\").replace('\\', "/").to_lowercase()
}

/// The OCR results file: per file, per page number, its crops.
fn read_ocr(path: &str) -> HashMap<String, HashMap<u64, Vec<Crop>>> {
    let text = std::fs::read_to_string(path).expect("can't read the OCR results");
    let mut out = HashMap::new();
    for line in text.lines().filter(|l| !l.trim().is_empty()) {
        let d: serde_json::Value = serde_json::from_str(line).expect("an OCR results line isn't JSON");
        let b4 = |v: &serde_json::Value| -> [f64; 4] { let a: Vec<f64> = v.as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default(); [a[0], a[1], a[2], a[3]] };
        let mut pages = HashMap::new();
        for p in d["pages"].as_array().into_iter().flatten() {
            let crops = p["crops"].as_array().into_iter().flatten().map(|c| Crop {
                b: b4(&c["box"]),
                source: c["source"].as_str().unwrap_or("").to_string(),
                words: c["words"].as_array().into_iter().flatten().map(|w| (b4(w), w[4].as_str().unwrap_or("").to_string(), w[5].as_f64().unwrap_or(0.0))).collect(),
            }).collect();
            pages.insert(p["n"].as_u64().unwrap_or(0), crops);
        }
        out.insert(key(d["file"].as_str().unwrap_or("")), pages);
    }
    out
}

fn merged_json(path: &str, ocr: &HashMap<String, HashMap<u64, Vec<Crop>>>) -> String {
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(e) => return format!("{{\"file\":{},\"status\":{}}}", json_str(path), json_str(&e.to_string())),
    };
    let doc = regions::extract(&bytes);
    let found = ocr.get(&key(path));
    let pages: Vec<String> = doc.pages.iter().map(|p| {
        let file: Vec<FileWord> = p.words.iter().map(|w| FileWord {
            text: w.text.clone(), b: [w.x0, w.y0, w.x1, w.y1], invisible: w.invisible,
            unseen: w.offpage || w.hidden || w.white, undecodable: undecodable(&w.text, w.unmapped),
        }).collect();
        let none = Vec::new();
        let crops = found.and_then(|f| f.get(&(p.n as u64))).unwrap_or(&none);
        let words: Vec<String> = merge(&file, crops).iter().map(|w| format!(
            "{{\"t\":{},\"x0\":{},\"y0\":{},\"x1\":{},\"y1\":{},\"source\":\"{}\",\"confidence\":{}{}}}",
            json_str(&w.text), r2(w.b[0]), r2(w.b[1]), r2(w.b[2]), r2(w.b[3]), w.source, r2(w.confidence),
            w.crop.map(|c| format!(",\"crop\":{c}")).unwrap_or_default())).collect();
        format!("{{\"n\":{},\"width\":{},\"height\":{},\"words\":[{}]}}", p.n, r2(p.width), r2(p.height), words.join(","))
    }).collect();
    format!("{{\"file\":{},\"status\":\"{}\",\"ocr\":{},\"pages\":[{}]}}", json_str(path), doc.status, found.is_some(), pages.join(","))
}

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let ocr = if args.first().map(|a| a == "--merge").unwrap_or(false) {
        let path = args.get(1).expect("--merge needs the OCR results file").clone();
        args.drain(0..2);
        Some(read_ocr(&path))
    } else {
        None
    };
    let files: Vec<String> = if args.first().map(|a| a == "--list").unwrap_or(false) {
        let list = std::fs::read_to_string(args.get(1).expect("--list needs a file")).expect("can't read the list");
        list.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect()
    } else {
        args
    };
    if files.is_empty() {
        eprintln!("usage: router-cli <file.pdf>... | router-cli --list <list.txt> | router-cli --merge <ocr.jsonl> (<file.pdf>... | --list <list.txt>)");
        std::process::exit(2);
    }
    for f in files {
        match &ocr { Some(o) => println!("{}", merged_json(&f, o)), None => println!("{}", file_json(&f)) }
    }
}
