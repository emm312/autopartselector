from pathlib import Path

import pytest

from autopartselector.kicad_sch import Schematic, load_hierarchy, parse, passive_kind

GOLDEN = Path(__file__).resolve().parents[2] / "schem-gen" / "fixtures" / "golden"
FIXTURES = sorted(GOLDEN.glob("*/*.kicad_sch")) if GOLDEN.exists() else []

MINI = '''(kicad_sch
	(version 20231120)
	(symbol
		(lib_id "Device:R")
		(in_bom yes)
		(property "Reference" "R1"
			(at 0 0 0)
		)
		(property "Value" "10k"
			(at 0 0 0)
		)
		(property "Footprint" ""
			(at 0 0 0)
			(effects
				(hide yes)
			)
		)
		(property "Datasheet" "~"
			(at 1 2 0)
			(effects
				(hide yes)
			)
		)
	)
	(symbol
		(lib_id "Device:C_Polarized")
		(property "Reference" "C1"
			(at 0 0 0)
		)
	)
)
'''


@pytest.mark.skipif(not FIXTURES, reason="schem-gen fixtures not present")
@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    s = Schematic(path)
    assert s.render() == s.text
    assert s.root.head == "kicad_sch"


def test_set_and_add_properties(tmp_path):
    p = tmp_path / "t.kicad_sch"
    p.write_text(MINI)
    s = Schematic(p)
    r1, c1 = s.symbols()
    assert passive_kind(r1) == "R" and passive_kind(c1) is None
    assert s.set_property(r1, "Footprint", "Resistor_SMD:R_0603_1608Metric")
    assert s.set_property(r1, "LCSC", "C25804")
    assert s.set_property(r1, "MPN", 'odd "name"')
    out = s.render()
    again = Schematic.__new__(Schematic)
    again.text, again.root, again.edits, again.path = out, parse(out), [], p
    r1b = again.symbols()[0]
    assert r1b.prop("Footprint") == "Resistor_SMD:R_0603_1608Metric"
    assert r1b.prop("LCSC") == "C25804"
    assert r1b.prop("MPN") == 'odd "name"'
    assert list(r1b.props) == ["Reference", "Value", "Footprint", "Datasheet", "LCSC", "MPN"]
    assert '(property "LCSC" "C25804"\n\t\t\t(at 1 2 0)\n\t\t\t(effects\n\t\t\t\t(hide yes)' in out


def test_unchanged_value_is_noop(tmp_path):
    p = tmp_path / "t.kicad_sch"
    p.write_text(MINI)
    s = Schematic(p)
    r1 = s.symbols()[0]
    assert not s.set_property(r1, "Value", "10k")
    assert s.render() == MINI


def _sheet(file, uuid):
    return f'''	(sheet
		(uuid "{uuid}")
		(property "Sheetname" "{uuid}"
			(at 0 0 0)
		)
		(property "Sheetfile" "{file}"
			(at 0 0 0)
		)
	)
'''


def test_hierarchy_reused_sheet_and_missing_file(tmp_path):
    (tmp_path / "root.kicad_sch").write_text(
        '(kicad_sch\n\t(uuid "ROOT")\n' + _sheet("child.kicad_sch", "A") + _sheet("child.kicad_sch", "B")
        + _sheet("gone.kicad_sch", "C") + ")\n")
    (tmp_path / "child.kicad_sch").write_text('''(kicad_sch
	(uuid "CHILD")
	(symbol
		(lib_id "Device:R")
		(property "Reference" "R1"
			(at 0 0 0)
		)
		(property "Value" "10k"
			(at 0 0 0)
		)
		(instances
			(project "p"
				(path "/ROOT/A"
					(reference "R1")
					(unit 1)
				)
				(path "/ROOT/B"
					(reference "R101")
					(unit 1)
				)
				(path "/OTHERPROJECT/X"
					(reference "R7")
					(unit 1)
				)
			)
		)
	)
)
''')
    sheets, warnings = load_hierarchy(tmp_path / "root.kicad_sch")
    assert len(sheets) == 2
    assert len(warnings) == 1 and "gone.kicad_sch" in warnings[0]
    child = next(s for s in sheets if s.path.name == "child.kicad_sch")
    assert child.instance_paths == {"/ROOT/A", "/ROOT/B"}
    assert child.symbols()[0].refs == ["R1", "R101"]
