"""Download and verify the speech model files. Uses only the Python standard library.

    python scripts/download_models.py            # download anything missing, verify all
    python scripts/download_models.py --verify   # verify only, never download

Files are checked against the SHA-256 values pinned in models/model-manifest.json.
Interrupted downloads resume. A file that fails verification is never kept.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path, expected_size: int) -> None:
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "Echolade-setup/0.1"})
    if 0 < have < expected_size:
        req.add_header("Range", f"bytes={have}-")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416:           # nothing left to resume: restart cleanly
            part.unlink(missing_ok=True)
            return download(url, dest, expected_size)
        raise
    mode = "ab" if resp.status == 206 else "wb"
    if mode == "wb":
        have = 0
    done = have
    with part.open(mode) as out:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            pct = min(100, done * 100 // max(expected_size, 1))
            print(f"\r  {dest.name}: {pct:3d}%  ({done / 1e6:,.0f} / {expected_size / 1e6:,.0f} MB)", end="", flush=True)
    print()
    part.replace(dest)


def main() -> int:
    verify_only = "--verify" in sys.argv
    manifest = json.loads((MODELS / "model-manifest.json").read_text(encoding="utf-8"))
    failed = False
    for f in manifest["files"]:
        dest = MODELS / f["name"]
        if dest.is_file() and sha256(dest) == f["sha256"]:
            print(f"  {f['name']}: verified")
            continue
        if verify_only:
            print(f"  {f['name']}: {'MISSING' if not dest.is_file() else 'DOES NOT MATCH'}")
            failed = True
            continue
        if dest.is_file():
            print(f"  {f['name']}: checksum mismatch, downloading again")
            dest.unlink()
        print(f"  Downloading {f['name']} ({f['size'] / 1e6:,.0f} MB) ...")
        try:
            download(f["url"], dest, f["size"])
        except Exception as exc:
            print(f"\n  Download failed: {exc}\n  Check your internet connection and run setup again; it resumes.")
            return 1
        if sha256(dest) != f["sha256"]:
            dest.unlink(missing_ok=True)
            print(f"  {f['name']}: downloaded file failed verification and was deleted. Run setup again.")
            return 1
        print(f"  {f['name']}: verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
