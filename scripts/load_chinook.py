"""Load Chinook CSV files into Snowflake DATAMIND_DB.CHINOOK.

Uses .env credentials with role DATAMIND_ADMIN to:
1. PUT data/chinook/*.csv files to @DATAMIND_DB.CHINOOK.CHINOOK_STAGE
2. TRUNCATE and COPY INTO each table
3. Query and print the resulting row count for each table

Run after snowflake/10_chinook_setup.sql has been executed in Snowsight.

Usage:
    python scripts/load_chinook.py            # live load to Snowflake
    python scripts/load_chinook.py --dry-run  # inspect statements without executing
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datamind.config import load_dotenv

# Tables in dependency order (referenced tables loaded before referencing ones)
TABLE_ORDER = [
    "ARTIST",
    "ALBUM",
    "EMPLOYEE",
    "CUSTOMER",
    "GENRE",
    "MEDIA_TYPE",
    "TRACK",
    "INVOICE",
    "INVOICE_LINE",
    "PLAYLIST",
    "PLAYLIST_TRACK",
]

# Mapping table uppercase name -> local CSV filename (without .csv)
TABLE_FILE_MAP = {
    "ARTIST": "artist",
    "ALBUM": "album",
    "EMPLOYEE": "employee",
    "CUSTOMER": "customer",
    "GENRE": "genre",
    "MEDIA_TYPE": "media_type",
    "TRACK": "track",
    "INVOICE": "invoice",
    "INVOICE_LINE": "invoice_line",
    "PLAYLIST": "playlist",
    "PLAYLIST_TRACK": "playlist_track",
}


def build_snowflake_params() -> dict[str, Any]:
    load_dotenv()
    params: dict[str, Any] = {
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
        "user": os.environ.get("SNOWFLAKE_USER", ""),
        "role": os.environ.get("SNOWFLAKE_ADMIN_ROLE", "DATAMIND_ADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "DATAMIND_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "DATAMIND_DB"),
        "schema": "CHINOOK",
        "client_session_keep_alive": True,
        "application": "DataMind-Loader",
    }
    pk_file = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
    pw = os.getenv("SNOWFLAKE_PASSWORD")
    if pk_file:
        from cryptography.hazmat.primitives import serialization
        key_path = Path(pk_file) if Path(pk_file).is_absolute() else ROOT / pk_file
        passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        p_bytes = passphrase.encode() if passphrase else None
        p_key = serialization.load_pem_private_key(key_path.read_bytes(), password=p_bytes)
        params["private_key"] = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    elif pw:
        params["password"] = pw
    return params


def load_chinook(data_dir: Path, dry_run: bool = False) -> dict[str, int]:
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory {data_dir} does not exist. Run scripts/get_chinook.py first.")

    for table in TABLE_ORDER:
        csv_file = data_dir / f"{TABLE_FILE_MAP[table]}.csv"
        if not csv_file.exists():
            raise FileNotFoundError(f"Missing required CSV file: {csv_file}")

    if dry_run:
        print("=== DRY RUN: The following operations would be executed ===")
        for table in TABLE_ORDER:
            csv_file = data_dir / f"{TABLE_FILE_MAP[table]}.csv"
            print(f"PUT file://{csv_file.as_posix()} @DATAMIND_DB.CHINOOK.CHINOOK_STAGE AUTO_COMPRESS=TRUE OVERWRITE=TRUE;")
            print(f"TRUNCATE TABLE DATAMIND_DB.CHINOOK.{table};")
            print(
                f"COPY INTO DATAMIND_DB.CHINOOK.{table} "
                f"FROM @DATAMIND_DB.CHINOOK.CHINOOK_STAGE/{csv_file.name}.gz "
                f"FILE_FORMAT = (FORMAT_NAME = 'DATAMIND_DB.CHINOOK.CHINOOK_CSV_FORMAT') "
                f"ON_ERROR = 'ABORT_STATEMENT';"
            )
            print(f"SELECT COUNT(*) FROM DATAMIND_DB.CHINOOK.{table};")
        return {t: -1 for t in TABLE_ORDER}

    import snowflake.connector

    params = build_snowflake_params()
    if not params.get("account") or not params.get("user"):
        raise ValueError("SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set in .env")

    print(f"Connecting to Snowflake ({params['account']}) as role {params['role']}...")
    con = snowflake.connector.connect(**params)
    cur = con.cursor()
    row_counts = {}

    try:
        cur.execute(f"USE ROLE {params['role']}")
        cur.execute(f"USE WAREHOUSE {params['warehouse']}")
        cur.execute(f"USE SCHEMA {params['database']}.CHINOOK")

        for table in TABLE_ORDER:
            csv_file = data_dir / f"{TABLE_FILE_MAP[table]}.csv"
            print(f"\n--- Loading {table} ---")
            put_sql = f"PUT file://{csv_file.as_posix()} @CHINOOK_STAGE AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
            print(f"Uploading {csv_file.name} to @CHINOOK_STAGE...")
            cur.execute(put_sql)

            print(f"Truncating {table}...")
            cur.execute(f"TRUNCATE TABLE {table}")

            copy_sql = (
                f"COPY INTO {table} "
                f"FROM @CHINOOK_STAGE/{csv_file.name} "
                f"FILE_FORMAT = (FORMAT_NAME = 'CHINOOK_CSV_FORMAT') "
                f"ON_ERROR = 'ABORT_STATEMENT'"
            )
            print(f"Copying into {table}...")
            cur.execute(copy_sql)

            cur.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cur.fetchone()[0]
            row_counts[table] = cnt
            print(f"Loaded {table}: {cnt} rows.")

    finally:
        cur.close()
        con.close()

    return row_counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Upload Chinook CSV data into Snowflake DATAMIND_DB.CHINOOK")
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "chinook"), help="path to directory with Chinook CSVs")
    ap.add_argument("--dry-run", action="store_true", help="print statements without executing them")
    args = ap.parse_args(argv)

    try:
        counts = load_chinook(Path(args.data_dir), dry_run=args.dry_run)
        if not args.dry_run:
            print("\n=== Chinook Load Complete ===")
            for t, c in counts.items():
                print(f"  {t:<16}: {c:>6} rows")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
