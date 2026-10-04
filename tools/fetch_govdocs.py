"""Fetch govdocs1 threads (Digital Corpora, US government files in the public domain) and unpack their PDFs.

Each thread is one zip of about 300 MB. It downloads to <thread>.zip.part, and a run that stops (a dropped
connection, a closed laptop, Ctrl+C) picks up where it left off: the next run asks the server only for
the bytes after the ones it has (an HTTP Range request), and checks the server's ETag is still the one
the part was started against, so a changed file is never spliced onto an old part. Failed requests are
retried with a growing pause. When the size matches, the zip is checked (every member's CRC) and renamed
to <thread>.zip; then only its PDFs are unpacked into <thread>/, flat, skipping any already there at the
right size, and the count is checked against the zip's.

usage: python tools/fetch_govdocs.py <dataset dir> 005 006 [...]
"""
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from rich.progress import BarColumn, DownloadColumn, Progress, TimeRemainingColumn, TransferSpeedColumn

URL = "https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/{}.zip"
CHUNK = 1 << 20
TRIES = 8


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"]), r.headers.get("ETag", "")


def download(thread, root, bar):
    url = URL.format(thread)
    final, part, state = root / f"{thread}.zip", root / f"{thread}.zip.part", root / f"{thread}.zip.state"
    if final.exists():
        return final
    size, etag = head(url)
    if part.exists() and state.exists() and json.loads(state.read_text())["etag"] != etag:
        part.unlink()  # the file changed on the server since this part was started
    state.write_text(json.dumps({"url": url, "etag": etag, "size": size}))
    task = bar.add_task(f"{thread}.zip", total=size, completed=part.stat().st_size if part.exists() else 0)
    for attempt in range(TRIES):
        have = part.stat().st_size if part.exists() else 0
        if have >= size:
            break
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-", "If-Match": etag})
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "ab") as f:
                if r.status != 206:
                    raise IOError(f"expected a partial response, got {r.status}")
                while block := r.read(CHUNK):
                    f.write(block)
                    bar.update(task, advance=len(block))
        except (urllib.error.URLError, IOError, TimeoutError) as e:
            wait = min(60, 2 ** attempt)
            bar.console.print(f"{thread}: {e}; retrying in {wait} s from byte {part.stat().st_size if part.exists() else 0:,}")
            time.sleep(wait)
    if not part.exists() or part.stat().st_size != size:
        sys.exit(f"{thread}: stopped at {part.stat().st_size if part.exists() else 0:,} of {size:,} bytes; run again to resume")
    with zipfile.ZipFile(part) as z:
        bad = z.testzip()
    if bad:
        sys.exit(f"{thread}: {bad} fails its CRC; delete {part.name} and run again")
    part.rename(final)
    state.unlink()
    return final


def unpack(zip_path, out):
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        pdfs = [m for m in z.infolist() if m.filename.lower().endswith(".pdf") and not m.is_dir()]
        done = 0
        for m in pdfs:
            dest = out / Path(m.filename).name
            if dest.exists() and dest.stat().st_size == m.file_size:
                done += 1
                continue
            with z.open(m) as src, open(dest, "wb") as f:
                while block := src.read(CHUNK):
                    f.write(block)
            done += 1
    have = sum(1 for p in out.iterdir() if p.suffix.lower() == ".pdf")
    if have != len(pdfs):
        sys.exit(f"{zip_path.name}: {len(pdfs)} PDFs in the zip but {have} in {out}")
    return len(pdfs)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=True)
    with Progress("[progress.description]{task.description}", BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn()) as bar:
        zips = [(t, download(t, root, bar)) for t in sys.argv[2:]]
    for t, z in zips:
        print(f"{t}: {z.stat().st_size:,} bytes, {unpack(z, root / t)} PDFs in {root / t}")


if __name__ == "__main__":
    main()
