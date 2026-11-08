"""Load the generator's Parquet files into Snowflake schema S4_RAW (key-pair auth, no password).

    python -m planwerk.load.snowflake [--raw data/raw] [--dry-run]

Per table: PUT the Parquet file to a temporary internal stage, create the table from the inferred
schema, COPY INTO with MATCH_BY_COLUMN_NAME, and check the row count against manifest.json.
Credentials come only from the environment: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and
SNOWFLAKE_PRIVATE_KEY_PATH (or SNOWFLAKE_PRIVATE_KEY with the PEM content).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from planwerk.generator.config import REPO_ROOT

SCHEMA = "S4_RAW"
DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "PLANWERK")


def statements(table: str, path: Path) -> list[str]:
    t = table.upper()
    return [
        f"create temporary stage if not exists {t}_STAGE file_format = (type = parquet)",
        f"put 'file://{path.resolve()}' @{t}_STAGE auto_compress = false overwrite = true",
        (f"create or replace table {SCHEMA}.{t} using template (select array_agg(object_construct(*)) "
         f"from table(infer_schema(location => '@{t}_STAGE', file_format => 'PLANWERK_PARQUET')))"),
        (f"copy into {SCHEMA}.{t} from @{t}_STAGE file_format = (format_name = 'PLANWERK_PARQUET') "
         f"match_by_column_name = case_insensitive on_error = abort_statement"),
    ]


def _connect():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
    if pem is None:
        pem = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).read_text()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return snowflake.connector.connect(account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
                                       private_key=der, role=os.environ.get("SNOWFLAKE_ROLE", "PLANWERK_LOADER"),
                                       warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "PLANWERK_WH"),
                                       database=DATABASE, schema=SCHEMA)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=Path(os.environ.get("PLANWERK_RAW", REPO_ROOT / "data" / "raw")))
    ap.add_argument("--dry-run", action="store_true", help="print the statements instead of running them")
    a = ap.parse_args(argv)
    manifest = json.loads((a.raw / "manifest.json").read_text())
    files = sorted(a.raw.glob("*.parquet"))
    setup = [f"create file format if not exists {SCHEMA}.PLANWERK_PARQUET type = parquet use_logical_type = true"]
    if a.dry_run:
        for s in setup:
            print(s + ";")
        for p in files:
            for s in statements(p.stem, p):
                print(s + ";")
        return
    con = _connect()
    cur = con.cursor()
    for s in setup:
        cur.execute(s)
    for p in files:
        for s in statements(p.stem, p):
            cur.execute(s)
        n = cur.execute(f"select count(*) from {SCHEMA}.{p.stem.upper()}").fetchone()[0]
        expected = manifest["row_counts"].get(p.stem.upper())
        if expected is not None and n != expected:
            raise RuntimeError(f"{p.stem}: loaded {n} rows, manifest says {expected}")
        print(f"{p.stem}: {n:,} rows")
    con.close()


if __name__ == "__main__":
    main()
