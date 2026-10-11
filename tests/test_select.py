import math

from autopartselector.db import Part, parse_description
from autopartselector.parse import parse_requirement
from autopartselector.select import Options, choose, index_by_package, size_ladder


def part(lcsc, kind, pkg, desc, basic=False, stock=1000, price=0.01):
    p = Part(lcsc, "MPN", "Mfr", pkg, basic, stock, price, desc)
    parse_description(kind, desc, p)
    return p


def pick(kind, value, parts, **kw):
    opts = Options(**kw)
    return choose(parse_requirement(kind, value, {}), index_by_package(parts), size_ladder(parts, opts), opts)


CAPS = [
    part(1, "C", "0402", "100nF 16V X7R ±10%", basic=True),
    part(2, "C", "0603", "100nF 50V X7R ±10%", basic=True),
    part(3, "C", "0603", "100nF 50V X7R ±10%", stock=10**7),
    part(4, "C", "0805", "100nF 100V X7R ±10%"),
    part(5, "C", "1206", "100nF 100V X7R ±10%", basic=True),
    part(6, "C", "0603", "100nF 50V Y5V ±20%", basic=True),
]


def test_prefers_smallest_size_from_preferred():
    assert pick("C", "100n", CAPS, size="0402").part.lcsc == 1
    assert pick("C", "100n", CAPS, size="0603").part.lcsc == 2  # basic beats higher-stock extended


def test_bumps_for_voltage():
    c = pick("C", "100n 100V", CAPS, size="0603")
    assert c.part.lcsc == 4 and c.bumped_from == "0603"


def test_basic_bump_allows_bigger_basic():
    assert pick("C", "100n 100V", CAPS, size="0603", basic_bump=1).part.lcsc == 5


def test_prefer_basic():
    assert pick("C", "100n 100V", CAPS, size="0603", prefer="smallest").part.lcsc == 4
    assert pick("C", "100n 100V", CAPS, size="0603", prefer="basic").part.lcsc == 5
    assert pick("C", "100n 100V", CAPS, size="0603", prefer="basic", max_size="0805").part.lcsc == 4
    assert pick("C", "100n", CAPS, size="0402", prefer="basic").part.lcsc == 1  # smallest Basic still wins


def test_max_size():
    assert pick("C", "100n 100V", CAPS, size="0603", max_size="0603") is None


def test_derate():
    assert pick("C", "100n 50V", CAPS, size="0603", cap_derate=1.5).part.lcsc == 4


def test_resistor_power_from_current():
    rs = [
        part(10, "R", "0603", "-55℃~+155℃ 100mW 100mΩ 75V Thick Film Resistor ±1% ±100ppm/℃", basic=True),
        part(11, "R", "1206", "-55℃~+155℃ 250mW 100mΩ 200V Thick Film Resistor ±1%"),
        part(12, "R", "2512", "-55℃~+155℃ 1W 100mΩ 200V Thick Film Resistor ±1%"),
        part(13, "R", "0603", "100mW 100mΩ 75V Thick Film Resistor ±5%", basic=True),
    ]
    assert pick("R", "0R1", rs).part.lcsc == 10
    assert pick("R", "0R1 1A", rs).part.lcsc == 10  # I²R = 0.1W, exactly the 0603 rating
    assert pick("R", "0R1 1.5A", rs).part.lcsc == 11  # 0.225W
    assert pick("R", "0R1 2A", rs).part.lcsc == 12  # 0.4W
    assert pick("R", "0R1 5%", rs).part.lcsc == 10


def test_inductor_current_uses_lowest_rating():
    ls = [
        part(20, "L", "0603", "1.45Ω 10uH 500mA 800mA Molded Inductor ±20%"),
        part(21, "L", "0805", "0.5Ω 10uH 1A 1.2A ±20%"),
        part(22, "L", "SMD,4x4mm", "50mΩ 10uH 3A 4A ±20%"),
    ]
    assert pick("L", "10uH 600mA", ls).part.lcsc == 21
    assert pick("L", "10uH 2A", ls) is None
    assert pick("L", "10uH 2A", ls, allow_power_inductors=True).part.lcsc == 22
    assert math.isclose(ls[0].value, 10e-6)


def test_shielded_inductors():
    ls = [
        part(30, "L", "0805", "10uH 1A 1.2A Multilayer inductor ±20%", basic=True),
        part(31, "L", "1210", "10uH 1.2A 1.5A 100mΩ Unshielded Inductor ±20%"),
        part(32, "L", "SMD,4x4mm", "10uH 2A 2.5A 50mΩ Magnetic Shielded Inductor ±20%"),
        part(33, "L", "SMD,5x5mm", "10uH 3A 4A 30mΩ Molded Inductor ±20%"),
    ]
    assert [p.shielded for p in ls] == [None, False, True, True]
    assert pick("L", "10uH", ls).part.lcsc == 30
    assert pick("L", "10uH shielded", ls, allow_power_inductors=True).part.lcsc == 32
    assert pick("L", "10uH 2.5A shielded", ls, allow_power_inductors=True).part.lcsc == 33
    assert pick("L", "10uH unshielded", ls).part.lcsc == 31


def test_similar_size_prefers_stock_footprint():
    ls = [
        part(40, "L", "SMD,2x1.2mm", "10uH 1A 1A Molded Inductor ±20%", stock=10**6),
        part(41, "L", "0805", "10uH 1A 1A Molded Inductor ±20%"),
    ]
    assert pick("L", "10uH shielded", ls, allow_power_inductors=True).part.lcsc == 41


def test_shield_request_from_description():
    from autopartselector.parse import parse_requirement
    r = parse_requirement("L", "4.7uH 2A", {"Description": "Shielded power inductor"})
    assert r.shielded is True and not r.problems and r.current == 2
    assert parse_requirement("L", "4.7uH", {"Description": "Inductor"}).shielded is None
    assert parse_requirement("L", "4.7uH non-shielded", {}).shielded is False
    assert parse_requirement("C", "1u shielded", {}).shielded is None


def test_implausible_inductor_listings():
    from autopartselector.db import implausible_inductor
    # JLC lists a 4x4mm molded inductor as "0402"; a genuine 0402 can't hold 2.2uH at 3A
    assert implausible_inductor(part(1, "L", "0402", "2.2uH 3A 58mΩ 5A Molded Inductor ±20%"))
    assert implausible_inductor(part(2, "L", "0201", "13@500MHz 250mΩ 3nH 450A 9.5GHz Multilayer inductor"))
    assert implausible_inductor(part(3, "L", "SMD,4x3.1mm", "0.6mΩ 45A 53uH ±25%"))
    # the best genuine parts in each class stay
    assert not implausible_inductor(part(4, "L", "0402", "1.15A 1A 1uH 300mΩ ±20%"))
    assert not implausible_inductor(part(5, "L", "1210", "1.9A 2.1A 22uH 315mΩ Molded Inductor ±20%"))
    assert not implausible_inductor(part(6, "L", "SMD,16.5x15.5mm", "15uH 22A 25.5A 7.5mΩ ±20%"))
    assert not implausible_inductor(part(7, "L", "0402", "10nH 300mA ±5%"))
