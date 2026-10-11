# autopartselector

Fills in `Footprint` and `LCSC` for the resistors, capacitors, inductors and diodes in a KiCad schematic, and
`LCSC` for everything else that has a part number (regulators, MCUs, transistors, crystals…).

For each R/C/L it picks the smallest package, no smaller than a size you choose, that meets the part's voltage,
current and power needs. Diodes and other parts are matched by part number. It prefers JLCPCB Basic parts.

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

### Other parts

Every other symbol in the BOM (`U…`, `Q…`, `Y…`, `J…`, `F…`, `FB…` and so on) is looked up by part number too, the
same way as diodes: an `MPN` field if there is one, otherwise the Value (`AMS1117-3.3`, `LM358DR`).

- Only `LCSC` is written. The footprint is never changed.
- If the symbol has a footprint in a package it recognises, only parts in that package are used: SOIC/SOP, SSOP,
  TSSOP, MSOP, QFN/DFN/SON, LQFP/TQFP, BGA, LGA, DIP, SOT-23-x, SOT-223, SOT-89, TO-92/220/247/252/263, chip sizes
  (`0603`…), SMD crystals/oscillators (`3225`…) and the diode packages. KiCad stock names and EasyEDA/JLC `plib`
  names (`SOIC-16_L10.3-W7.5…`) are both read.
- Sizes are compared too when both sides give one: SOIC/SSOP/TSSOP body width (a `SOIC-8_5.3x5.3mm` footprint only
  takes 208mil parts; a JLC listing with no width counts as 150mil for SOIC and 4.4mm for TSSOP), and QFN/DFN/LGA/BGA
  and crystal body size. Pitch and exposed pad aren't checked for QFN/DFN.
- If the footprint is unrecognised (connectors, modules), any package is allowed, so check the `Pkg` column.
- Values left as a generic symbol name (`Conn_01x04`, `Q_NMOS_GSD`) are skipped.
- If a part number isn't found, the closest stocked part whose MPN starts with it (in the footprint's package, if
  known) is shown in the Notes column, e.g. `closest TPS56339DDCR (C2071106, TSOT-23-6, …)`. It isn't written:
  copy it into an `MPN` field to use it. A lowercase `x` in a Value (`STM32F072CBTx`) matches any one character.
- If a part number from the Value isn't found, the symbol is skipped with a note. If a part number from an `MPN`
  field isn't found, or is only stocked in a different package, it counts as unresolved.
- `TP`, `H`, `MH`, `FID`, `NT` and `LOGO` references are left alone, and so are `R`/`C`/`L` symbols the passive
  matcher doesn't handle (such as polarized caps).

`--no-other` turns this off.

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
| `--no-diodes` | don't look up diodes and LEDs |
| `--no-other` | don't look up other parts by part number |
| `--net NAME=V` | voltage for a net whose name doesn't say it (repeatable) |
| `--no-net-voltage` | don't estimate voltages from nets |
| `--overwrite` | re-pick symbols that already have an `LCSC` |

Symbols that already have an LCSC number (in any `LCSC…`/`JLC…` field) are left alone. Polarized caps and anything excluded from the BOM are skipped.
Only the touched fields change in the file. A sheet used more than once gets one pick shared by all its copies,
because KiCad stores the same fields for every copy.

## Data

Part data comes from the [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) parts database.
`update` keeps every in-stock part in `~/.cache/autopartselector/parts.sqlite3`, with descriptions only for the
passives and diodes it matches on. Re-run it after upgrading from a version without other-part support (the old
`passives.sqlite3` still works for R/C/L and diodes).
