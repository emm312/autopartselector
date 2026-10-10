import pytest

from autopartselector.netlist import across, net_voltage


@pytest.mark.parametrize("net,v", [
    ("+3V3", 3.3), ("+1V0 MGTAVCC", 1.0), ("ETH A +1V2", 1.2), ("+HDMI 5V", 5.0), ("+5V", 5.0),
    ("/Power/+12V", 12.0), ("-12V", -12.0), ("+3.3V", 3.3), ("2V5_REF", 2.5), ("VBUS", 5.0), ("FT VBUS", 5.0),
    ("+VBUS", 5.0), ("GND", 0.0), ("AGND", 0.0), ("GNDA", 0.0), ("VSS", 0.0),
    ("3V3_PG", None), ("1V0_PG", None), ("5V_EN", None), ("+BATT", None), ("VCC", None), ("+V_{TT}", None),
    ("Net-(C12-Pad1)", None), ("/DDR3L Memory (PS)/A0", None), ("I2C1 SDA", None), ("+DDR3L", None),
])
def test_net_voltage(net, v):
    assert net_voltage(net) == v


def test_overrides():
    assert net_voltage("+BATT", {"+BATT": 4.2}) == 4.2
    assert net_voltage("/bms/VBAT", {"VBAT": 16.8}) == 16.8
    assert net_voltage("+5V", {"+5V": 5.5}) == 5.5


def test_across():
    assert across(["+5V", "GND"]) == 5
    assert across(["+12V", "+5V"]) == 7
    assert across(["-12V", "+12V"]) == 24
    assert across(["+3V3", "Net-(R1-Pad2)"]) == 3.3  # pull-up: unknown side assumed within rails
    assert across(["Net-(a)", "Net-(b)"]) is None
    assert across(["GND", "Net-(R1-Pad2)"]) is None  # pull-down: signal voltage unknown
