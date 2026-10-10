"""Parse engineering values ("4k7", "100n", "0.1uF", "1/4W", "500mA") and requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}
# Unit suffixes we strip before reading the number (longest first).
UNITS = ("ohms", "ohm", "Ω", "F", "H", "V", "A", "W", "R")

DIELECTRICS = {"C0G", "NP0", "X5R", "X6S", "X6T", "X7R", "X7S", "X7T", "X8R", "X8L", "Y5V", "Z5U"}
_DIELECTRIC_ALIASES = {"COG": "C0G", "NPO": "C0G", "NP0": "C0G"}

_RKM = re.compile(r"^(\d+)([pnumkKMGR])(\d+)$")
_PLAIN = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)([pnumkKMG]?)$")
_FRACTION = re.compile(r"^(\d+)/(\d+)$")


def _normalise(tok: str) -> str:
    return tok.strip().replace("µ", "u").replace("μ", "u").replace("±", "")


def parse_si(tok: str, unit: str | None = None) -> float | None:
    """Parse a value with optional SI prefix / RKM notation / unit suffix.

    `unit` (e.g. "V") requires that unit, if present, to match; when None any of UNITS is stripped.
    Case matters: m = milli, M = mega.
    """
    s = _normalise(tok)
    if not s:
        return None
    if not _RKM.match(s):
        units = (unit,) if unit else UNITS
        for u in units:
            if s.endswith(u) and len(s) > len(u):
                s = s[: -len(u)]
                break
            if s.lower().endswith(u.lower()) and u.lower() in ("ohm", "ohms"):
                s = s[: -len(u)]
                break
        s = s.strip()
    rkm = _RKM.match(s)
    if rkm:
        a, p, b = rkm.groups()
        return float(f"{a}.{b}") * (1.0 if p == "R" else PREFIX[p])
    frac = _FRACTION.match(s)
    if frac:
        return int(frac.group(1)) / int(frac.group(2))
    m = _PLAIN.match(s)
    if not m:
        # "10k" style with a unit we didn't expect, or junk
        return None
    num, p = m.groups()
    return float(num) * (PREFIX[p] if p else 1.0)


def parse_tolerance(tok: str) -> float | None:
    s = _normalise(tok)
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100
        except ValueError:
            return None
    return None


def parse_dielectric(tok: str) -> str | None:
    s = tok.strip().upper()
    s = _DIELECTRIC_ALIASES.get(s, s)
    return s if s in DIELECTRICS else None


@dataclass
class Requirement:
    kind: str  # "R", "C", "L"
    value: float | None = None
    voltage: float | None = None
    current: float | None = None
    power: float | None = None
    tolerance: float | None = None
    dielectric: str | None = None
    net_voltage: float | None = None  # estimated from net names; used only when `voltage` is unset
    shielded: bool | None = None  # inductors: True/False if the symbol asks for (un)shielded
    problems: list[str] = field(default_factory=list)

    @property
    def working_voltage(self) -> float | None:
        return self.voltage if self.voltage is not None else self.net_voltage

    def describe(self) -> str:
        bits = []
        if self.voltage is not None:
            bits.append(f"{fmt_si(self.voltage)}V")
        elif self.net_voltage is not None:
            bits.append(f"{fmt_si(self.net_voltage)}V(net)")
        if self.current is not None:
            bits.append(f"{fmt_si(self.current)}A")
        if self.power is not None:
            bits.append(f"{fmt_si(self.power)}W")
        if self.tolerance is not None:
            bits.append(f"{self.tolerance * 100:g}%")
        if self.dielectric:
            bits.append(self.dielectric)
        if self.shielded is not None:
            bits.append("shielded" if self.shielded else "unshielded")
        return " ".join(bits) or "-"


def fmt_si(v: float) -> str:
    for p, mult in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1.0), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(v) >= mult * 0.9999:
            return f"{v / mult:g}{p}"
    return f"{v:g}"


def classify_token(tok: str) -> tuple[str, object] | None:
    """Classify a rating token from a Value field or a description: ("voltage", 25.0) etc."""
    s = _normalise(tok)
    if not s or "@" in s or "Hz" in s or "℃" in s or "ppm" in s:
        return None
    d = parse_dielectric(s)
    if d:
        return "dielectric", d
    if s.endswith("%"):
        t = parse_tolerance(s)
        return ("tolerance", t) if t is not None else None
    for key, unit in (("voltage", "V"), ("current", "A"), ("power", "W")):
        if s.endswith(unit):
            v = parse_si(s, unit)
            if v is not None:
                return key, v
    return None


FIELD_ALIASES = {
    "voltage": "voltage", "v": "voltage", "vmax": "voltage", "rated voltage": "voltage",
    "current": "current", "i": "current", "imax": "current", "rated current": "current",
    "power": "power", "p": "power", "pmax": "power",
    "tolerance": "tolerance", "tol": "tolerance",
    "dielectric": "dielectric", "tempco": "dielectric",
}
_FIELD_UNITS = {"voltage": "V", "current": "A", "power": "W"}


def shield_request(text: str) -> bool | None:
    """'shielded' -> True, 'unshielded' / 'non-shielded' -> False, else None."""
    t = text.lower()
    if re.search(r"\b(un|non-?)shielded\b", t):
        return False
    if re.search(r"\bshielded\b", t):
        return True
    return None


def parse_requirement(kind: str, value_field: str, fields: dict[str, str]) -> Requirement:
    """Merge Value-field tokens and explicit symbol fields (fields win)."""
    req = Requirement(kind)
    if kind == "L":
        for text in (fields.get("Description", ""), value_field):
            s = shield_request(text)
            if s is not None:
                req.shielded = s
        value_field = re.sub(r"\b(?:un|non-?)?shielded\b", "", value_field, flags=re.I)
    toks = value_field.split()
    if toks:
        req.value = parse_si(toks[0])
        if req.value is None:
            req.problems.append(f"can't parse value {toks[0]!r}")
        for t in toks[1:]:
            c = classify_token(t)
            if c is None:
                req.problems.append(f"ignored value token {t!r}")
            else:
                setattr(req, c[0], c[1])
    else:
        req.problems.append("empty value")

    for name, raw in fields.items():
        key = FIELD_ALIASES.get(name.strip().lower())
        if not key or not raw.strip():
            continue
        if key == "tolerance":
            v = parse_tolerance(raw) if raw.strip().endswith("%") else None
        elif key == "dielectric":
            v = parse_dielectric(raw)
        else:
            v = parse_si(raw, _FIELD_UNITS[key])
            if v is None:
                v = parse_si(raw)
        if v is None:
            req.problems.append(f"can't parse field {name}={raw!r}")
        else:
            setattr(req, key, v)
    return req
