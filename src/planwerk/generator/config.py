"""Static configuration of the simulated Nordwerk group.

Everything in here is fictional. Numbers are calibrated so that the dev profile
(scale=1.0) produces a mid-sized German machine builder with roughly EUR 250 M
revenue, about 1,100 employees and three company codes (DE, AT, PL).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
DRIVER_DIR = REPO_ROOT / "data" / "drivers"

CLIENT = "100"
LEDGER = "0L"
CONTROLLING_AREA = "NW00"
GROUP_CURRENCY = "EUR"
FIRST_PERIOD = "2023-01"
LAST_PERIOD = "2025-12"

# --------------------------------------------------------------------------------------
# Company codes (T001) and plants (T001W)
# --------------------------------------------------------------------------------------
COMPANY_CODES = {
    "1000": dict(name="Nordwerk GmbH", country="DE", currency="EUR", city="Bremen",
                 plant="1000", share=0.70, price_level=1.00, vat=0.19),
    "2000": dict(name="Nordwerk Austria GmbH", country="AT", currency="EUR", city="Linz",
                 plant="2000", share=0.12, price_level=1.02, vat=0.20),
    "3000": dict(name="Nordwerk Polska Sp. z o.o.", country="PL", currency="PLN", city="Poznań",
                 plant="3000", share=0.18, price_level=0.85, vat=0.23),
}

# --------------------------------------------------------------------------------------
# Product groups (MATKL) and contribution-margin structure
# --------------------------------------------------------------------------------------
# revenue_share: share of group revenue; material_ratio: standard material cost / net price
# qty_mean: mean quantity per order item; lead: probability of billing 0..3 months after order
PRODUCT_GROUPS = {
    "PG10": dict(name="Kreiselpumpen", mtart="FERT", n=40, price=(1800, 14000), revenue_share=0.35,
                 material_ratio=0.46, qty_mean=2.0, lead=(0.30, 0.45, 0.20, 0.05), unit="ST"),
    "PG20": dict(name="Dosierpumpen", mtart="FERT", n=25, price=(900, 6000), revenue_share=0.20,
                 material_ratio=0.34, qty_mean=3.0, lead=(0.35, 0.45, 0.15, 0.05), unit="ST"),
    "PG30": dict(name="Ventile und Armaturen", mtart="FERT", n=50, price=(150, 3500), revenue_share=0.20,
                 material_ratio=0.50, qty_mean=6.0, lead=(0.50, 0.40, 0.10, 0.00), unit="ST"),
    "PG40": dict(name="Ersatzteile", mtart="HAWA", n=300, price=(8, 900), revenue_share=0.15,
                 material_ratio=0.44, qty_mean=8.0, lead=(1.0, 0.0, 0.0, 0.0), unit="ST"),
    "PG50": dict(name="Service", mtart="DIEN", n=4, price=(95, 140), revenue_share=0.10,
                 material_ratio=0.0, qty_mean=8.0, lead=(1.0, 0.0, 0.0, 0.0), unit="H"),
}
SERVICE_MATERIALS = ["Inbetriebnahme", "Wartung", "Reparatur", "Schulung"]

# Raw material classes and the real price index that drives them
COMPONENT_CLASSES = {
    "STAHL": dict(name="Guss- und Stahlteile", n=30, price=(4, 180), driver="ppi_basic_metals"),
    "KUNST": dict(name="Dichtungen und Kunststoffteile", n=20, price=(1, 45), driver="ppi_rubber_plastics"),
    "ELEK": dict(name="Motoren und Elektronik", n=25, price=(40, 1600), driver="ppi_machinery"),
}
TRADING_GOODS_DRIVER = "ppi_machinery"

# Customer segments (KDGRP): share of customers, typical discount, product-group affinity
SEGMENTS = {
    "01": dict(name="OEM / Anlagenbauer", customer_share=0.15, discount=0.16,
               affinity=dict(PG10=1.6, PG20=1.4, PG30=0.8, PG40=0.5, PG50=0.4)),
    "02": dict(name="Industrie", customer_share=0.40, discount=0.08,
               affinity=dict(PG10=1.0, PG20=1.2, PG30=1.0, PG40=1.0, PG50=1.2)),
    "03": dict(name="Kommunal / Wasserwirtschaft", customer_share=0.20, discount=0.05,
               affinity=dict(PG10=1.3, PG20=0.6, PG30=1.2, PG40=0.8, PG50=1.6)),
    "04": dict(name="Handel", customer_share=0.25, discount=0.24,
               affinity=dict(PG10=0.5, PG20=0.6, PG30=1.1, PG40=1.6, PG50=0.1)),
}
CUSTOMERS_PER_COMPANY = {"1000": 900, "2000": 180, "3000": 300}
VENDORS_PER_COMPANY = {"1000": 220, "2000": 60, "3000": 90}

# Payment terms (ZTERM): days net, cash-discount days, cash-discount rate
PAYMENT_TERMS = {
    "Z030": dict(net=30, skonto_days=0, skonto=0.0),
    "Z014": dict(net=30, skonto_days=14, skonto=0.02),
    "Z060": dict(net=60, skonto_days=0, skonto=0.0),
}

# Order-intake seasonality (sums to 12)
SEASONALITY = np.array([0.85, 0.92, 1.08, 0.98, 1.00, 1.06, 0.98, 0.80, 1.05, 1.03, 1.07, 1.18])

# Underlying volume level per year (German industrial weakness 2024/25)
YEAR_VOLUME = {2023: 1.00, 2024: 0.96, 2025: 0.97}

# Price list increases effective 1 January (actual realised)
PRICE_INCREASE = {
    2023: dict(PG10=0.070, PG20=0.065, PG30=0.070, PG40=0.080, PG50=0.060),
    2024: dict(PG10=0.030, PG20=0.030, PG30=0.035, PG40=0.040, PG50=0.035),
    2025: dict(PG10=0.015, PG20=0.030, PG30=0.030, PG40=0.040, PG50=0.035),
}

# --------------------------------------------------------------------------------------
# Chart of accounts (own operating chart "NWKR", SKR04-inspired)
# --------------------------------------------------------------------------------------
# kind: P = profit and loss primary, B = balance sheet, S = secondary cost element
# gkv:  line of the HGB § 275 (2) total cost format the account maps to
# cm:   contribution-margin block (REV, VAR, FIX)
ACCOUNTS = {
    "400000": dict(text="Umsatzerlöse Inland", kind="P", gkv="01_UMSATZ", cm="REV"),
    "401000": dict(text="Umsatzerlöse EU", kind="P", gkv="01_UMSATZ", cm="REV"),
    "402000": dict(text="Umsatzerlöse Drittland", kind="P", gkv="01_UMSATZ", cm="REV"),
    "405000": dict(text="Umsatzerlöse Service", kind="P", gkv="01_UMSATZ", cm="REV"),
    "409000": dict(text="Erlösschmälerungen (Skonti)", kind="P", gkv="01_UMSATZ", cm="REV"),
    "480000": dict(text="Bestandsveränderungen fertige Erzeugnisse", kind="P", gkv="02_BESTAND", cm="VAR"),
    "500000": dict(text="Aufwand Guss- und Stahlteile", kind="P", gkv="05A_MATERIAL_RHB", cm="VAR"),
    "501000": dict(text="Aufwand Dichtungen und Kunststoffteile", kind="P", gkv="05A_MATERIAL_RHB", cm="VAR"),
    "502000": dict(text="Aufwand Motoren und Elektronik", kind="P", gkv="05A_MATERIAL_RHB", cm="VAR"),
    "503000": dict(text="Aufwand Handelswaren", kind="P", gkv="05A_MATERIAL_RHB", cm="VAR"),
    "520000": dict(text="Energie (Strom)", kind="P", gkv="05A_MATERIAL_RHB", cm="FIX"),
    "530000": dict(text="Fremdleistungen", kind="P", gkv="05B_MATERIAL_LEIST", cm="FIX"),
    "600000": dict(text="Löhne", kind="P", gkv="06A_PERSONAL_LOHN", cm="FIX"),
    "601000": dict(text="Gehälter", kind="P", gkv="06A_PERSONAL_LOHN", cm="FIX"),
    "640000": dict(text="Soziale Abgaben", kind="P", gkv="06B_PERSONAL_SOZIAL", cm="FIX"),
    "680000": dict(text="Abschreibungen auf Sachanlagen", kind="P", gkv="07_ABSCHREIBUNG", cm="FIX"),
    "700000": dict(text="Miete und Raumkosten", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "701000": dict(text="Instandhaltung durch Dritte", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "702000": dict(text="Ausgangsfrachten", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "703000": dict(text="Reisekosten", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "704000": dict(text="Werbung und Messen", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "705000": dict(text="IT und Software", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "706000": dict(text="Rechts- und Beratungskosten", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "707000": dict(text="Versicherungen", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "709000": dict(text="Sonstige betriebliche Aufwendungen", kind="P", gkv="08_SONST_BETR_AUFW", cm="FIX"),
    "760000": dict(text="Erträge und Aufwendungen aus Kursdifferenzen", kind="P", gkv="08_SONST_BETR_AUFW", cm="OTH"),
    "750000": dict(text="Zinsen und ähnliche Aufwendungen", kind="P", gkv="13_ZINSAUFWAND", cm="FIN"),
    "770000": dict(text="Steuern vom Einkommen und Ertrag", kind="P", gkv="14_STEUERN_EE", cm="TAX"),
    # balance sheet
    "100000": dict(text="Roh-, Hilfs- und Betriebsstoffe", kind="B", gkv="", cm=""),
    "101000": dict(text="Fertige Erzeugnisse und Waren", kind="B", gkv="", cm=""),
    "120000": dict(text="Forderungen aus Lieferungen und Leistungen", kind="B", gkv="", cm=""),
    "140000": dict(text="Vorsteuer", kind="B", gkv="", cm=""),
    "180000": dict(text="Bank", kind="B", gkv="", cm=""),
    "330000": dict(text="Verbindlichkeiten aus Lieferungen und Leistungen", kind="B", gkv="", cm=""),
    "350000": dict(text="WE/RE-Verrechnung", kind="B", gkv="", cm=""),
    "370000": dict(text="Verbindlichkeiten Lohn und Gehalt", kind="B", gkv="", cm=""),
    "380000": dict(text="Umsatzsteuer", kind="B", gkv="", cm=""),
    "039000": dict(text="Kumulierte Abschreibungen", kind="B", gkv="", cm=""),
    "390000": dict(text="Sonstige Verbindlichkeiten / Rückstellungen", kind="B", gkv="", cm=""),
    "290000": dict(text="Eigenkapital (Gewinnvortrag, Ausschüttungen)", kind="B", gkv="", cm=""),
}
COMPONENT_ACCOUNT = {"STAHL": "500000", "KUNST": "501000", "ELEK": "502000", "HAWA": "503000"}

# --------------------------------------------------------------------------------------
# Cost centres (CSKS). level: DB2 = production-related fixed cost, DB3 = area fixed cost
# (sales, service, logistics), UNT = corporate fixed cost, HILF = service cost centre that
# is allocated in the BAB. hc = headcount at scale 1, wage = monthly personnel cost per
# head (EUR, 2023), blue = share of wage earners (Löhne) vs salaried (Gehälter).
# --------------------------------------------------------------------------------------
COST_CENTRES = [
    # Germany
    ("1000", "1100", "Geschäftsführung", "UNT", 6, 14500, 0.0),
    ("1000", "1110", "Finanzen und Controlling", "UNT", 18, 6400, 0.0),
    ("1000", "1120", "Personal", "UNT", 9, 5800, 0.0),
    ("1000", "1130", "IT", "HILF", 16, 6900, 0.0),
    ("1000", "1200", "Forschung und Entwicklung", "UNT", 42, 7100, 0.1),
    ("1000", "1300", "Einkauf und Materialwirtschaft", "DB2", 24, 5200, 0.3),
    ("1000", "1400", "Energieversorgung", "HILF", 4, 5300, 0.8),
    ("1000", "1410", "Instandhaltung", "HILF", 28, 4900, 0.9),
    ("1000", "1500", "Fertigung Pumpen", "DB2", 190, 4400, 0.92),
    ("1000", "1510", "Fertigung Ventile", "DB2", 95, 4300, 0.92),
    ("1000", "1520", "Mechanische Fertigung", "DB2", 120, 4600, 0.92),
    ("1000", "1530", "Qualitätssicherung", "DB2", 22, 5100, 0.4),
    ("1000", "1600", "Vertrieb Inland", "DB3", 34, 6200, 0.0),
    ("1000", "1610", "Vertrieb Export", "DB3", 21, 6500, 0.0),
    ("1000", "1620", "Marketing", "DB3", 9, 5900, 0.0),
    ("1000", "1700", "Service", "DB3", 70, 5000, 0.7),
    ("1000", "1800", "Logistik und Versand", "DB3", 38, 4100, 0.85),
    # Austria
    ("2000", "2100", "Geschäftsführung und Verwaltung", "UNT", 9, 7600, 0.0),
    ("2000", "2400", "Energieversorgung", "HILF", 1, 5200, 1.0),
    ("2000", "2500", "Fertigung", "DB2", 62, 4500, 0.9),
    ("2000", "2600", "Vertrieb", "DB3", 10, 6300, 0.0),
    ("2000", "2700", "Service", "DB3", 16, 5000, 0.7),
    ("2000", "2800", "Logistik und Versand", "DB3", 8, 4100, 0.8),
    # Poland
    ("3000", "3100", "Zarząd i administracja", "UNT", 14, 3600, 0.0),
    ("3000", "3400", "Energieversorgung", "HILF", 2, 2300, 1.0),
    ("3000", "3410", "Instandhaltung", "HILF", 9, 2100, 0.9),
    ("3000", "3500", "Fertigung", "DB2", 140, 1900, 0.93),
    ("3000", "3520", "Mechanische Fertigung", "DB2", 46, 2000, 0.93),
    ("3000", "3600", "Vertrieb", "DB3", 13, 3100, 0.0),
    ("3000", "3700", "Service", "DB3", 18, 2300, 0.7),
    ("3000", "3800", "Logistik und Versand", "DB3", 11, 1800, 0.85),
]

# Cost centre that receives production consumption and production confirmations per
# company code and product group
PRODUCTION_CC = {
    ("1000", "PG10"): "1500", ("1000", "PG20"): "1500", ("1000", "PG30"): "1510",
    ("2000", "PG10"): "2500", ("2000", "PG20"): "2500", ("2000", "PG30"): "2500",
    ("3000", "PG10"): "3500", ("3000", "PG20"): "3500", ("3000", "PG30"): "3500",
}
TRADING_CC = {"1000": "1300", "2000": "2800", "3000": "3800"}
SALES_CC = {"1000": "1600", "2000": "2600", "3000": "3600"}
EXPORT_CC = {"1000": "1610", "2000": "2600", "3000": "3600"}
SERVICE_CC = {"1000": "1700", "2000": "2700", "3000": "3700"}
LOGISTICS_CC = {"1000": "1800", "2000": "2800", "3000": "3800"}

# Fictional managers (VERAK). Changes over time create SCD2 history.
MANAGERS = [
    "M. Albers", "K. Brandt", "S. Celik", "T. Dąbrowski", "J. Ehlers", "A. Fischer", "L. Gruber",
    "R. Hoffmann", "N. Iwanowa", "P. Jansen", "C. Kowalska", "D. Lindner", "E. Moser", "F. Nowak",
    "G. Ostermann", "H. Petersen", "I. Quast", "U. Riedel", "V. Schulz", "W. Thiele", "Y. Unger",
    "Z. Vogt", "B. Wagner", "O. Zimmer", "Ł. Wiśniewski", "K. Steiner", "M. Huber", "J. Kamiński",
    "A. Wójcik", "S. Bauer", "T. Lehmann",
]

# Statistical key figures for the BAB (allocation keys)
# energy: MWh per month at scale 1, maint: machine hours share, IT by headcount
ENERGY_MWH = {"1000": 2350.0, "2000": 330.0, "3000": 900.0}
ENERGY_HEDGE_SHARE = 0.70
ENERGY_GRID_FEES = 62.0  # EUR/MWh grid fees, levies and taxes for industrial customers

# Contract prices of the hedged share (signed in prior autumn), EUR/MWh
ENERGY_HEDGE_PRICE = {2023: 185.0, 2024: 118.0, 2025: 92.0}


@dataclass(frozen=True)
class Profile:
    name: str
    scale: float
    description: str


PROFILES = {
    "ci": Profile("ci", 0.05, "Tiny, for unit tests and CI (~100 k journal lines)"),
    "dev": Profile("dev", 1.0, "Mid-sized machine builder, ~EUR 250 M revenue (~2 M journal lines)"),
    "full": Profile("full", 15.0, "Large multi-plant group (~30 M journal lines)"),
}


@dataclass
class GeneratorConfig:
    seed: int = 42
    profile: str = "dev"
    first_period: str = FIRST_PERIOD
    last_period: str = LAST_PERIOD
    out_dir: Path = field(default_factory=lambda: REPO_ROOT / "data" / "raw")

    @property
    def scale(self) -> float:
        return PROFILES[self.profile].scale

    def rng(self, name: str) -> np.random.Generator:
        """Independent, stable random stream per module/purpose."""
        return np.random.default_rng([self.seed, zlib.crc32(name.encode())])
