"""Pick the smallest package (>= preferred size) whose parts meet the requirement."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from .db import Part
from .footprints import CHIP, package_area
from .parse import Requirement

DEFAULT_DIELECTRICS = {"C0G", "X5R", "X6S", "X6T", "X7R", "X7S", "X7T", "X8R", "X8L"}


@dataclass
class Options:
    size: str = "0603"
    max_size: str | None = None
    cap_derate: float = 1.0
    min_voltage: float | None = None
    default_res_tolerance: float = 0.01
    basic_bump: int = 0  # extra size steps allowed to land on a Basic part
    allow_power_inductors: bool = False


@dataclass
class Choice:
    part: Part
    bumped_from: str | None  # preferred size if we had to go bigger
    reason: str


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-4)


def required_power(req: Requirement) -> float | None:
    cands = []
    if req.power is not None:
        cands.append(req.power)
    if req.value:
        if req.current is not None:
            cands.append(req.current ** 2 * req.value)
        if req.voltage is not None:
            cands.append(req.voltage ** 2 / req.value)
    return max(cands) if cands else None


def meets(req: Requirement, p: Part, opts: Options) -> bool:
    if req.value is None or p.value is None or not _same(req.value, p.value):
        return False
    if req.kind == "R":
        need = required_power(req)
        if need is not None and (p.power is None or p.power < need):
            return False
        if req.voltage is not None and p.voltage is not None and p.voltage < req.voltage:
            return False
        tol = req.tolerance if req.tolerance is not None else opts.default_res_tolerance
        if p.tolerance is None or p.tolerance > tol + 1e-9:
            return False
    elif req.kind == "C":
        v = req.voltage * opts.cap_derate if req.voltage is not None else None
        if opts.min_voltage is not None:
            v = max(v or 0.0, opts.min_voltage)
        if v is not None and (p.voltage is None or p.voltage < v):
            return False
        if req.dielectric:
            if p.dielectric != req.dielectric:
                return False
        elif p.dielectric not in DEFAULT_DIELECTRICS:
            return False
        if req.tolerance is not None and (p.tolerance is None or p.tolerance > req.tolerance + 1e-9):
            return False
    elif req.kind == "L":
        if req.current is not None and (not p.currents or min(p.currents) < req.current):
            return False
        if req.tolerance is not None and (p.tolerance is None or p.tolerance > req.tolerance + 1e-9):
            return False
    return True


def _rank_key(p: Part):
    return (not p.basic, -p.stock, p.price if p.price is not None else math.inf)


def size_ladder(parts: list[Part], opts: Options) -> list[tuple[float, list[str]]]:
    """Groups of packages, smallest first, starting at the preferred size."""
    start = package_area(opts.size)
    if start is None:
        raise SystemExit(f"unknown size {opts.size!r}; pick one of {', '.join(CHIP)}")
    stop = package_area(opts.max_size) if opts.max_size else math.inf
    by_area: dict[float, set[str]] = defaultdict(set)
    for p in parts:
        if p.package not in CHIP and not opts.allow_power_inductors:
            continue
        a = package_area(p.package)
        if a is not None and start - 1e-9 <= a <= stop + 1e-9:
            by_area[round(a, 3)].add(p.package)
    return [(a, sorted(by_area[a])) for a in sorted(by_area)]


def choose(req: Requirement, parts_by_pkg: dict[str, list[Part]], ladder, opts: Options) -> Choice | None:
    steps: list[list[Part]] = []  # matches per ladder step, from the first step that has any
    for _area, pkgs in ladder:
        ok = [p for pkg in pkgs for p in parts_by_pkg.get(pkg, ()) if meets(req, p, opts)]
        if ok or steps:
            steps.append(ok)
        if len(steps) > opts.basic_bump:
            break
    if not steps:
        return None
    pick_from = steps[0]
    if not any(p.basic for p in pick_from):
        for ok in steps[1:]:
            if any(p.basic for p in ok):
                pick_from = ok
                break
    best = min(pick_from, key=_rank_key)
    bumped = opts.size if best.package != opts.size else None
    reason = "basic" if best.basic else "extended"
    return Choice(best, bumped, reason)


def index_by_package(parts: list[Part]) -> dict[str, list[Part]]:
    out: dict[str, list[Part]] = defaultdict(list)
    for p in parts:
        out[p.package].append(p)
    return out
