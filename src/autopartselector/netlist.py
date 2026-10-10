"""Estimate the voltage across a part from the names of the nets on its pins.

Connectivity comes from `kicad-cli sch export netlist`, so labels, power symbols and hierarchy are
resolved by KiCad. Net names are then read as rails: "+3V3" -> 3.3, "+5V HDMI" -> 5, "GND" -> 0.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .kicad_sch import parse

# A word that is a voltage: 3V3, +1V0, 5V, -12V, 3.3V, +2.5V
_VOLT_WORD = re.compile(r"^([+-]?)(\d+)(?:V(\d+)|(?:\.(\d+))?V)$", re.I)
_GROUND = re.compile(r"^(?:[ADPSC]?GND[A-Z0-9]*|GND_\w+|VSS[A-Z]*|0V|EARTH|CHASSIS)$", re.I)
# Words that make a voltage-looking name a signal rather than a rail: "3V3_PG", "5V_EN", "12V_SENSE"
_SIGNAL_WORDS = {"PG", "PGOOD", "POK", "EN", "ENABLE", "FB", "SENSE", "SNS", "MON", "ADC", "DET", "OK", "FAULT"}
DEFAULT_NETS = {"VBUS": 5.0, "VUSB": 5.0}


def short_name(net: str) -> str:
    """'/Power/+3V3' -> '+3V3' (local labels carry the sheet path)."""
    return net.rsplit("/", 1)[-1]  # KiCad escapes "/" inside names as {slash}


def net_voltage(net: str, overrides: dict[str, float] | None = None) -> float | None:
    name = short_name(net)
    for table in (overrides or {}, DEFAULT_NETS):
        for k, v in table.items():
            if k.lower() in (name.lower(), net.lower()):
                return v
    if name.startswith(("Net-(", "unconnected-(")):
        return None
    if _GROUND.match(name):
        return 0.0
    words = [w for w in re.split(r"[\s_]+", name) if w]
    if any(w.upper() in _SIGNAL_WORDS for w in words):
        return None
    for w in words:
        m = _VOLT_WORD.match(w)
        if m:
            sign, whole, rkm, frac = m.groups()
            v = float(f"{whole}.{rkm or frac or 0}")
            return -v if sign == "-" else v
        if w.lstrip("+").upper() in DEFAULT_NETS:
            return DEFAULT_NETS[w.lstrip("+").upper()]
    return None


def across(nets: list[str], overrides: dict[str, float] | None = None) -> float | None:
    """Voltage across a two-terminal part: the difference if every pin's net is known, otherwise the
    known rail's magnitude (a pull-up's signal side is assumed to sit between that rail and ground).
    Ground plus an unknown net (a pull-down, a filter cap) says nothing, so that's None."""
    vs = [net_voltage(n, overrides) for n in nets]
    known = [v for v in vs if v is not None]
    if not known:
        return None
    if len(known) == len(vs):
        return max(known) - min(known)
    v = max(abs(v) for v in known)
    return v or None


def export_nets(root_sch: Path) -> dict[str, list[str]]:
    """ref -> net names on its pins, from KiCad's netlist. Raises RuntimeError if kicad-cli fails."""
    kicad_cli = shutil.which("kicad-cli")
    if not kicad_cli:
        raise RuntimeError("kicad-cli not found on PATH")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "n.net"
        r = subprocess.run(
            [kicad_cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(root_sch)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"kicad-cli netlist export failed: {(r.stderr or r.stdout).strip()}")
        root = parse(out.read_text(encoding="utf-8"))
    by_ref: dict[str, list[str]] = {}
    nets = root.child("nets")
    for net in nets.children("net") if nets is not None else ():
        name = net.child("name").atom(1).text
        for node in net.children("node"):
            by_ref.setdefault(node.child("ref").atom(1).text, []).append(name)
    return by_ref
