"""Load and parse candidate parts from the passives DB built by `update`."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .footprints import CHIP, package_area
from .parse import classify_token, parse_si

SUBCATEGORIES = {
    "R": ("Chip Resistor - Surface Mount",),
    "C": ("Multilayer Ceramic Capacitors MLCC - SMD/SMT",),
    "L": ("Inductors (SMD)", "Power Inductors", "Molding Power Inductors"),
}
DIODE_SUBCATEGORIES = (
    "Switching Diodes", "Diodes - General Purpose", "Schottky Diodes", "Zener Diodes",
    "Fast Recovery / High Efficiency Diodes", "Super Barrier Rectifiers (SBR)", "Avalanche Diodes",
    "Bridge Rectifiers", "ESD and Surge Protection (TVS/ESD)", "LED Indication - Discrete",
)
# Description token that carries the primary value, by unit suffix.
VALUE_UNIT = {"R": "Ω", "C": "F", "L": "H"}


@dataclass
class Part:
    lcsc: int
    mfr: str
    manufacturer: str
    package: str
    basic: bool
    stock: int
    price: float | None
    description: str
    value: float | None = None
    voltage: float | None = None
    power: float | None = None
    tolerance: float | None = None
    dielectric: str | None = None
    currents: list[float] = field(default_factory=list)
    shielded: bool | None = None

    @property
    def lcsc_str(self) -> str:
        return f"C{self.lcsc}"


def first_price(price: str) -> float | None:
    # "1-199:0.036,200-599:0.028,..."
    try:
        return float(price.split(",")[0].split(":")[1])
    except (IndexError, ValueError):
        return None


def parse_description(kind: str, desc: str, part: Part) -> None:
    unit = VALUE_UNIT[kind]
    if kind == "L":
        d = desc.lower()
        if "unshielded" in d:
            part.shielded = False
        elif "shielded" in d or "molded" in d:  # molded (metal composite) inductors are shielded by construction
            part.shielded = True
    for tok in desc.split():
        if "@" in tok or "Hz" in tok or "℃" in tok:
            continue
        if tok.endswith(unit):
            v = parse_si(tok, unit)
            # For inductors an Ω token is DCR, not the value; only the H token counts.
            if v is not None and part.value is None:
                part.value = v
            continue
        c = classify_token(tok)
        if c is None:
            continue
        key, v = c
        if key == "current":
            part.currents.append(v)
        elif getattr(part, key) is None:
            setattr(part, key, v)


# Most energy (L * I^2) an inductor can store per mm^2 of footprint. Genuine chip inductors reach ~10 uJ/mm^2;
# listings above 20 have the wrong package (a 4x4mm 'SKSHC0402' listed as 0402) or a garbled description
# ('3nH 450A'). Packages given as 'SMD,AxBmm' include tall parts (genuine up to ~50), so only absurd ones are cut.
MAX_UJ_PER_MM2 = {"chip": 20.0, "smd": 100.0}


def implausible_inductor(p: Part) -> bool:
    area = package_area(p.package)
    if not area or not p.value or not p.currents:
        return False
    density = p.value * min(p.currents) ** 2 * 1e6 / area
    return density > MAX_UJ_PER_MM2["chip" if p.package in CHIP else "smd"]


# Most energy (C * V^2) an MLCC can store per mm^2 of footprint, by dielectric. Genuine class-II parts reach
# ~2e4 uJ/mm^2 and C0G ~3e3 at any size; listings far above that have a garbled description ('51000uF C0G 0402').
MAX_CAP_UJ_PER_MM2 = {"C0G": 1e4, "other": 5e4}


def implausible_capacitor(p: Part) -> bool:
    area = package_area(p.package)
    if not area or not p.value or not p.voltage:
        return False
    density = p.value * p.voltage ** 2 * 1e6 / area
    return density > MAX_CAP_UJ_PER_MM2["C0G" if p.dielectric == "C0G" else "other"]


def open_db(path: Path) -> sqlite3.Connection:
    legacy = path.with_name("passives.sqlite3")
    if not path.exists() and path.name == "parts.sqlite3" and legacy.exists():
        sys.stderr.write(f"warning: using old passives-only DB {legacy}; "
                         f"run `autopartselector update` to look up other parts\n")
        path = legacy
    if not path.exists():
        raise SystemExit(f"parts DB not found at {path}\nrun: autopartselector update")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def find_mpn(conn: sqlite3.Connection, mpn: str, min_stock: int,
             subcategories: tuple[str, ...] | None = DIODE_SUBCATEGORIES) -> list[Part]:
    """In-stock parts whose MPN is `mpn`, or `mpn` plus a ' '/'-' suffix (e.g. 'B5819W SL').

    Limited to `subcategories` (default: diodes/LEDs); None searches every part.
    """
    esc = mpn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    sub_sql = f"subcategory IN ({','.join('?' * len(subcategories))}) AND " if subcategories else ""
    rows = conn.execute(
        f"SELECT lcsc, mfr, manufacturer, package, library_type, stock, price, description FROM parts "
        f"WHERE {sub_sql}stock >= ? "
        f"AND (mfr = ? COLLATE NOCASE OR mfr LIKE ? ESCAPE '\\' OR mfr LIKE ? ESCAPE '\\')",
        (*(subcategories or ()), min_stock, mpn, esc + " %", esc + "-%"),
    )
    return [
        Part(r["lcsc"], r["mfr"], r["manufacturer"], r["package"], r["library_type"] == "Basic",
             r["stock"], first_price(r["price"] or ""), r["description"] or "")
        for r in rows
    ]


def find_mpn_prefix(conn: sqlite3.Connection, mpn: str, min_stock: int,
                    subcategories: tuple[str, ...] | None = DIODE_SUBCATEGORIES, limit: int = 500) -> list[Part]:
    """In-stock parts whose MPN starts with `mpn` ('TLV62569DDC' -> 'TLV62569DDCR'), highest stock first.

    A lowercase 'x' in an otherwise upper-case MPN is a KiCad wildcard ('STM32F072CBTx') and matches any one character.
    """
    esc = mpn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if any(c.isupper() for c in mpn):
        esc = esc.replace("x", "_")
    sub_sql = f"subcategory IN ({','.join('?' * len(subcategories))}) AND " if subcategories else ""
    rows = conn.execute(
        f"SELECT lcsc, mfr, manufacturer, package, library_type, stock, price, description FROM parts "
        f"WHERE {sub_sql}stock >= ? AND mfr LIKE ? ESCAPE '\\' ORDER BY stock DESC LIMIT ?",
        (*(subcategories or ()), min_stock, esc + "%", limit),
    )
    return [
        Part(r["lcsc"], r["mfr"], r["manufacturer"], r["package"], r["library_type"] == "Basic",
             r["stock"], first_price(r["price"] or ""), r["description"] or "")
        for r in rows
    ]


def load_parts(conn: sqlite3.Connection, kind: str, min_stock: int) -> list[Part]:
    subs = SUBCATEGORIES[kind]
    rows = conn.execute(
        f"SELECT lcsc, mfr, manufacturer, package, library_type, stock, price, description FROM parts "
        f"WHERE subcategory IN ({','.join('?' * len(subs))}) AND stock >= ?",
        (*subs, min_stock),
    )
    out = []
    for r in rows:
        p = Part(r["lcsc"], r["mfr"], r["manufacturer"], r["package"], r["library_type"] == "Basic",
                 r["stock"], first_price(r["price"] or ""), r["description"] or "")
        parse_description(kind, p.description, p)
        if p.value is None or (kind == "L" and implausible_inductor(p)) or (kind == "C" and implausible_capacitor(p)):
            continue
        out.append(p)
    return out
