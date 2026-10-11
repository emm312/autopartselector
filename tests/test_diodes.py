import sqlite3
from types import SimpleNamespace

import pytest

from autopartselector import db
from autopartselector.cli import _diode_mpn
from autopartselector.db import Part
from autopartselector.footprints import Package, diode_footprint, package_key, footprint_package_key
from autopartselector.kicad_sch import Symbol, diode_kind
from autopartselector.select import choose_mpn


@pytest.mark.parametrize("pkg,key", [
    ("SMA(DO-214AC)", "SMA"), ("DO-214AC(SMA)", "SMA"), ("SMB", "SMB"), ("SOD-123FL", "SOD-123F"),
    ("LL-34", "MINIMELF"), ("DFN1006-2L", "SOD-882"), ("SOT-23-6L", "SOT-23-6"), ("0603", "0603"),
    ("SMAF", "SMAF"), ("TO-220F", "TO-220F-3"),
])
def test_package_key(pkg, key):
    assert package_key(pkg) == key


@pytest.mark.parametrize("fp,key", [
    ("Diode_SMD:D_SOD-123", "SOD-123"), ("Diode_SMD:D_SMB_Modified", "SMB"),
    ("LED_SMD:LED_0603_1608Metric", "0603"), ("Package_TO_SOT_SMD:SOT-323_SC-70", "SOT-323"),
    ("Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal", "DO-41"), ("MyLib:weird", None),
])
def test_footprint_key(fp, key):
    assert footprint_package_key(fp) == key


def test_diode_footprints():
    assert diode_footprint("SMA", led=False) == "Diode_SMD:D_SMA"
    assert diode_footprint("0603", led=True) == "LED_SMD:LED_0603_1608Metric"
    assert diode_footprint("0603", led=False) == "Diode_SMD:D_0603_1608Metric"
    assert diode_footprint("SMAF", led=False) is None


def P(lcsc, mfr, pkg, basic=False, stock=1000, manufacturer="X"):
    return Part(lcsc, mfr, manufacturer, pkg, basic, stock, 0.01, "")


PARTS = [
    P(1, "B5819W", "SOD-123", stock=10**6),
    P(2, "B5819W SL", "SOD-123", basic=True),
    P(3, "B5819W", "SOD-323", stock=10**7, manufacturer="Nexperia"),
]


def test_choose_mpn_prefers_basic_then_exact():
    assert choose_mpn("B5819W", PARTS).lcsc == 2
    assert choose_mpn("B5819W", PARTS[:1] + PARTS[2:]).lcsc == 3  # no basic: exact, highest stock


def test_choose_mpn_package_and_manufacturer_filters():
    assert choose_mpn("B5819W", PARTS, package=Package("SOD-323")).lcsc == 3
    assert choose_mpn("B5819W", PARTS, manufacturer="nexperia").lcsc == 3
    assert choose_mpn("B5819W", PARTS, package=Package("SMA")) is None


def test_find_mpn_suffix_and_like_escaping(tmp_path):
    conn = sqlite3.connect(tmp_path / "p.sqlite3")
    conn.execute("CREATE TABLE parts (lcsc INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, mfr TEXT, "
                 "package TEXT, manufacturer TEXT, library_type TEXT, description TEXT, datasheet TEXT, "
                 "price TEXT, stock INTEGER)")
    rows = [
        (1, "SS34", "SMA"), (2, "ss34-MS", "SMA"), (3, "SS345", "SMA"), (4, "SS34 X", "SMA"),
        (5, "A_B", "SOD-123"), (6, "AXB", "SOD-123"),
    ]
    conn.executemany("INSERT INTO parts VALUES (?, 'Diodes', 'Schottky Diodes', ?, ?, 'm', 'Extended', '', '', "
                     "'1-:0.01', 1000)", rows)
    conn.row_factory = sqlite3.Row
    assert sorted(p.lcsc for p in db.find_mpn(conn, "SS34", 1)) == [1, 2, 4]
    assert [p.lcsc for p in db.find_mpn(conn, "A_B", 1)] == [5]


def sym(ref, lib_id, **props):
    s = Symbol(None, lib_id, {}, [ref])
    s.prop = lambda name, _p={"Reference": ref, **props}: _p.get(name)
    s.props = {"Reference": None, **{k: None for k in props}}
    return s


def test_diode_kind():
    assert diode_kind(sym("D1", "Device:D_Schottky")) == "D"
    assert diode_kind(sym("D2", "Device:LED")) == "LED"
    assert diode_kind(sym("LED3", "Device:LED")) == "LED"
    assert diode_kind(sym("DS1", "Device:D")) is None
    assert diode_kind(sym("R1", "Device:R")) is None


def test_diode_mpn_source():
    assert _diode_mpn(sym("D1", "Device:D", Value="1N4148W")) == "1N4148W"
    assert _diode_mpn(sym("D1", "Device:D", Value="1N4148W", MPN="1N4148WS")) == "1N4148WS"
    assert _diode_mpn(sym("D1", "Device:D_Schottky", Value="D_Schottky")) is None
    assert _diode_mpn(sym("D1", "Device:LED", Value="LED GREEN")) is None
    assert _diode_mpn(sym("D1", "Device:D", Value="D")) is None
