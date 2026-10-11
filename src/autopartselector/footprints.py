"""Package size ladder and KiCad footprint names (from KiCad 10 stock libraries)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

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
    r"^(E|H)?(SOIC|SOP|SO|SSOP|TSSOP|MSOP|VSSOP|LQFP|TQFP|T?SOT-23|P?DIP|[A-Z]*QF?P?N|[A-Z]*DF?P?N|[A-Z]*SON"
    r"|[A-Z]*BGA|[A-Z]?LGA)-(\d+)(W)?(-\d*EP)?$")
_IC_FAMILY = {"SOP": "SOIC", "SO": "SOIC", "TSOT-23": "SOT-23", "PDIP": "DIP"}
_IC_ALIASES = {
    "SOT-223-3": "SOT-223", "SOT-223-4": "SOT-223", "SOT-89-3": "SOT-89",
    "SOT-25": "SOT-23-5", "SOT-753": "SOT-23-5", "SOT-26": "SOT-23-6", "SOT-23-6L": "SOT-23-6",
    "SC-70-5": "SOT-353", "SOT-666-6": "SOT-666", "SC-88A": "SOT-353", "SOT-353-5": "SOT-353", "SC-88": "SOT-363",
    "TO-252-2": "TO-252", "TO-252-3": "TO-252", "DPAK": "TO-252",
    "TO-263-2": "TO-263", "TO-263-3": "TO-263", "D2PAK": "TO-263",
    "TO-220": "TO-220-3", "TO-220AB": "TO-220-3", "TO-220AB-3": "TO-220-3",
    "TO-220AC": "TO-220-2", "TO-220F": "TO-220F-3",
    "TO-92-3": "TO-92", "TO-247": "TO-247-3", "TSOP-6": "SOT-23-6",
    "SOT-25-5": "SOT-23-5", "TSOT-25": "SOT-23-5", "TSOT-25-5": "SOT-23-5",
}
_IC_KEYS = {
    "SOT-223", "SOT-89", "SOT-353", "SOT-563", "SOT-723", "SOT-143", "SOT-666", "TO-252", "TO-263", "TO-263-5",
    "TO-263-7", "TO-220-2", "TO-220-3", "TO-220-5", "TO-220F-3", "TO-92", "TO-247-3",
}

# Body width classes (mm) for small-outline packages, and the mil names JLC uses for them.
_SO_FAMILIES = {"SOIC", "SSOP", "TSSOP"}
_SO_WIDTHS = (3.9, 4.4, 5.3, 6.1, 7.5)
_MIL_WIDTH = {150: 3.9, 154: 3.9, 173: 4.4, 175: 4.4, 200: 5.3, 208: 5.3, 209: 5.3, 240: 6.1, 300: 7.5}
# What JLC means when it gives no width.
_DEFAULT_WIDTH = {"SOIC": 3.9, "TSSOP": 4.4}
# Families compared on body size (when both sides give one).
_BODY_FAMILIES = ("QFN-", "DFN-", "LGA-", "BGA-", "XTAL-")
# Crystals/oscillators: JLC 'SMD3225-4P' (3.2x2.5mm, 4 pads); KiCad 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm'.
_JLC_XTAL = re.compile(r"^SMD(\d)(\d)(\d)(\d)-(\d+)P$")
_KICAD_XTAL = re.compile(r"-(\d+)PIN$")


@dataclass(frozen=True)
class Package:
    """A package reduced to something comparable across JLC listings and KiCad footprint names."""

    key: str  # 'SOIC-8', 'QFN-32', 'SOT-23-5', '0603', 'SMA', ...
    width: float | None = None  # SOIC/SSOP/TSSOP body width class, mm
    body: tuple[float, float] | None = None  # QFN/DFN/LGA/BGA body (short, long), mm

    def matches(self, other: "Package") -> bool:
        if self.key != other.key:
            return False
        if self.width is not None and other.width is not None and self.width != other.width:
            return False
        if self.body is not None and other.body is not None:
            return all(abs(a - b) <= 0.15 for a, b in zip(self.body, other.body))
        return True

    def __str__(self) -> str:
        if self.width is not None:
            return f"{self.key} ({self.width:g}mm)"
        if self.body is not None:
            return f"{self.key} ({self.body[0]:g}x{self.body[1]:g}mm)"
        return self.key


def _snap_width(mm: float) -> float | None:
    best = min(_SO_WIDTHS, key=lambda w: abs(w - mm))
    return best if abs(best - mm) <= 0.25 else None


def _normalise(t: str) -> tuple[str, float | None, bool]:
    """Spelling fixes before alias lookup, and any width suffix: 'SOT223' -> 'SOT-223', 'SOT-23-5L' -> 'SOT-23-5',
    'SOIC-16-300mil' -> ('SOIC-16', 7.5). Returns (token, width, whether a width suffix was given)."""
    t = re.sub(r"^(T?)SOT(?=\d)", r"\1SOT-", t)  # 'SOT23-5', 'TSOT23-5'
    t = re.sub(r"^SOT-23-(?:THIN-(\d+)|(\d+)-THIN)$", lambda m: f"TSOT-23-{m.group(1) or m.group(2)}", t)
    width, given = None, False
    m = re.match(r"^(.*-\d+)-([\d.]+)(MIL|MM)$", t)
    if m:
        t, given = m.group(1), True
        v = float(m.group(2))
        width = _MIL_WIDTH.get(int(v)) if m.group(3) == "MIL" else _snap_width(v)
    m = re.match(r"^(.*-\d+)-(NB|WB)$", t)
    if m:
        t, given, width = m.group(1), True, 3.9 if m.group(2) == "NB" else 7.5
    return re.sub(r"^(.*-\d+)L$", r"\1", t), width, given


def _canon(tok: str) -> Package | None:
    t, width, given = _normalise(tok.strip().upper())
    t = _DIODE_ALIASES.get(t, t)
    t = _IC_ALIASES.get(t, t)
    if t in _KNOWN_DIODE_KEYS or t in _IC_KEYS:
        return Package(t)
    m = _IC_PKG.match(t)
    if not m:
        return None
    lead, family, pins, wide, ep = m.groups()
    family = _IC_FAMILY.get(family, family)
    if family.endswith("SON"):
        family = "DFN"
    family = re.sub(r"([QD])FPN$", r"\1FN", family)  # ST's UFQFPN / UFDFPN
    for f in ("QFN", "DFN", "BGA", "LGA"):
        if family.endswith(f):
            return Package(f"{f}-{pins}")  # QFN/DFN nearly always have a pad; match on pin count (and body) only
    if family == "SOT-23" and pins == "3":
        return Package("SOT-23")
    key = f"{family}-{pins}" + ("-EP" if lead or ep else "")
    if family in _SO_FAMILIES:
        if wide:
            width, given = 7.5, True
        return Package(key, width if given else None)
    return Package(key)


_JLC_BODY = re.compile(r"\((\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)\)")


def _with_size(pkg: Package, width: float | None, body: tuple[float, float] | None) -> Package:
    if pkg.key.split("-")[0] in _SO_FAMILIES:
        return Package(pkg.key, pkg.width if pkg.width is not None else width)
    if pkg.key.startswith(_BODY_FAMILIES) and body:
        return Package(pkg.key, body=tuple(sorted(body)))
    return pkg


@lru_cache(maxsize=None)
def parse_package(package: str) -> Package | None:
    """A JLC package string: 'SOP-8' -> SOIC-8 (3.9mm), 'SOIC-8-208mil' -> SOIC-8 (5.3mm),
    'QFN-32-EP(5x5)' -> QFN-32 (5x5mm), 'SMA(DO-214AC)' -> SMA; None if unknown."""
    for tok in re.split(r"[()\s,_]+", package):
        if m := _JLC_XTAL.match(tok.upper()):
            a, b, c, d, pads = m.groups()
            return Package(f"XTAL-{pads}", body=tuple(sorted((float(f"{a}.{b}"), float(f"{c}.{d}")))))
        pkg = _canon(tok)
        if pkg:
            m = _JLC_BODY.search(package.upper())
            body = (float(m.group(1)), float(m.group(2))) if m else None
            family = pkg.key.split("-")[0]
            if pkg.width is None and family in _DEFAULT_WIDTH and not re.search(r"-\d+(?:\.\d+)?MM\b", package.upper()):
                pkg = Package(pkg.key, _DEFAULT_WIDTH[family])
            return _with_size(pkg, None, body)
    return None


def package_key(package: str) -> str | None:
    """'SMA(DO-214AC)' -> 'SMA', 'SOP-8' -> 'SOIC-8', 'QFN-32-EP(5x5)' -> 'QFN-32'; None if unknown."""
    pkg = parse_package(package)
    return pkg.key if pkg else None


_KICAD_CHIP = re.compile(r"(?:^|_)(\d{4,5})_(\d{4,5})Metric")
_KICAD_BODY = re.compile(r"_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm")
_PLIB_BODY = re.compile(r"_L(\d+(?:\.\d+)?)-W(\d+(?:\.\d+)?)")  # EasyEDA/JLC library names


@lru_cache(maxsize=None)
def parse_footprint(footprint: str) -> Package | None:
    """A KiCad footprint name: 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm' -> SOIC-8 (5.3mm),
    'Capacitor_SMD:C_0805_2012Metric' -> 0805, 'plib:VQFN-48_L7.0-W7.0-P0.50-BL-EP4.1' -> QFN-48 (7x7mm)."""
    lib, _, name = footprint.rpartition(":")
    if lib.startswith(("Crystal", "Oscillator")):
        for tok in name.split("_"):
            if m := _KICAD_XTAL.search(tok.upper()):
                body = _KICAD_BODY.search(name)
                return Package(f"XTAL-{m.group(1)}", body=tuple(sorted(
                    (float(body.group(1)), float(body.group(2))))) if body else None)
    m = _KICAD_CHIP.search(name)
    if m and m.group(1) in CHIP and CHIP[m.group(1)][2] == m.group(2):
        return Package(m.group(1))
    name = re.sub(r"^(D|LED)_", "", name)
    for tok in name.split("_"):
        pkg = _canon(tok)
        if pkg:
            width, body = None, None
            if m := _PLIB_BODY.search(name):
                length, width = float(m.group(1)), float(m.group(2))
                body = (width, length)
            elif m := _KICAD_BODY.search(name):
                width, length = float(m.group(1)), float(m.group(2))
                body = (width, length)
            return _with_size(pkg, _snap_width(width) if width is not None else None, body)
    return None


def footprint_package_key(footprint: str) -> str | None:
    """'Diode_SMD:D_SOD-123F' -> 'SOD-123F', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm' -> 'SOIC-8'."""
    pkg = parse_footprint(footprint)
    return pkg.key if pkg else None


def diode_footprint(key: str, led: bool) -> str | None:
    if key in CHIP:
        if key not in ("0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512"):
            return None
        return f"{'LED_SMD:LED' if led else 'Diode_SMD:D'}_{key}_{CHIP[key][2]}Metric"
    return _DIODE_FOOTPRINTS.get(key)
