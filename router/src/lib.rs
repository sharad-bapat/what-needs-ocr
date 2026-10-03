//! What needs OCR? For each page of a born-digital PDF, the parts whose text only exists as pixels:
//! images that hold text, letters drawn as outlines, text layers that don't decode. They're routed from
//! the page map that where-are-the-regions gives, cropped, read by an OCR engine outside this crate, and
//! merged back with the file's own words.

pub use regions;

pub mod merge;
pub mod route;

#[cfg(test)]
mod tests {
    #[test]
    fn the_page_map_is_reachable() {
        // one page with one word, through where-are-the-regions
        let content = "BT /F1 12 Tf 72 700 Td (Hello) Tj ET";
        let objs = [
            "<< /Type /Catalog /Pages 2 0 R >>".to_string(),
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_string(),
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".to_string(),
            format!("<< /Length {} >>\nstream\n{}\nendstream", content.len(), content),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>".to_string(),
        ];
        let mut pdf = String::from("%PDF-1.4\n");
        for (k, o) in objs.iter().enumerate() { pdf += &format!("{} 0 obj\n{}\nendobj\n", k + 1, o); }
        pdf += "trailer << /Root 1 0 R >>\n%%EOF\n";
        let doc = regions::extract(pdf.as_bytes());
        assert_eq!(doc.pages.len(), 1);
        assert_eq!(doc.pages[0].words.iter().map(|w| w.text.as_str()).collect::<Vec<_>>(), ["Hello"]);
    }
}
