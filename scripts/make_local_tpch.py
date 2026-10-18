"""Generate TPC-H Parquet files locally (official dbgen-compatible data via tpchgen-cli).

Used for offline tests (scale 0.01) and for computing evaluation ground truth independently of
Snowflake (scale 1 = the same data as SNOWFLAKE_SAMPLE_DATA.TPCH_SF1). Not used to answer questions.

    pip install tpchgen-cli
    python scripts/make_local_tpch.py --scale 0.01     # -> data/tpch_sf0_01  (~3 MB, seconds)
    python scripts/make_local_tpch.py --scale 1        # -> data/tpch_sf1     (~360 MB, ~1 minute)
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def target_dir(scale: float) -> Path:
    return ROOT / "data" / f"tpch_sf{format(scale, 'g').replace('.', '_')}"


def generate(scale: float) -> Path:
    out = target_dir(scale)
    if out.exists() and len(list(out.glob("*.parquet"))) == 8:
        return out
    exe = shutil.which("tpchgen-cli")
    if not exe:
        sys.exit("tpchgen-cli not found: pip install tpchgen-cli")
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([exe, "parquet", "-s", str(scale), "--output-dir", str(out)], check=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.01)
    print(generate(ap.parse_args().scale))
