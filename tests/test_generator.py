"""Generator invariants: accounting correctness, referential integrity, determinism, scenario."""

from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from planwerk.generator import config as C
from planwerk.generator.config import GeneratorConfig
from planwerk.generator.run import generate


def test_every_document_balances_in_all_currencies(con):
    bad = con.execute("""
        select rbukrs, gjahr, belnr from acdoca group by all
        having abs(sum(tsl)) > 0.005 or abs(sum(hsl)) > 0.005 or abs(sum(ksl)) > 0.005
    """).fetchall()
    assert bad == []


def test_bkpf_and_acdoca_agree(con):
    assert con.execute("select count(*) from bkpf").fetchone()[0] == con.execute(
        "select count(distinct (rbukrs, gjahr, belnr)) from acdoca").fetchone()[0]
    orphan = con.execute("""select count(*) from acdoca a anti join bkpf b
                        on a.rbukrs = b.bukrs and a.gjahr = b.gjahr and a.belnr = b.belnr""").fetchone()[0]
    assert orphan == 0


def test_document_numbers_unique_and_ten_digits(con):
    dup = con.execute("select bukrs, gjahr, belnr, count(*) n from bkpf group by all having n > 1").fetchall()
    assert dup == []
    assert con.execute("select min(length(belnr)), max(length(belnr)) from bkpf").fetchone() == (10, 10)


def test_posting_dates_inside_window(con):
    lo, hi = con.execute("select min(budat), max(budat) from acdoca").fetchone()
    assert str(lo) >= "2023-01-01" and str(hi) <= "2025-12-31"


def test_debit_credit_indicator_matches_sign(con):
    n = con.execute("select count(*) from acdoca where (drcrk = 'S' and hsl < 0) or (drcrk = 'H' and hsl > 0)").fetchone()[0]
    assert n == 0


def test_accounts_exist_in_chart(con):
    n = con.execute("select count(*) from acdoca a anti join ska1 s on a.racct = s.saknr").fetchone()[0]
    assert n == 0
    n = con.execute("select count(*) from acdocp p anti join ska1 s on p.racct = s.saknr").fetchone()[0]
    assert n == 0


def test_cost_centres_valid_at_posting_date(con):
    n = con.execute("""
        select count(*) from acdoca a
        where a.rcntr <> '' and not exists (
            select 1 from csks c where c.kostl = a.rcntr
              and cast(a.budat as varchar) between c.datab and c.datbi)
    """).fetchone()[0]
    assert n == 0


def test_invoice_items_reference_order_items(con):
    n = con.execute("""select count(*) from vbrp r anti join vbap p
                   on r.aubel = p.vbeln and r.aupos = p.posnr""").fetchone()[0]
    assert n == 0


def test_revenue_in_journal_equals_billing(con):
    j = con.execute("select -sum(hsl) from acdoca where racct in ('400000', '405000')").fetchone()[0]
    b = con.execute("select sum(netwr) from vbrp").fetchone()[0]
    assert j == pytest.approx(b, abs=0.05)


def test_cleared_items_net_to_zero(con):
    """Each cleared open item (AR/AP) and its clearing line offset in local currency."""
    bad = con.execute("""
        select rbukrs, augbl, left(cast(augdt as varchar), 4) augyr, racct, sum(hsl) s from acdoca
        where augbl <> '' and racct in ('120000', '330000')
        group by all having abs(s) > 0.005
    """).fetchall()
    assert bad == []


def test_open_items_exist_at_year_end(con):
    """Unpaid invoices at 31.12.2025 feed the 13-week liquidity forecast."""
    n_ar = con.execute("select count(*) from acdoca where racct = '120000' and augbl = ''").fetchone()[0]
    n_ap = con.execute("select count(*) from acdoca where racct = '330000' and augbl = ''").fetchone()[0]
    assert n_ar > 0 and n_ap > 0
    late = con.execute("select min(netdt) from acdoca where racct = '120000' and augbl = ''").fetchone()[0]
    assert late is not None


def test_production_orders_have_consumption(con):
    n = con.execute("""select count(*) from afko f anti join acdoca a
                   on a.aufnr = f.aufnr and a.blart = 'WA'""").fetchone()[0]
    assert n == 0


