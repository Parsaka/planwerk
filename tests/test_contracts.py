"""The generator output honours the source data contract (contracts/s4_sources.yaml)."""

import pyarrow.parquet as pq
import pytest
import yaml

from planwerk.generator.config import REPO_ROOT

CONTRACT = yaml.safe_load((REPO_ROOT / "contracts" / "s4_sources.yaml").read_text(encoding="utf-8"))
TYPES = {"string": ("string", "large_string"), "decimal": ("double", "float", "decimal"),
         "integer": ("int64", "int32", "int16", "int8"), "boolean": ("bool",), "date": ("date32[day]",)}


@pytest.mark.parametrize("table", sorted(CONTRACT["tables"]))
def test_table_matches_contract(ci_data, con, table):
    out, _ = ci_data
    spec = CONTRACT["tables"][table]
    schema = pq.read_schema(out / f"{table.lower()}.parquet")
    actual = {f.name: str(f.type) for f in schema}
    for col in spec["columns"]:
        assert col["name"] in actual, f"{table}.{col['name']} missing"
        allowed = TYPES.get(col["type"], (col["type"],))
        assert actual[col["name"]].startswith(allowed), f"{table}.{col['name']}: {actual[col['name']]} != {col['type']}"
    pk = spec["primary_key"]
    if pk:
        cols = ", ".join(pk)
        nulls = con.execute(f"select count(*) from {table.lower()} where " + " or ".join(f"{c} is null" for c in pk)).fetchone()[0]
        dups = con.execute(f"select count(*) from (select {cols} from {table.lower()} group by {cols} having count(*) > 1)").fetchone()[0]
        assert nulls == 0 and dups == 0, f"{table}: {nulls} null keys, {dups} duplicate keys"
