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


# IC/transistor packages, as "<family>-<pins>" with an optional EP suffix ("SOIC-8-1EP", "ESOP-8", "QFN-32-EP").
_IC_PKG = re.compile(
    r"^(E|H)?(SOIC|SOP|SO|SSOP|TSSOP|MSOP|VSSOP|LQFP|TQFP|T?SOT-23|[VWUTX]?QFN|[VWUXP]?DFN|[VWUX]?SON)-(\d+)(W)?(-\d*EP)?$")
_IC_FAMILY = {"SOP": "SOIC", "SO": "SOIC", "TSOT-23": "SOT-23"}
_IC_ALIASES = {
    "SOT-223-3": "SOT-223", "SOT-223-4": "SOT-223", "SOT-89-3": "SOT-89",
    "SOT-25": "SOT-23-5", "SOT-753": "SOT-23-5", "SOT-26": "SOT-23-6", "SOT-23-6L": "SOT-23-6",
    "SC-70-5": "SOT-353", "SOT-666-6": "SOT-666", "SC-88A": "SOT-353", "SOT-353-5": "SOT-353", "SC-88": "SOT-363",
    "TO-252-2": "TO-252", "TO-252-3": "TO-252", "DPAK": "TO-252",
    "TO-263-2": "TO-263", "TO-263-3": "TO-263", "D2PAK": "TO-263",
}
_IC_KEYS = {"SOT-223", "SOT-89", "SOT-353", "SOT-563", "SOT-723", "SOT-143", "SOT-666", "TO-252", "TO-263"}


def _normalise(t: str) -> str:
    """Spelling fixes before alias lookup: 'SOT223' -> 'SOT-223', 'SOT-23-5L' -> 'SOT-23-5',
    'SOIC-16-300mil' -> 'SOIC-16W' (wide body, as KiCad names it), 'SSOP-20-208mil' -> 'SSOP-20'."""
    t = re.sub(r"^SOT(?=\d)", "SOT-", t)
    m = re.match(r"^(.*-\d+)-[\d.]+(MIL|MM)$", t)
    if m:
        t = m.group(1) + ("W" if t.endswith("-300MIL") and t.startswith("SO") and not t.startswith("SOT") else "")
    return re.sub(r"^(.*-\d+)L$", r"\1", t)


def _canon(tok: str) -> str | None:
    t = _normalise(tok.strip().upper())
    t = _DIODE_ALIASES.get(t, t)
    t = _IC_ALIASES.get(t, t)
    if t in _KNOWN_DIODE_KEYS or t in _IC_KEYS:
        return t
    m = _IC_PKG.match(t)
    if not m:
        return None
    lead, family, pins, wide, ep = m.groups()
    family = _IC_FAMILY.get(family, family)
    if family.endswith("SON"):
        family = "DFN"
    if family.endswith("QFN") or family.endswith("DFN"):
        return f"{family[-3:]}-{pins}"  # these nearly always have a pad; match on pin count only
    if family == "SOT-23" and pins == "3":
        return "SOT-23"
    return f"{family}-{pins}" + (wide or "") + ("-EP" if lead or ep else "")


def package_key(package: str) -> str | None:
    """'SMA(DO-214AC)' -> 'SMA', 'SOP-8' -> 'SOIC-8', 'QFN-32-EP(5x5)' -> 'QFN-32'; None if unknown."""
    for tok in re.split(r"[()\s,_]+", package):
        k = _canon(tok)
        if k:
            return k
    return None


def footprint_package_key(footprint: str) -> str | None:
    """'Diode_SMD:D_SOD-123F' -> 'SOD-123F', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm' -> 'SOIC-8'."""
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
