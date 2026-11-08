"""Read-only SQL guard: only SELECT on whitelisted semantic views, with a row limit."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_VIEWS = {
    "sem_kennzahlen_monat", "sem_abweichungsbruecke", "sem_produktgruppen", "sem_kostenstellen",
    "sem_kostenarten", "sem_auftragseingang", "sem_prognose",
}
ALLOWED_SCHEMA = "semantic"
MAX_ROWS = 500
FORBIDDEN_FUNCTIONS = {"read_parquet", "read_csv", "read_csv_auto", "read_json", "glob", "getvariable",
                       "setvariable", "query", "query_table", "sniff_csv", "parquet_scan", "system"}


class SQLRejected(ValueError):
    pass


def validate(sql: str, dialect: str = "duckdb") -> str:
    """Return a safe version of ``sql`` (with LIMIT) or raise SQLRejected."""
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as e:  # pragma: no cover - message varies by version
        raise SQLRejected(f"SQL nicht lesbar: {e}") from e
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SQLRejected("Genau eine Abfrage erlaubt")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLRejected("Nur SELECT-Abfragen erlaubt")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command,
                             exp.Merge, exp.Copy, exp.Attach if hasattr(exp, "Attach") else exp.Command)):
            raise SQLRejected("Schreibende Anweisung erkannt")
        if isinstance(node, exp.Func):
            name = (node.sql_name() if hasattr(node, "sql_name") else type(node).__name__).lower()
            if name in FORBIDDEN_FUNCTIONS or (isinstance(node, exp.Anonymous) and node.name.lower() in FORBIDDEN_FUNCTIONS):
                raise SQLRejected(f"Funktion nicht erlaubt: {name}")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if name in ctes:
            continue
        if name not in ALLOWED_VIEWS:
            raise SQLRejected(f"Tabelle nicht freigegeben: {t.sql()}")
        if t.db and t.db.lower() != ALLOWED_SCHEMA:
            raise SQLRejected(f"Schema nicht freigegeben: {t.db}")
        if not t.db:
            t.set("db", exp.to_identifier(ALLOWED_SCHEMA))
    if isinstance(tree, exp.Select):
        lim = tree.args.get("limit")
        if lim is None:
            tree = tree.limit(MAX_ROWS)
        else:
            try:
                n = int(lim.expression.name)
            except (AttributeError, ValueError):
                n = MAX_ROWS + 1
            if n > MAX_ROWS:
                tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect=dialect)
