"""Ground truth of injected effects: expected impact on fiscal-year DB I / DB II in EUR.

For each effect the expected-value model is evaluated with and without that single effect
(all else equal). The difference is the "true" size the variance analysis should recover.
"""

from __future__ import annotations

import copy

import pandas as pd

from planwerk.generator import aggregate as A
from planwerk.generator.masterdata import MasterData
from planwerk.generator.scenario import Scenario


def _year_totals(md: MasterData, drivers: pd.DataFrame, s: Scenario, scale: float, year: int,
                 company_code: str | None = None) -> dict[str, float]:
    m = A.monthly_db(md, drivers, s, scale)
    m = m[m["PERIOD"].str[:4] == str(year)]
    return {k: float(m[k].sum()) for k in ("REVENUE", "DB1", "DB2", "DB3", "EBIT")}


def compute_ground_truth(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float) -> dict:
    y = scenario.target_year
    base = _year_totals(md, drivers, scenario, scale, y)
    plan = A.monthly_db(md, drivers, scenario, scale, plan_year=y)
    plan_tot = {k: float(plan[k].sum()) for k in ("REVENUE", "DB1", "DB2", "DB3", "EBIT")}
    effects = []

    def variant(name: str, category: str, mutate, description: str, scope: dict):
        s = copy.deepcopy(scenario)
        mutate(s)
        alt = _year_totals(md, drivers, s, scale, y)
        effects.append(dict(effect=name, category=category, description=description, scope=scope,
                            impact_revenue_eur=round(base["REVENUE"] - alt["REVENUE"], 2),
                            impact_db1_eur=round(base["DB1"] - alt["DB1"], 2),
                            impact_db2_eur=round(base["DB2"] - alt["DB2"], 2)))

    plan_pg10 = scenario.price_increase_plan[y]["PG10"]

    def m_price(s: Scenario):
        s.price_increase_actual[y]["PG10"] = plan_pg10
    variant("price_pg10", "price", m_price,
            f"Preiserhöhung Kreiselpumpen {scenario.price_increase_actual[y]['PG10']:.1%} statt geplant {plan_pg10:.1%}",
            dict(product_group="PG10"))

    def m_vol(s: Scenario):
        s.year_volume_actual[y] = scenario.year_volume_plan[y]
    variant("volume_level", "volume", m_vol,
            f"Marktvolumen {scenario.year_volume_actual[y]:.2f} statt geplant {scenario.year_volume_plan[y]:.2f}",
            dict())
    for i, loss in enumerate(scenario.customer_losses):
        def m_loss(s: Scenario, i=i):
            s.customer_losses = [x for j, x in enumerate(s.customer_losses) if j != i]
        variant(f"customer_loss_{loss.company_code}_{loss.segment}", "volume", m_loss, loss.description,
                dict(company_code=loss.company_code, segment=loss.segment, from_period=loss.start_period,
                     kunnr=loss.kunnr))
    if scenario.demand_shifts:
        def m_mix(s: Scenario):
            s.demand_shifts = []
        variant("demand_shift", "mix", m_mix, "; ".join(d.description for d in scenario.demand_shifts),
                dict(shifts=[dict(company_code=d.company_code, product_group=d.product_group, factor=d.factor,
                                  from_period=d.start_period) for d in scenario.demand_shifts]))
    for i, oc in enumerate(scenario.one_off_costs):
        def m_oc(s: Scenario, i=i):
            s.one_off_costs = [x for j, x in enumerate(s.one_off_costs) if j != i]
        variant(f"one_off_{oc.cost_centre}_{oc.period}", "fixed_cost", m_oc, oc.description,
                dict(company_code=oc.company_code, cost_centre=oc.cost_centre, account=oc.account,
                     period=oc.period, amount_eur=oc.amount_eur * scale))
    return dict(
        target_year=y, scale=scale,
        expected_actual=base, plan=plan_tot,
        expected_gap_db2_eur=round(base["DB2"] - plan_tot["DB2"], 2),
        effects=effects,
        note=("Impacts are expected values (no noise) at actual FX. Remaining gap not covered by the "
              "listed effects comes from real driver paths (material prices, wages, energy, FX) versus "
              "plan assumptions."),
    )
