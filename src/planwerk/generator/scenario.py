"""Scenario definition: the effects the generator injects, and the plan assumptions.

The *main* scenario is the one documented in the Fachkonzept and analysed in the
reports. ``random_scenario`` draws variations of it for the forecast backtest (Q2).
Every injected effect ends up in ``ground_truth.json`` next to the generated tables.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

import numpy as np

from planwerk.generator.config import PRICE_INCREASE, YEAR_VOLUME


@dataclass
class CustomerLoss:
    company_code: str
    segment: str
    factor: float          # share of the customer's orders that remain (0.1 = 90 % lost)
    start_period: str
    description: str
    kunnr: str | None = None  # resolved from master data (largest customer in the segment)


@dataclass
class DemandShift:
    company_code: str | None  # None = all company codes
    product_group: str | None  # None = all product groups
    factor: float
    start_period: str
    description: str


@dataclass
class OneOffCost:
    company_code: str
    cost_centre: str
    account: str
    period: str
    amount_eur: float
    description: str


@dataclass
class Scenario:
    name: str = "main"
    target_year: int = 2025
    # actual list-price increases per year and product group
    price_increase_actual: dict = field(default_factory=lambda: copy.deepcopy(PRICE_INCREASE))
    # what the plan assumed (only differs where the controller was wrong)
    price_increase_plan: dict = field(default_factory=lambda: {
        2023: dict(PG10=0.070, PG20=0.065, PG30=0.070, PG40=0.080, PG50=0.060),
        2024: dict(PG10=0.035, PG20=0.030, PG30=0.035, PG40=0.040, PG50=0.035),
        2025: dict(PG10=0.040, PG20=0.030, PG30=0.030, PG40=0.040, PG50=0.035),
    })
    year_volume_actual: dict = field(default_factory=lambda: dict(YEAR_VOLUME))
    year_volume_plan: dict = field(default_factory=lambda: {2023: 1.01, 2024: 0.99, 2025: 0.98})
    customer_losses: list = field(default_factory=lambda: [
        CustomerLoss("2000", "03", 0.10, "2025-04",
                     "Rahmenvertrag mit größtem Kommunalkunden in Österreich verloren (Ausschreibung)"),
    ])
    demand_shifts: list = field(default_factory=lambda: [
        DemandShift("1000", "PG20", 0.85, "2025-03",
                    "Kunden wechseln von Dosierpumpen zu günstigeren Kreiselpumpen-Lösungen"),
        DemandShift("1000", "PG10", 1.08, "2025-03",
                    "Mehrnachfrage Kreiselpumpen als Ersatz für Dosierpumpen"),
    ])
    one_off_costs: list = field(default_factory=lambda: [
        OneOffCost("1000", "1410", "701000", "2025-06", 450_000.0,
                   "Außerplanmäßige Reparatur Pumpenprüfstand durch Fremdfirma"),
    ])
    # cost-side plan assumptions
    component_price_change_plan: dict = field(default_factory=lambda: {2023: 0.03, 2024: 0.00, 2025: 0.01})
    wage_increase_plan: dict = field(default_factory=lambda: {2023: 0.050, 2024: 0.045, 2025: 0.035})
    overhead_inflation_plan: dict = field(default_factory=lambda: {2023: 0.05, 2024: 0.03, 2025: 0.025})
    energy_spot_plan: dict = field(default_factory=lambda: {2023: 160.0, 2024: 95.0, 2025: 90.0})
    fx_plan_eur_pln: dict = field(default_factory=lambda: {2023: 4.75, 2024: 4.45, 2025: 4.35})
    noise_level: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def main_scenario() -> Scenario:
    return Scenario()


def random_scenario(index: int, base_seed: int = 7) -> Scenario:
    """Variation of the main scenario for the Q2 backtest.

    Roughly half of the draws end up missing the DB II target by more than 2 %.
    """
    rng = np.random.default_rng([base_seed, index])
    s = Scenario(name=f"bt{index:03d}")
    s.price_increase_actual = copy.deepcopy(PRICE_INCREASE)
    pg10 = float(rng.uniform(0.0, 0.05))
    s.price_increase_actual[2025]["PG10"] = pg10
    s.year_volume_actual = dict(YEAR_VOLUME)
    s.year_volume_actual[2025] = float(rng.uniform(0.94, 1.03))
    start_shift = int(rng.integers(2, 11))
    shift = float(rng.uniform(0.80, 1.08))
    s.demand_shifts = [
        DemandShift(None, None, shift, f"2025-{start_shift:02d}", "Nachfrageschock (Backtest)"),
    ]
    if rng.random() < 0.5:
        start_loss = int(rng.integers(2, 11))
        s.customer_losses = [CustomerLoss("2000", "03", float(rng.uniform(0.0, 0.6)),
                                          f"2025-{start_loss:02d}", "Kundenverlust (Backtest)")]
    else:
        s.customer_losses = []
    s.one_off_costs = []
    if rng.random() < 0.3:
        m = int(rng.integers(3, 12))
        s.one_off_costs = [OneOffCost("1000", "1410", "701000", f"2025-{m:02d}",
                                      float(rng.uniform(1e5, 1.2e6)), "Einmalkosten (Backtest)")]
    return s
