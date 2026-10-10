import sqlite3

import pytest

from autopartselector import cli
from autopartselector.db import Part
from autopartselector.footprints import footprint_package_key, package_key
from autopartselector.kicad_sch import Schematic
from autopartselector.select import choose_mpn
from test_diodes import sym


@pytest.mark.parametrize("pkg,key", [
    ("SOP-8", "SOIC-8"), ("SOIC-8_150mil", "SOIC-8"), ("ESOP-8", "SOIC-8-EP"), ("SOT-25", "SOT-23-5"),
    ("TSOT-23-6", "SOT-23-6"), ("SOT-223-3", "SOT-223"), ("QFN-32-EP(5x5)", "QFN-32"), ("WQFN-16(3x3)", "QFN-16"),
    ("DFN-8(2x2)", "DFN-8"), ("LQFP-48(7x7)", "LQFP-48"), ("TO-252-2(DPAK)", "TO-252"), ("HTSSOP-20", "TSSOP-20-EP"),
    ("SOT-23(TO-236)", "SOT-23"), ("SC-70-5", "SOT-353"), ("SOT223", "SOT-223"), ("SOT-23-5L", "SOT-23-5"),
    ("SOT-223-3L", "SOT-223"), ("TO-252-2L", "TO-252"), ("SO-8", "SOIC-8"), ("SOIC-16-300mil", "SOIC-16W"),
    ("SSOP-20-208mil", "SSOP-20"), ("VSSOP-8-0.65mm", "VSSOP-8"), ("DFN-8L(3x3)", "DFN-8"),
    ("WSON-6-EP(2x2)", "DFN-6"), ("SOT-563", "SOT-563"), ("SOT-666", "SOT-666"), ("TO-220F", None),
])
def test_ic_package_key(pkg, key):
    assert package_key(pkg) == key


@pytest.mark.parametrize("fp,key", [
    ("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "SOIC-8"),
    ("Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm", "SOIC-8-EP"),
    ("Package_TO_SOT_SMD:SOT-223-3_TabPin2", "SOT-223"),
    ("Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm", "QFN-32"),
    ("Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm", "TSSOP-20"),
    ("Package_TO_SOT_SMD:TSOT-23-5", "SOT-23-5"),
    ("Package_TO_SOT_SMD:TO-252-2", "TO-252"),
    ("Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", "SOIC-16W"),
    ("Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", None),
])
def test_ic_footprint_key(fp, key):
    assert footprint_package_key(fp) == key


def test_choose_mpn_ic_package():
    parts = [Part(1, "LM358", "X", "SOP-8", True, 1000, 0.1, ""),
             Part(2, "LM358", "X", "TSSOP-8", False, 5000, 0.1, "")]
    assert choose_mpn("LM358", parts, package_key="SOIC-8").lcsc == 1
    assert choose_mpn("LM358", parts, package_key="TSSOP-8").lcsc == 2
    assert choose_mpn("LM358", parts, package_key="QFN-8") is None


def _symbol(lib_id, ref, value, footprint="", **extra):
    props = {"Reference": ref, "Value": value, "Footprint": footprint, **extra}
    body = "".join(f'\t\t(property "{k}" "{v}"\n\t\t\t(at 0 0 0)\n\t\t)\n' for k, v in props.items())
    return f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(in_bom yes)\n{body}\t)\n'


