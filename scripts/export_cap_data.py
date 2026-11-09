"""Export the semantic views from the local DuckDB warehouse as CAP initial data (CSV, ';').

    python scripts/export_cap_data.py [--duckdb data/warehouse/planwerk.duckdb]

Writes sap/cap/db/data/planwerk-<Entity>.csv. CAP loads these into SQLite (local tests) and into
the HDI container on SAP HANA Cloud (deploy). All figures are SIMULATED.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
VIEWS = {
    "KennzahlenMonat": "sem_kennzahlen_monat",
    "Abweichungsbruecke": "sem_abweichungsbruecke",
    "Kostenstellen": "sem_kostenstellen",
    "Kostenarten": "sem_kostenarten",
    "Produktgruppen": "sem_produktgruppen",
    "Auftragseingang": "sem_auftragseingang",
}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duckdb", type=Path,
                    default=Path(os.environ.get("PLANWERK_DUCKDB", ROOT / "data" / "warehouse" / "planwerk.duckdb")))
    ap.add_argument("--out", type=Path, default=ROOT / "sap" / "cap" / "db" / "data")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(a.duckdb), read_only=True)
    con.execute("set variable planwerk_user = 'controller'")  # full view; CAP applies its own rules
    for entity, view in VIEWS.items():
        df = con.execute(f"select * from semantic.{view}").df()
        for c in df.columns:
            if df[c].dtype.kind == "f":
                df[c] = df[c].round(6 if c.endswith("_pct") else 2)
        path = a.out / f"planwerk-{entity}.csv"
        df.to_csv(path, sep=";", index=False)
        print(f"{path.name}: {len(df)} rows")


if __name__ == "__main__":
    main()
