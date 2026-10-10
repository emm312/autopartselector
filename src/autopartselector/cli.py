"""autopartselector: fill Footprint + LCSC for R/C/L symbols in a KiCad schematic."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile
from pathlib import Path

import shutil
import subprocess

from . import db, kicad_sch, project, select, update
from .footprints import CHIP, footprint_for
from .parse import parse_requirement


def cmd_update(args) -> int:
    update.build(Path(args.db), Path(args.from_dir) if args.from_dir else None)
    return 0


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def cmd_assign(args) -> int:
    opts = select.Options(
        size=args.size, max_size=args.max_size, cap_derate=args.cap_derate, min_voltage=args.min_voltage,
        default_res_tolerance=args.res_tolerance / 100, basic_bump=args.basic_bump,
        allow_power_inductors=args.allow_power_inductors,
    )
    sheets, warnings = kicad_sch.load_hierarchy(Path(args.schematic))
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    root = Path(args.schematic)
    field, source = (args.field, "--field") if args.field else project.detect_field(root, sheets)
    print(f"LCSC field: {field!r} ({source})")
    conn = db.open_db(Path(args.db))
    cache: dict[str, tuple[dict, list]] = {}

    rows = []
    unresolved = 0
    for sch in sheets:
        for sym in sch.symbols():
            kind = kicad_sch.passive_kind(sym)
            if kind is None or not sym.in_bom or sym.ref.startswith("#"):
                continue
            value = sym.prop("Value") or ""
            refs = ",".join(sym.refs)
            existing = next((n for n in sym.props if project.LCSC_LIKE.match(n) and (sym.prop(n) or "").strip()), None)
            if existing and not args.overwrite:
                rows.append((refs, value, "", sym.prop(existing), "", "", "", "", f"kept existing {existing}"))
                continue
            if kind not in cache:
                parts = db.load_parts(conn, kind, args.min_stock)
                cache[kind] = (select.index_by_package(parts), select.size_ladder(parts, opts))
            by_pkg, ladder = cache[kind]

            fields = {k: sym.prop(k) or "" for k in sym.props}
            req = parse_requirement(kind, value, fields)
            notes = list(req.problems)
            choice = select.choose(req, by_pkg, ladder, opts) if req.value is not None else None
            if choice is None:
                unresolved += len(sym.refs)
                notes.append("NO MATCH")
                rows.append((refs, value, req.describe(), "-", "", "", "", "", "; ".join(notes)))
                continue
            p = choice.part
            fp = footprint_for(kind, p.package)
            if fp:
                sch.set_property(sym, "Footprint", fp)
            else:
                notes.append(f"no stock footprint for {p.package}; Footprint left as-is")
            sch.set_property(sym, field, p.lcsc_str)
            if args.mpn:
                sch.set_property(sym, "MPN", p.mfr)
            if choice.bumped_from:
                notes.append(f"bumped {choice.bumped_from}->{p.package}")
            price = f"${p.price:.4f}" if p.price is not None else "?"
            rows.append((refs, value, req.describe(), p.lcsc_str, p.package,
                         "Basic" if p.basic else "Ext", str(p.stock), price, "; ".join(notes)))

    rows.sort(key=lambda r: (r[0][:1], int("".join(ch for ch in r[0] if ch.isdigit()) or 0)))
    header = ("Ref", "Value", "Needs", "LCSC", "Pkg", "Type", "Stock", "Price", "Notes")
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header) - 1)]
    for r in [header, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)) + "  " + r[-1])

    changed = [s for s in sheets if s.edits]
    for s in changed:
        new = s.render()
        if args.dry_run:
            sys.stdout.writelines(difflib.unified_diff(
                s.text.splitlines(True), new.splitlines(True), str(s.path), str(s.path) + " (new)"))
        else:
            _write_atomic(s.path, new)
    bom_msg = project.ensure_bom_field(root, field, args.dry_run)
    if bom_msg:
        print(bom_msg)
    n_parts = sum(len(r[0].split(",")) for r in rows)
    n_basic = sum(len(r[0].split(",")) for r in rows if r[5] == "Basic")
    n_kept = sum(len(r[0].split(",")) for r in rows if r[-1].startswith("kept existing"))
    print(f"\n{n_parts} passives ({len(rows)} symbols), {n_basic} basic, {n_kept} kept, {unresolved} unresolved; "
          f"{'would change' if args.dry_run else 'updated'} {len(changed)} file(s)")
    if changed and not args.dry_run:
        print("If the schematic is open in KiCad, close it without saving and reopen.", file=sys.stderr)
    return 1 if unresolved else 0


def cmd_bom(args) -> int:
    kicad_cli = shutil.which("kicad-cli")
    if not kicad_cli:
        raise SystemExit("kicad-cli not found on PATH")
    root = Path(args.schematic)
    sheets, _ = kicad_sch.load_hierarchy(root)
    field = args.field or project.detect_field(root, sheets)[0]
    out = Path(args.output) if args.output else root.with_name(root.stem + "-jlcpcb-bom.csv")
    cmd = [
        kicad_cli, "sch", "export", "bom", "-o", str(out),
        "--fields", f"Value,Reference,Footprint,{field}",
        "--labels", "Comment,Designator,Footprint,LCSC Part #",
        "--group-by", f"Value,Footprint,{field}",
        "--ref-range-delimiter", "",
        "--exclude-dnp",
        str(root),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        return r.returncode
    print(f"wrote {out} (LCSC from field {field!r})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="autopartselector", description=__doc__)
    ap.add_argument("--db", default=str(update.default_db_path()), help="passives DB path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("update", help="download + build the passives DB (~1GB streamed, ~75MB stored)")
    u.add_argument("--from-dir", help="read parts-fts5.db.zip.* chunks from this dir instead of downloading")
    u.set_defaults(func=cmd_update)

    a = sub.add_parser("assign", help="pick parts for passives in a schematic (and its sub-sheets)")
    a.add_argument("schematic")
    a.add_argument("--size", default="0603", choices=list(CHIP), help="preferred (smallest) package")
    a.add_argument("--max-size", choices=list(CHIP), help="never go bigger than this")
    a.add_argument("--min-stock", type=int, default=100)
    a.add_argument("--cap-derate", type=float, default=1.0, help="cap voltage rating >= V * this")
    a.add_argument("--min-voltage", type=float, help="minimum cap voltage rating when none is given")
    a.add_argument("--res-tolerance", type=float, default=1.0, help="default resistor tolerance, %%")
    a.add_argument("--basic-bump", type=int, default=0,
                   help="allow up to N sizes larger than the smallest match to get a Basic part")
    a.add_argument("--allow-power-inductors", action="store_true",
                   help="also consider non-chip inductor packages (LCSC only, no footprint)")
    a.add_argument("--field", help="LCSC field name (default: what the project's BOM uses, else LCSC)")
    a.add_argument("--mpn", action="store_true", help="also write an MPN field")
    a.add_argument("--overwrite", action="store_true", help="re-pick symbols that already have an LCSC field")
    a.add_argument("--dry-run", action="store_true", help="print a diff instead of writing")
    a.set_defaults(func=cmd_assign)

    b = sub.add_parser("bom", help="export a JLCPCB assembly BOM CSV (via kicad-cli)")
    b.add_argument("schematic")
    b.add_argument("-o", "--output", help="default: <schematic>-jlcpcb-bom.csv")
    b.add_argument("--field", help="LCSC field name (default: detected as for assign)")
    b.set_defaults(func=cmd_bom)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