def test_material_ratio_is_plausible(con):
    """Variable material cost / revenue for finished goods between 30 % and 55 %."""
    r = con.execute("""
        with rev as (select sum(-hsl) r from acdoca where racct = '400000' and matkl_mm in ('PG10','PG20','PG30')),
             mat as (select sum(hsl) m from acdoca where blart = 'WA' and racct like '50%')
        select m / r from rev, mat
    """).fetchone()[0]
    assert 0.30 < r < 0.55


def test_group_scale_matches_profile(con):
    """CI profile is 5 % of the EUR 250 M dev company."""
    rev = con.execute("select -sum(ksl) from acdoca where racct like '40%' and gjahr = '2023'").fetchone()[0]
    assert 0.8 * 12.5e6 < rev < 1.2 * 12.5e6


def test_pl_amounts_use_ecb_rates(con):
    rate = con.execute("""select sum(hsl) / sum(ksl) from acdoca
                      where rbukrs = '3000' and racct = '400000' and poper = '006' and gjahr = '2025'""").fetchone()[0]
    assert rate == pytest.approx(4.2658, rel=1e-3)  # ECB EUR/PLN June 2025 monthly average


def test_scd2_history_in_cost_centres(con):
    versions = dict(con.execute("select kostl, count(*) from csks group by 1 having count(*) > 1").fetchall())
    assert set(versions) == {"1520", "1610", "2600"}
    assert con.execute("select datab from csks where kostl = '1630'").fetchone()[0] == "2024-04-01"


def test_plan_covers_three_years_and_all_company_codes(con):
    rows = con.execute("select ryear, count(distinct rbukrs) from acdocp group by 1 order by 1").fetchall()
    assert rows == [("2023", 3), ("2024", 3), ("2025", 3)]


def test_plan_has_quantities_for_revenue(con):
    n = con.execute("select count(*) from acdocp where racct in ('400000','405000') and msl = 0").fetchone()[0]
    assert n == 0


def test_master_data_quality_findings_are_present(con):
    """The MDG-style checks must have something to find (documented, deliberate)."""
    assert con.execute("select count(*) from kna1 where stceg = ''").fetchone()[0] >= 1
    assert con.execute("select count(*) from (select name1, ort01 from kna1 group by all having count(*) > 1)").fetchone()[0] >= 1


def test_ground_truth_effects_have_expected_sign(ci_data):
    out, _ = ci_data
    gt = json.loads((out / "ground_truth.json").read_text())
    eff = {e["effect"]: e for e in gt["effects"]}
    assert eff["price_pg10"]["impact_db2_eur"] < 0
    assert eff["customer_loss_2000_03"]["impact_db2_eur"] < 0
    assert eff["one_off_1410_2025-06"]["impact_db2_eur"] == pytest.approx(-450_000 * 0.05, rel=1e-6)
    assert gt["expected_gap_db2_eur"] < 0


def test_manifest_labels_data_as_simulated(ci_data):
    out, _ = ci_data
    m = json.loads((out / "manifest.json").read_text())
    assert "SIMULIERT" in m["label"] and m["seed"] == 42 and m["profile"] == "ci"


def _digest(tables: dict) -> str:
    h = hashlib.sha256()
    for name in ("ACDOCA", "ACDOCP", "VBRP", "KNA1"):
        df = tables[name]
        h.update(pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes())
    return h.hexdigest()


def test_generator_is_deterministic(ci_data, tmp_path):
    _, t1 = ci_data
    t2 = generate(GeneratorConfig(seed=42, profile="ci", out_dir=tmp_path), write=False, log=lambda *_: None)
    assert _digest(t1) == _digest(t2)


def test_different_seed_changes_data(ci_data, tmp_path):
    _, t1 = ci_data
    t3 = generate(GeneratorConfig(seed=7, profile="ci", out_dir=tmp_path), write=False, log=lambda *_: None)
    assert _digest(t1) != _digest(t3)


def test_profiles_are_defined():
    assert set(C.PROFILES) == {"ci", "dev", "full"}
