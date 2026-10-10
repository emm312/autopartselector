# autopartselector

Fills in `Footprint` and `LCSC` for the resistors, capacitors, inductors and diodes in a KiCad schematic.

For each R/C/L it picks the smallest package, no smaller than a size you choose, that meets the part's voltage,
current and power needs. Diodes are matched by part number. It prefers JLCPCB Basic parts.

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
- **L**: both listed currents (rated and saturation) ≥ I. If the symbol's Description or Value says `shielded`, only shielded (or molded) parts
  are used; `unshielded` does the opposite. Either one also allows power-inductor packages for that part.

### Voltage from nets

If a capacitor or resistor has no voltage given, it's estimated from the names of the nets on its pins (using
KiCad's netlist): `+3V3`, `+5V HDMI`, `ETH +1V2`, `-12V` and `VBUS` (5V) are read as rails, `GND`/`AGND`/`VSS` as 0V.
A part between two known rails gets the difference. A part between a rail and an unnamed net gets the rail. A part
between ground and an unnamed net gets no estimate. Signals like `3V3_PG` or `5V_EN` aren't treated as rails.

The estimate sets cap voltage ratings (times `--cap-derate`) and the resistor working-voltage check, but not resistor
power. A voltage you give explicitly always wins; if it's lower than the nets suggest, the report says so. Names it
can't read (`+BATT`, `VCC`) can be given with `--net +BATT=16.8`.

### Diodes

Diodes (references `D…`, `LED…`) are looked up by part number: an `MPN` field if there is one, otherwise the Value
(`1N4148W`, `SS34`, `BZT52C5V1`). Listings with a suffix, such as `B5819W SL`, also count. Among matches it prefers
Basic, then the exact part number, then stock.

- If the symbol already has a footprint, only parts in that package are used and the footprint is kept.
  If not, the footprint is set from the chosen part.
- A `Manufacturer` field limits matches to that maker.
- Values without a part number (`D`, `D_Schottky`) are reported as no match. LEDs without one (`LED GREEN`) are skipped.

### Options

| Flag | Effect |
|---|---|
| `--size` | smallest package to use (default `0603`) |
| `--max-size` | largest package to use |
| `--prefer smallest\|basic` | `smallest` (default): smallest package that fits. `basic`: smallest Basic part at any size up to `--max-size`, else smallest Extended |
| `--basic-bump N` | with `--prefer smallest`, allow up to N sizes larger to get a Basic part |
| `--cap-derate X` | cap voltage margin multiplier |
| `--min-voltage V` | minimum cap rating when none is given |
| `--res-tolerance %` | default resistor tolerance |
| `--min-stock N` | ignore parts with less stock (default 100) |
| `--allow-power-inductors` | also use non-chip inductor packages (sets LCSC only) |
| `--field NAME` | field to write the LCSC number to |
| `--mpn` | also write an `MPN` field |
| `--no-diodes` | only do R/C/L |
| `--net NAME=V` | voltage for a net whose name doesn't say it (repeatable) |
| `--no-net-voltage` | don't estimate voltages from nets |
| `--overwrite` | re-pick symbols that already have an `LCSC` |

Symbols that already have an LCSC number (in any `LCSC…`/`JLC…` field) are left alone. Polarized caps and anything excluded from the BOM are skipped.
Only the touched fields change in the file. A sheet used more than once gets one pick shared by all its copies,
because KiCad stores the same fields for every copy.

## Data

Part data comes from the [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) parts database.
`update` keeps only in-stock chip resistors, MLCCs, SMD inductors, diodes, TVS/ESD parts and indicator LEDs, in
`~/.cache/autopartselector/`. Re-run it after upgrading from a version without diode support.
