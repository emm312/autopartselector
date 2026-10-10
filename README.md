# autopartselector

Fills in `Footprint` and `LCSC` for the resistors, capacitors and inductors in a KiCad schematic.

For each passive it picks the smallest package, no smaller than a size you choose, that meets the part's voltage,
current and power needs. It prefers JLCPCB Basic parts.

## Install

```sh
uv tool install --editable .
autopartselector update        # build the local parts DB; re-run to refresh stock
```

## Use

```sh
autopartselector assign board.kicad_sch --size 0603 --dry-run   # show picks and the diff
autopartselector assign board.kicad_sch --size 0603             # write them
```

Pass the root sheet; sub-sheets are included. Close the schematic in KiCad before writing.

The part number goes in the LCSC field your project's BOM already uses (for example `LCSC Part #`). If there isn't
one, it uses `LCSC` and adds it to the project's BOM fields. Use `--field` to choose a different name.

```sh
autopartselector bom board.kicad_sch    # board-jlcpcb-bom.csv: Comment, Designator, Footprint, LCSC Part #
```

### Ratings

Put them after the value, or in symbol fields (fields take precedence):

- Value: `10u 25V`, `100n 50V X7R`, `0R1 2A`, `10k 1/4W 0.1%`, `4.7uH 1.5A`
- Fields: `Voltage`, `Current`, `Power`, `Tolerance`, `Dielectric`

What each rating means:

- **R**: power ≥ the largest of P, I²R and V²/R. Tolerance defaults to 1%.
- **C**: voltage rating ≥ V × `--cap-derate` (default 1). If no dielectric is given, any of C0G, X5R, X6S, X7R,
  X7S or X8R is allowed.
- **L**: both listed currents (rated and saturation) ≥ I.

### Options

| Flag | Effect |
|---|---|
| `--size` | smallest package to use (default `0603`) |
| `--max-size` | largest package to use |
| `--basic-bump N` | allow up to N sizes larger to get a Basic part |
| `--cap-derate X` | cap voltage margin multiplier |
| `--min-voltage V` | minimum cap rating when none is given |
| `--res-tolerance %` | default resistor tolerance |
| `--min-stock N` | ignore parts with less stock (default 100) |
| `--allow-power-inductors` | also use non-chip inductor packages (sets LCSC only) |
| `--field NAME` | field to write the LCSC number to |
| `--mpn` | also write an `MPN` field |
| `--overwrite` | re-pick symbols that already have an `LCSC` |

Symbols that already have an LCSC number (in any `LCSC…`/`JLC…` field) are left alone. Polarized caps and anything excluded from the BOM are skipped.
Only the touched fields change in the file. A sheet used more than once gets one pick shared by all its copies,
because KiCad stores the same fields for every copy.

## Data

Part data comes from the [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) parts database.
`update` keeps only in-stock chip resistors, MLCCs and SMD inductors, in `~/.cache/autopartselector/`.
