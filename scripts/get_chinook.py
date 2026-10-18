"""Download and extract the Chinook database for offline testing and Snowflake loading.

Source: Chinook_Sqlite.sqlite from github.com/lerocha/chinook-database
Path: ChinookDatabase/DataSources/Chinook_Sqlite.sqlite
Commit: 7f67772503d71ba90f19283c38e93923addb43fa (pinned, MIT licence)
SHA-256: 7651ba378ac2fcd0dfc3c66fb101f7a7eed3ba39a612ec642b96e20702061f15

Reads the SQLite database strictly as data via Python's sqlite3 in read-only URI mode,
never executes anything from the download, and exports one CSV and one Parquet per
table into data/chinook/ (git-ignored).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

CHINOOK_URL = (
    "https://raw.githubusercontent.com/lerocha/chinook-database/"
    "7f67772503d71ba90f19283c38e93923addb43fa/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
)
EXPECTED_SHA256 = "7651ba378ac2fcd0dfc3c66fb101f7a7eed3ba39a612ec642b96e20702061f15"


def camel_to_snake(s: str) -> str:
    """Convert CamelCase / PascalCase to snake_case."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def download_sqlite(dest: Path, force: bool = False) -> Path:
    if dest.exists() and not force:
        h = hashlib.sha256(dest.read_bytes()).hexdigest()
        if h == EXPECTED_SHA256:
            return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest.with_suffix(".tmp")
    print(f"Downloading Chinook SQLite from {CHINOOK_URL}...")
    urllib.request.urlretrieve(CHINOOK_URL, temp_file)
    actual_hash = hashlib.sha256(temp_file.read_bytes()).hexdigest()
    if actual_hash != EXPECTED_SHA256:
        temp_file.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 mismatch for downloaded file:\n"
            f"  Expected: {EXPECTED_SHA256}\n"
            f"  Actual:   {actual_hash}"
        )
    temp_file.replace(dest)
    print(f"Verified SHA-256: {actual_hash}")
    return dest


def export_tables(sqlite_path: Path, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    row_counts = {}
    for table in tables:
        target_name = camel_to_snake(table)
        cur.execute(f'SELECT * FROM "{table}"')
        raw_cols = [d[0] for d in cur.description]
        snake_cols = [camel_to_snake(c) for c in raw_cols]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=snake_cols)
        for c in df.columns:
            if c.endswith("_date"):
                df[c] = pd.to_datetime(df[c])
        csv_path = out_dir / f"{target_name}.csv"
        parquet_path = out_dir / f"{target_name}.parquet"
        df.to_csv(csv_path, index=False)
        df.to_parquet(parquet_path, index=False)
        row_counts[target_name] = len(df)
        print(f"Exported {target_name} ({len(df)} rows) -> {csv_path.name}, {parquet_path.name}")
    con.close()
    return row_counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download and export Chinook dataset to CSV & Parquet")
    ap.add_argument("--force", action="store_true", help="re-download even if already present")
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "chinook"), help="target output directory")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    sqlite_file = out_dir / "Chinook_Sqlite.sqlite"
    download_sqlite(sqlite_file, force=args.force)
    counts = export_tables(sqlite_file, out_dir)
    print(f"\nDone. Exported {len(counts)} tables to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
