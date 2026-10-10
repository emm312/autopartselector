"""The LCSC field name a project uses, and making sure KiCad's BOM shows it."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .kicad_sch import Schematic

DEFAULT_FIELD = "LCSC"
LCSC_LIKE = re.compile(r"^(lcsc|jlc)", re.I)


def project_file(root_sch: Path) -> Path:
    return root_sch.with_suffix(".kicad_pro")


def _bom_fields(pro: dict) -> list[dict] | None:
    return pro.get("schematic", {}).get("bom_settings", {}).get("fields_ordered")


def detect_field(root_sch: Path, sheets: list[Schematic]) -> tuple[str, str]:
    """(field name, where it came from). Prefers what the project's BOM shows, then what symbols use."""
    pro = project_file(root_sch)
    if pro.exists():
        fields = _bom_fields(json.loads(pro.read_text(encoding="utf-8"))) or []
        for f in fields:
            if f.get("show") and LCSC_LIKE.match(f.get("name", "")):
                return f["name"], f"{pro.name} BOM settings"
    used = Counter(
        name for s in sheets for sym in s.symbols() for name in sym.props
        if LCSC_LIKE.match(name) and (sym.prop(name) or "").strip()
    )
    if used:
        return used.most_common(1)[0][0], "existing symbol fields"
    return DEFAULT_FIELD, "default"


def ensure_bom_field(root_sch: Path, field: str, dry_run: bool) -> str | None:
    """Show `field` in the project's BOM field list. Returns a message if something changed (or would)."""
    pro = project_file(root_sch)
    if not pro.exists():
        return None
    text = pro.read_text(encoding="utf-8")
    data = json.loads(text)
    fields = _bom_fields(data)
    if fields is None:
        return None
    entry = next((f for f in fields if f.get("name") == field), None)
    if entry is not None and entry.get("show"):
        return None
    if entry is None:
        fields.append({"group_by": False, "label": field, "name": field, "show": True})
        verb, past, msg = "add", "added", f"{field!r} to the BOM fields in {pro.name}"
    else:
        entry["show"] = True
        verb, past, msg = "enable", "enabled", f"{field!r} in the BOM fields in {pro.name}"
    if not dry_run:
        pro.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"would {verb} {msg}" if dry_run else f"{past} {msg}"
