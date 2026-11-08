"""Connection helper for the local DuckDB warehouse built by dbt."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from planwerk.generator.config import REPO_ROOT


def warehouse_path() -> Path:
    return Path(os.environ.get("PLANWERK_DUCKDB", REPO_ROOT / "data" / "warehouse" / "planwerk.duckdb"))


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    p = warehouse_path()
    if not p.exists():
        raise FileNotFoundError(f"warehouse {p} not found - run `make generate dbt` first")
    return duckdb.connect(str(p), read_only=read_only)
