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


# --- diodes / LEDs -------------------------------------------------------------
# JLC writes the same package many ways ("SMA(DO-214AC)", "DO-214AC(SMA)", "SMA"); KiCad footprint names
# use yet another spelling. Both are reduced to one key so they can be compared.
_DIODE_ALIASES = {
    "DO-214AC": "SMA", "DO-214AA": "SMB", "DO-214AB": "SMC",
    "SOD-123FL": "SOD-123F",
    "LL-34": "MINIMELF", "SOD-80": "MINIMELF", "MINIMELF": "MINIMELF", "LL-41": "MELF", "MELF": "MELF",
    "DFN1006-2": "SOD-882", "DFN1006-2L": "SOD-882", "SOD-882": "SOD-882",
    "SC-70": "SOT-323", "SC-70-6": "SOT-363", "SOT-23-3": "SOT-23", "SOT-23-3L": "SOT-23", "TO-236": "SOT-23",
    "SOT-23-6L": "SOT-23-6", "SOT-363-6L": "SOT-363",
}
# Packages we can recognise (to match against an existing footprint) but don't pick a footprint for.
_DIODE_NO_FOOTPRINT = {"SMAF", "SMBF", "SOD-123W", "DO-41", "DO-35", "DO-15", "DO-201AD", "DO-27"}
_DIODE_FOOTPRINTS = {
    **{k: f"Diode_SMD:D_{k}" for k in (
        "SOD-123", "SOD-123F", "SOD-323", "SOD-323F", "SOD-523", "SOD-923", "SOD-882", "SOD-128",
        "SMA", "SMB", "SMC",
    )},
    "MINIMELF": "Diode_SMD:D_MiniMELF",
    "MELF": "Diode_SMD:D_MELF",
    "SOT-23": "Package_TO_SOT_SMD:SOT-23",
    "SOT-23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "SOT-323": "Package_TO_SOT_SMD:SOT-323_SC-70",
    "SOT-363": "Package_TO_SOT_SMD:SOT-363_SC-70-6",
    "SOT-523": "Package_TO_SOT_SMD:SOT-523",
}
_KNOWN_DIODE_KEYS = set(_DIODE_FOOTPRINTS) | set(CHIP) | _DIODE_NO_FOOTPRINT


def _canon(tok: str) -> str | None:
    t = tok.strip().upper()
    t = _DIODE_ALIASES.get(t, t)
    return t if t in _KNOWN_DIODE_KEYS else None


def diode_package_key(package: str) -> str | None:
    """'SMA(DO-214AC)' -> 'SMA', 'DFN1006-2L' -> 'SOD-882', '0603' -> '0603'; None if unknown."""
    for tok in re.split(r"[()\s,]+", package):
        k = _canon(tok)
        if k:
            return k
    return None


def footprint_package_key(footprint: str) -> str | None:
    """'Diode_SMD:D_SOD-123F' -> 'SOD-123F', 'LED_SMD:LED_0603_1608Metric' -> '0603'."""
    name = footprint.split(":", 1)[-1]
    name = re.sub(r"^(D|LED)_", "", name)
    for tok in (name.split("_")[0], name):
        k = _canon(tok)
        if k:
            return k
    return None


def diode_footprint(key: str, led: bool) -> str | None:
    if key in CHIP:
        if key not in ("0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512"):
            return None
        return f"{'LED_SMD:LED' if led else 'Diode_SMD:D'}_{key}_{CHIP[key][2]}Metric"
    return _DIODE_FOOTPRINTS.get(key)
