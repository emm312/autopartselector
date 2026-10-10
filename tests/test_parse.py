import math

import pytest

from autopartselector.parse import classify_token, parse_requirement, parse_si


@pytest.mark.parametrize("tok,want", [
    ("10k", 10e3), ("4k7", 4.7e3), ("2R2", 2.2), ("0R1", 0.1), ("10R", 10), ("1M", 1e6), ("100mΩ", 0.1),
    ("100n", 100e-9), ("4n7", 4.7e-9), ("0.1uF", 0.1e-6), ("10µF", 10e-6), ("4.7uH", 4.7e-6), ("50", 50),
    ("10kΩ", 10e3), ("1kohm", 1e3), ("470p", 470e-12),
])
def test_parse_si(tok, want):
    assert math.isclose(parse_si(tok), want)


@pytest.mark.parametrize("tok", ["R", "C", "", "abc", "DNP"])
def test_parse_si_junk(tok):
    assert parse_si(tok) is None


@pytest.mark.parametrize("tok,want", [
    ("25V", ("voltage", 25.0)), ("500mA", ("current", 0.5)), ("1/4W", ("power", 0.25)),
    ("62.5mW", ("power", 0.0625)), ("±1%", ("tolerance", 0.01)), ("X7R", ("dielectric", "X7R")),
    ("NP0", ("dielectric", "C0G")), ("8@100MHz", None), ("-55℃~+155℃", None),
])
def test_classify(tok, want):
    got = classify_token(tok)
    if want is None:
        assert got is None
    else:
        assert got[0] == want[0] and (got[1] == want[1] or math.isclose(got[1], want[1]))


def test_requirement_fields_override_value_tokens():
    r = parse_requirement("C", "10u 16V", {"Voltage": "25V", "Dielectric": "x5r", "Datasheet": "~"})
    assert math.isclose(r.value, 10e-6) and r.voltage == 25 and r.dielectric == "X5R"
    assert not r.problems


def test_requirement_problems():
    r = parse_requirement("R", "R", {})
    assert r.value is None and r.problems
