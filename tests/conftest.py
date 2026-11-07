from __future__ import annotations

import duckdb
import pytest

from planwerk.generator.config import GeneratorConfig
from planwerk.generator.run import generate


@pytest.fixture(scope="session")
def ci_data(tmp_path_factory):
    """Generate the tiny CI profile once per test session."""
    out = tmp_path_factory.mktemp("raw")
    tables = generate(GeneratorConfig(seed=42, profile="ci", out_dir=out), log=lambda *_: None)
    return out, tables


@pytest.fixture(scope="session")
def con(ci_data):
    out, _ = ci_data
    c = duckdb.connect()
    for p in out.glob("*.parquet"):
        c.execute(f"create view {p.stem} as select * from '{p}'")
    return c
