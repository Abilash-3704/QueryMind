#!/usr/bin/env python3
"""
Download the Chinook SQLite database into backend/data/chinook.sqlite.
Run once before using the Phase 1 pipeline.
"""
from __future__ import annotations

import sys
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "data" / "chinook.sqlite"

# Canonical Chinook SQLite source on GitHub (raw file in repo master branch)
URL = (
    "https://raw.githubusercontent.com/lerocha/chinook-database/master/"
    "ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
)


def main() -> None:
    if DEST.exists():
        print(f"Already exists: {DEST}")
        return

    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Chinook → {DEST} …")

    try:
        import httpx
    except ImportError:
        print("httpx not installed. Run: pip install httpx")
        sys.exit(1)

    with httpx.stream("GET", URL, follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(DEST, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {pct}% ({downloaded}/{total} bytes)", end="", flush=True)
        print()

    print(f"Done. Saved to {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
