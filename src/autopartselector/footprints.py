"""Package size ladder and KiCad footprint names (from KiCad 10 stock libraries)."""

from __future__ import annotations

import re

# imperial code -> (length mm, width mm, metric code)
CHIP = {
    "01005": (0.4, 0.2, "0402"),
    "0201": (0.6, 0.3, "0603"),
    "0402": (1.0, 0.5, "1005"),
    "0603": (1.6, 0.8, "1608"),
    "0805": (2.0, 1.25, "2012"),
    "0806": (2.0, 1.6, "2016"),
    "1008": (2.5, 2.0, "2520"),
    "1206": (3.2, 1.6, "3216"),
    "1210": (3.2, 2.5, "3225"),
    "1806": (4.5, 1.6, "4516"),
    "1808": (4.5, 2.0, "4520"),
    "1812": (4.5, 3.2, "4532"),
    "2010": (5.0, 2.5, "5025"),
    "2220": (5.7, 5.0, "5750"),
    "2512": (6.4, 3.2, "6332"),
}

# Chip codes that have a stock footprint, per symbol kind.
_STOCK = {
    "R": ("Resistor_SMD", "R", {"01005", "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512"}),
    "C": ("Capacitor_SMD", "C", {"01005", "0201", "0402", "0603", "0805", "1206", "1210", "1808", "1812", "2220"}),
    "L": ("Inductor_SMD", "L", {"01005", "0201", "0402", "0603", "0805", "1008", "1206", "1210", "1806", "1812", "2010", "2512"}),
}

_SMD_DIMS = re.compile(r"^SMD,\s*(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm$")


def package_area(package: str) -> float | None:
    """Body footprint area in mm² for a chip code or an 'SMD,AxBmm' package; None if unknown."""
    if package in CHIP:
        l, w, _ = CHIP[package]
        return l * w
    m = _SMD_DIMS.match(package.strip())
    if m:
        return float(m.group(1)) * float(m.group(2))
    return None


def footprint_for(kind: str, package: str) -> str | None:
    lib, prefix, codes = _STOCK[kind]
    if package not in codes:
        return None
    return f"{lib}:{prefix}_{package}_{CHIP[package][2]}Metric"
