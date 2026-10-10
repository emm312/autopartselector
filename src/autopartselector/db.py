"""Load and parse candidate parts from the passives DB built by `update`."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
        if p.value is not None:
            out.append(p)
    return out
