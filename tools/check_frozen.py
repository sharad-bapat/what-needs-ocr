"""Check the frozen source before any held-out run: every file in results/frozen.sha256 must hash as
recorded, where-are-the-regions (a path dependency, so part of the router's behaviour) must be at the
recorded commit with nothing changed in its regions/ folder, and router-cli must be newer than the files
built into it.

What is frozen: router/Cargo.toml, Cargo.lock and every file in router/src; the tools that crop and OCR
(ocr_crops.py), build and check the sets (build_ocr_set.py, check_truth.py, build_real.py, check_real.py)
and score (score_route.py, score_ocr.py); the set manifests (data/constructed/manifest.json and
data/real/*.json, each pinning its pages); and this file. Line endings are normalised to LF first.

usage: python tools/check_frozen.py            check
       python tools/check_frozen.py --write    record the current source (at the freeze only)
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ROOT.parent / "where-are-the-regions"
RECORD = ROOT / "results" / "frozen.sha256"
CLI = ROOT / "router" / "target" / "release" / "router-cli.exe"
TOOLS = ["tools/check_frozen.py", "tools/ocr_crops.py", "tools/build_ocr_set.py", "tools/check_truth.py", "tools/build_real.py",
         "tools/check_real.py", "tools/score_route.py", "tools/score_ocr.py"]


def names():
    src = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "router" / "src").glob("*.rs"))
    real = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "real").glob("*.json"))
    return ["router/Cargo.toml", "router/Cargo.lock"] + src + TOOLS + ["data/constructed/manifest.json"] + real


def digest_of(name):
    return hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", str(REGIONS), *args], capture_output=True, text=True).stdout.strip()


def problems():
    """What stops a held-out run: changed, missing or new files, regions moved or edited, a stale binary."""
    if not RECORD.exists():
        return ["no results/frozen.sha256: the router isn't frozen"]
    out, recorded, regions_commit = [], {}, None
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        if name == "where-are-the-regions":
            regions_commit = digest
            continue
        recorded[name] = digest
        if not (ROOT / name).exists():
            out.append(f"MISSING {name}")
        elif digest_of(name) != digest:
            out.append(f"CHANGED {name}")
    out += [f"NEW {n} (not in the record)" for n in names() if n not in recorded]
    if regions_commit != git("rev-parse", "HEAD"):
        out.append(f"where-are-the-regions is at {git('rev-parse', '--short', 'HEAD')}, frozen at {(regions_commit or '?')[:7]}")
    if git("status", "--porcelain", "--", "regions"):
        out.append("where-are-the-regions has changes in regions/")
    if not CLI.exists():
        out.append("no release router-cli: cargo build --release")
    elif any((ROOT / n).stat().st_mtime > CLI.stat().st_mtime for n in recorded if n.startswith("router/") and (ROOT / n).exists()):
        out.append("router-cli is older than its source: cargo build --release")
    return out


def require_frozen():
    """For the held-out guards: stop unless the source is frozen."""
    p = problems()
    if p:
        sys.exit("held-out data is refused, the source isn't frozen:\n  " + "\n  ".join(p))


if __name__ == "__main__":
    if "--write" in sys.argv:
        lines = [f"{digest_of(n)}  {n}" for n in names()] + [f"{git('rev-parse', 'HEAD')}  where-are-the-regions"]
        RECORD.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"recorded {len(lines) - 1} files and where-are-the-regions at {git('rev-parse', '--short', 'HEAD')}")
    p = problems()
    print("frozen source: ok" if not p else "frozen source: " + str(len(p)) + " problem(s)\n  " + "\n  ".join(p))
    sys.exit(1 if p else 0)
