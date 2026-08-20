import pytest

from cogs5e.models.automation.saveutils import parse_save_bonuses


@pytest.mark.parametrize(
    "save_type, save_bonuses, expected",
    [
        ("con", ["1d4|con"], ["1d4"]),
        ("con", ["1d4 - 1d3|con"], ["1d4-1d3"]),
        ("con", ["1d4|dex + 2|con"], ["2"]),
        ("dex", ["-2 +1d6|dex"], ["-2+1d6"]),
        ("wis", ["+1d4 +2|wis -1|con"], ["1d4+2"]),
        ("wis", ["-1|wis"], ["-1"]),
        ("dex", ["+2|dex"], ["2"]),
        ("dex", ["1d4[spell]|dex + 1d2"], ["1d4[spell]", "1d2"]),
        ("dex", ["1d4[hello world]|dex+1d4"], ["1d4[hello world]", "1d4"]),
        ("dex", ["-2[guidance]|dex-2|con"], ["-2[guidance]"]),
        ("con", ["+1d4", "1d2[abc123]|con"], ["1d4", "1d2[abc123]"]),
    ],
)
def test_parse_save_bonuses(save_type, save_bonuses, expected):
    assert set(parse_save_bonuses(save_type, save_bonuses)) == set(expected)