def test_assign_other_parts(tmp_path, capsys):
    dbp = tmp_path / "parts.sqlite3"
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE parts (lcsc INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, mfr TEXT, "
                 "package TEXT, manufacturer TEXT, library_type TEXT, description TEXT, datasheet TEXT, "
                 "price TEXT, stock INTEGER)")
    conn.executemany("INSERT INTO parts VALUES (?, 'x', ?, ?, ?, 'm', ?, NULL, NULL, '1-:0.1', 1000)", [
        (6186, "Linear Voltage Regulators (LDO)", "AMS1117-3.3", "SOT-223", "Basic"),
        (7, "Linear Voltage Regulators (LDO)", "AMS1117-3.3", "SOT-89", "Extended"),
        (8, "Operational Amplifier", "LM358DR", "SOIC-8", "Extended"),
        (2869734, "Power Switches", "LM66100DCKR", "SC-70-6", "Extended"),
        (10, "Power Switches", "LM66100DCKT", "SOT-23-6", "Extended"),
    ])
    conn.commit()
    conn.close()
    sch = tmp_path / "b.kicad_sch"
    sch.write_text("(kicad_sch\n\t(version 20231120)\n"
                   + _symbol("Regulator_Linear:AMS1117-3.3", "U1", "AMS1117-3.3",
                             "Package_TO_SOT_SMD:SOT-223-3_TabPin2")
                   + _symbol("Connector:Conn_01x04", "J1", "Conn_01x04")
                   + _symbol("Amplifier_Operational:LM358", "U2", "LM358", "Package_SO:TSSOP-8_4.4x3mm_P0.65mm",
                             MPN="LM358DR")
                   + _symbol("MCU:STM32", "U3", "STM32F103C8Tx")
                   + _symbol("Device:Q_NMOS_GSD", "Q1", "Q_NMOS_GSD")
                   + _symbol("Power_Management:LM66100DCK", "U4", "LM66100DCK",
                             "Package_TO_SOT_SMD:SOT-363_SC-70-6")
                   + ")\n")

    rc = cli.main(["--db", str(dbp), "assign", str(sch), "--no-net-voltage"])
    out = capsys.readouterr().out
    syms = {s.ref: s for s in Schematic(sch).symbols()}
    assert syms["U1"].prop("LCSC") == "C6186"  # SOT-223 matches the footprint, not the SOT-89 one
    assert syms["U1"].prop("Footprint") == "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
    assert syms["J1"].prop("LCSC") is None and syms["Q1"].prop("LCSC") is None
    assert syms["U3"].prop("LCSC") is None and "add an MPN field" in out
    assert syms["U2"].prop("LCSC") is None and "stocked in SOIC-8" in out  # explicit MPN, wrong package
    # prefix match is only suggested, in the package the footprint asks for
    assert syms["U4"].prop("LCSC") is None
    assert "closest LM66100DCKR (C2869734, SC-70-6" in out and "LM66100DCKT" not in out
    assert "1 unresolved" in out and rc == 1


def test_no_other_flag(tmp_path, capsys):
    sch = tmp_path / "b.kicad_sch"
    sch.write_text("(kicad_sch\n" + _symbol("Regulator_Linear:AMS1117-3.3", "U1", "AMS1117-3.3") + ")\n")
    dbp = tmp_path / "parts.sqlite3"
    sqlite3.connect(dbp).execute("CREATE TABLE parts (lcsc INTEGER)").connection.close()
    assert cli.main(["--db", str(dbp), "assign", str(sch), "--no-net-voltage", "--no-other"]) == 0
    assert "0 parts" in capsys.readouterr().out


def test_other_mpn_source():
    assert cli._other_mpn(sym("U1", "Regulator_Linear:AMS1117-3.3", Value="AMS1117-3.3")) == ("AMS1117-3.3", False)
    assert cli._other_mpn(sym("J1", "Connector:Conn_01x04", Value="Conn_01x04")) == (None, False)
    assert cli._other_mpn(sym("SW2", "Switch:SW_Push", Value="K0")) == (None, False)
    assert cli._other_mpn(sym("Y2", "Device:Crystal", Value="25M")) == (None, False)
    assert cli._other_mpn(sym("SW2", "Switch:SW_Push", Value="K0", MPN="K0")) == ("K0", True)
    assert cli._other_mpn(sym("U1", "x:y", Value="LDO", MPN="TLV75533PDBVR")) == ("TLV75533PDBVR", True)
    assert cli.other_kind(sym("U1", "x:y")) and cli.other_kind(sym("FB1", "x:y"))
    assert not cli.other_kind(sym("TP1", "x:y")) and not cli.other_kind(sym("C5", "Device:C_Polarized"))


def test_find_mpn_prefix_wildcard(tmp_path):
    conn = sqlite3.connect(tmp_path / "p.sqlite3")
    conn.execute("CREATE TABLE parts (lcsc INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, mfr TEXT, "
                 "package TEXT, manufacturer TEXT, library_type TEXT, description TEXT, datasheet TEXT, "
                 "price TEXT, stock INTEGER)")
    conn.executemany("INSERT INTO parts VALUES (?, 'x', 'MCU', ?, 'LQFP-48', 'm', 'Extended', '', '', '', ?)",
                     [(1, "STM32F072CBT6", 500), (2, "STM32F072CBT7", 900), (3, "STM32F072RBT6", 900)])
    conn.row_factory = sqlite3.Row
    from autopartselector import db
    assert [p.lcsc for p in db.find_mpn_prefix(conn, "STM32F072CBTx", 1, None)] == [2, 1]
    assert [p.lcsc for p in db.find_mpn_prefix(conn, "STM32F072", 1, None)] == [2, 3, 1]
