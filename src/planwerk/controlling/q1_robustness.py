"""Exploratory robustness check for Q1 (not part of the pre-registered criteria in ADR-0001).

Re-runs generator, dbt and the Q1 evaluation for further seeds and collects which injected
effects are recovered in each realisation. It answers *why* an effect is or is not recovered;
it never changes the verdict on H1, which is fixed on the main scenario (seed 42).

    python -m planwerk.controlling.q1_robustness --seeds 7 123 2024 31415
    python -m planwerk.controlling.q1_robustness --collect-only     # only aggregate existing runs
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from planwerk.generator.config import REPO_ROOT

EXPLORE = REPO_ROOT / "data" / "explore"
OUT = REPO_ROOT / "docs" / "ergebnisse" / "q1_robustness.json"


def run_seed(seed: int, noise_level: float = 1.0) -> Path:
    d = EXPLORE / (f"seed{seed}" if noise_level == 1.0 else f"seed{seed}_noise{noise_level:g}")
    env = {**os.environ, "PLANWERK_RAW": str(d / "raw"), "PLANWERK_DUCKDB": str(d / "planwerk.duckdb")}
    py = sys.executable
    subprocess.run([py, "-m", "planwerk.generator.run", "--seed", str(seed), "--noise-level", str(noise_level),
                    "--out", str(d / "raw")], check=True, env=env)
    subprocess.run(["dbt", "build", "--project-dir", str(REPO_ROOT / "dbt"), "--profiles-dir", str(REPO_ROOT / "dbt"),
                    "--target-path", str(d / "target"), "--log-path", str(d / "logs")], check=False, env=env)
    subprocess.run([py, "-m", "planwerk.controlling.q1_evaluation", "--raw", str(d / "raw"),
                    "--out", str(d / "q1.json")], check=True, env=env)
    return d / "q1.json"


def collect(main_result: Path = REPO_ROOT / "docs" / "ergebnisse" / "q1_evaluation.json") -> dict:
    runs = []
    sources = [("seed42 (main)", main_result)] + [(p.parent.name, p) for p in sorted(EXPLORE.glob("*/q1.json"))]
    for name, p in sources:
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        runs.append(dict(run=name,
                         gap_db2_eur=r["gap_db2_eur"],
                         revenue_realisation_vs_expected=r["realisation"]["revenue_realisation_vs_expected"],
                         bridge_closes=r["criteria"]["c1_bridge_closes"],
                         cost_centre_coverage=r["criteria"]["c3_cost_centre_coverage"],
                         effects={e["effect"]: dict(injected=e["injected_eur"], measured=e["measured_eur"],
                                                    recovered=e["recovered"]) for e in r["recovery"]}))
    names = sorted({k for r in runs for k in r["effects"]})
    summary = {n: f"{sum(r['effects'][n]['recovered'] for r in runs if n in r['effects'])}/"
                  f"{sum(n in r['effects'] for r in runs)}" for n in names}
    return dict(note="Exploratory, not pre-registered. The H1 verdict stays as in q1_evaluation.json.",
                runs=runs, recovered_per_effect=summary)


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[7, 123, 2024, 31415])
    ap.add_argument("--noise-level", type=float, default=1.0)
    ap.add_argument("--collect-only", action="store_true")
    a = ap.parse_args(argv)
    if not a.collect_only:
        for s in a.seeds:
            run_seed(s, a.noise_level)
    res = collect()
    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    for r in res["runs"]:
        flags = " ".join(f"{k.split()[0]}={'OK' if v['recovered'] else 'miss'}" for k, v in r["effects"].items())
        print(f"{r['run']:<22} realisation {r['revenue_realisation_vs_expected']:+.2%}  {flags}")
    print(res["recovered_per_effect"])
    return res


if __name__ == "__main__":
    main()
