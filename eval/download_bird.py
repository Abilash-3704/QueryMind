#!/usr/bin/env python3
"""
Download the BIRD dev set (dev.json + dev_databases + dev_tables.json) into eval/data/.

Usage:
    python eval/download_bird.py           # skip if already downloaded
    python eval/download_bird.py --force   # re-download

Final layout:
    eval/data/dev.json
    eval/data/dev_tables.json
    eval/data/dev_databases/<db_id>/<db_id>.sqlite
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DEV_ZIP_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"


def _download(url: str, dest: Path) -> None:
    import httpx

    print(f"Downloading {url}\n  → {dest}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1 << 16):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {pct}% ({downloaded:,}/{total:,} bytes)", end="", flush=True)
        print()


def _unzip(zip_path: Path, dest_dir: Path) -> None:
    print(f"Unzipping {zip_path.name} → {dest_dir}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def _find(name: str, root: Path) -> Path | None:
    """Find a file by name anywhere under root (BIRD's zip nests contents in subdirs)."""
    matches = list(root.rglob(name))
    return matches[0] if matches else None


def _flatten(root: Path) -> None:
    """Move dev.json / dev_tables.json / dev_databases/ up to eval/data/ regardless of nesting."""
    dev_json = _find("dev.json", root)
    dev_tables = _find("dev_tables.json", root)
    dev_databases_zip = _find("dev_databases.zip", root)

    if dev_json and dev_json.parent != root:
        shutil.move(str(dev_json), str(root / "dev.json"))
        dev_json = root / "dev.json"
    if dev_tables and dev_tables.parent != root:
        shutil.move(str(dev_tables), str(root / "dev_tables.json"))

    if dev_databases_zip:
        _unzip(dev_databases_zip, root)
        # dev_databases.zip may extract to root/dev_databases or root/<nested>/dev_databases
        extracted = _find("dev_databases", root)
        if extracted and extracted != root / "dev_databases":
            if (root / "dev_databases").exists():
                shutil.rmtree(root / "dev_databases")
            shutil.move(str(extracted), str(root / "dev_databases"))


def _summarize(dev_json_path: Path) -> None:
    data = json.loads(dev_json_path.read_text())
    difficulty_counts = Counter(item["difficulty"] for item in data)
    db_ids = {item["db_id"] for item in data}

    print(f"\nBIRD dev set ready: {len(data)} questions across {len(db_ids)} databases")
    for level in ("simple", "moderate", "challenging"):
        print(f"  {level:<12}: {difficulty_counts.get(level, 0)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    args = parser.parse_args()

    dev_json_path = DATA_DIR / "dev.json"
    if dev_json_path.exists() and not args.force:
        print(f"Already downloaded: {dev_json_path} (use --force to re-download)")
        _summarize(dev_json_path)
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DATA_DIR / "dev.zip"

    try:
        import httpx  # noqa: F401
    except ImportError:
        print("httpx not installed. Run: pip install httpx")
        sys.exit(1)

    _download(DEV_ZIP_URL, zip_path)
    _unzip(zip_path, DATA_DIR)
    _flatten(DATA_DIR)

    if not (DATA_DIR / "dev.json").exists():
        print("[ERROR] dev.json not found after extraction. Check the zip contents.")
        sys.exit(1)

    dbs = list((DATA_DIR / "dev_databases").glob("*/*.sqlite")) if (DATA_DIR / "dev_databases").exists() else []
    print(f"Extracted {len(dbs)} SQLite databases.")

    _summarize(DATA_DIR / "dev.json")
    print("\nDone.")


if __name__ == "__main__":
    main()
