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


@pytest.fixture(scope="session")
def warehouse(ci_data, tmp_path_factory):
    """Build the full dbt warehouse on the CI data, then forecast and liquidity, in a temp DuckDB."""
    import os
    import subprocess

    from planwerk.generator.config import REPO_ROOT

    out, _ = ci_data
    db = tmp_path_factory.mktemp("wh") / "planwerk_ci.duckdb"
    env = {**os.environ, "PLANWERK_RAW": str(out), "PLANWERK_DUCKDB": str(db), "PLANWERK_TARGET": "duckdb"}
    flags = ["--project-dir", str(REPO_ROOT / "dbt"), "--profiles-dir", str(REPO_ROOT / "dbt"),
             "--target-path", str(tmp_path_factory.mktemp("dbt_target"))]
    for cmd in (["dbt", "seed", *flags], ["dbt", "build", *flags]):
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-4000:]
    old = os.environ.get("PLANWERK_DUCKDB")
    os.environ["PLANWERK_DUCKDB"] = str(db)
    from planwerk.controlling import liquidity
    from planwerk.forecast import rolling

    rolling.main()
    liquidity.main(["--out", str(tmp_path_factory.mktemp("reports"))])
    yield db
    if old is None:
        os.environ.pop("PLANWERK_DUCKDB", None)
    else:
        os.environ["PLANWERK_DUCKDB"] = old


@pytest.fixture(scope="session")
def wcon(warehouse):
    c = duckdb.connect(str(warehouse), read_only=True)
    yield c
    c.close()
