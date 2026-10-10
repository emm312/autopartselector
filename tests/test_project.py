import json

from autopartselector.project import detect_field, ensure_bom_field


def _pro(tmp_path, fields):
    pro = {"schematic": {"bom_settings": {"fields_ordered": fields}}}
    (tmp_path / "b.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")
    return tmp_path / "b.kicad_sch"


def test_detects_field_shown_in_bom(tmp_path):
    sch = _pro(tmp_path, [{"name": "LCSC Part", "show": False}, {"name": "LCSC Part #", "show": True}])
    assert detect_field(sch, [])[0] == "LCSC Part #"


def test_default_field_and_bom_insert(tmp_path):
    sch = _pro(tmp_path, [{"name": "Reference", "show": True}])
    assert detect_field(sch, [])[0] == "LCSC"
    assert ensure_bom_field(sch, "LCSC", dry_run=True).startswith("would add")
    assert ensure_bom_field(sch, "LCSC", dry_run=False).startswith("added")
    fields = json.loads((tmp_path / "b.kicad_pro").read_text())["schematic"]["bom_settings"]["fields_ordered"]
    assert fields[-1] == {"group_by": False, "label": "LCSC", "name": "LCSC", "show": True}
    assert ensure_bom_field(sch, "LCSC", dry_run=False) is None  # already shown


def test_enables_hidden_field(tmp_path):
    sch = _pro(tmp_path, [{"name": "LCSC", "show": False, "label": "LCSC", "group_by": False}])
    assert ensure_bom_field(sch, "LCSC", dry_run=False).startswith("enabled")
