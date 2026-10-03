//! router-cli: the routes of each page, one JSON line per file.
//!
//! usage: router-cli <file.pdf>...
//!        router-cli --list <list.txt>     one path per line

use router::route::route_page;
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
            format!("{{\"x0\":{},\"y0\":{},\"x1\":{},\"y1\":{},\"source\":\"{}\",\"index\":{},\"decision\":\"{}\",\"confidence\":{},\"reasons\":[{}]}}",
                    r2(r.x0), r2(r.y0), r2(r.x1), r2(r.y1), r.source, r.index, r.decision, r2(r.confidence), reasons.join(","))
        }).collect();
        format!("{{\"n\":{},\"width\":{},\"height\":{},\"routes\":[{}]}}", p.n, r2(p.width), r2(p.height), routes.join(","))
    }).collect();
    format!("{{\"file\":{},\"status\":\"{}\",\"pages\":[{}]}}", json_str(path), doc.status, pages.join(","))
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let files: Vec<String> = if args.first().map(|a| a == "--list").unwrap_or(false) {
        let list = std::fs::read_to_string(args.get(1).expect("--list needs a file")).expect("can't read the list");
        list.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect()
    } else {
        args
    };
    if files.is_empty() {
        eprintln!("usage: router-cli <file.pdf>... | router-cli --list <list.txt>");
        std::process::exit(2);
    }
    for f in files { println!("{}", file_json(&f)); }
}
