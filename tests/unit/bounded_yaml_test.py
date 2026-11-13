import time

import pytest
import yaml

from utils.functions import MAX_YAML_VALUES, safe_load_bounded_yaml


def _nested_aliases(levels):
    """Each level refers to the one below 6 times through a YAML alias."""
    inner = "[{type: text, text: x}]"
    for i in range(1, levels + 1):
        a = f"n{i}"
        inner = (
            f"[{{type: condition, condition: '1', onTrue: &{a} {inner}, onFalse: *{a}}}, "
            f"{{type: condition, condition: '1', onTrue: *{a}, onFalse: *{a}}}, "
            f"{{type: condition, condition: '1', onTrue: *{a}, onFalse: *{a}}}]"
        )
    return "{name: x, _v: 2, automation: " + inner + "}"


def test_loads_ordinary_automation():
    data = "name: Bite\n_v: 2\nautomation:\n  - type: target\n    target: each\n    effects:\n      - type: damage\n"
    assert safe_load_bounded_yaml(data)["name"] == "Bite"


def test_small_aliases_still_load():
    data = "a: &dmg {type: damage, damage: 1d6}\nb: [*dmg, *dmg]"
    assert safe_load_bounded_yaml(data)["b"][1]["damage"] == "1d6"


def test_rejects_alias_expansion_quickly():
    start = time.perf_counter()
    with pytest.raises(yaml.YAMLError):
        safe_load_bounded_yaml(_nested_aliases(10))  # under Discord's 2,000-character message limit
    assert time.perf_counter() - start < 1


def test_rejects_self_reference():
    with pytest.raises(yaml.YAMLError):
        safe_load_bounded_yaml("&a [*a]")


def test_limit_counts_expanded_values():
    shared = "x: &x [" + ", ".join(["1"] * 99) + "]\n"
    fits = shared + "y: [" + ", ".join(["*x"] * (MAX_YAML_VALUES // 100 - 2)) + "]"
    too_big = shared + "y: [" + ", ".join(["*x"] * (MAX_YAML_VALUES // 100 + 1)) + "]"
    assert safe_load_bounded_yaml(fits)
    with pytest.raises(yaml.YAMLError):
        safe_load_bounded_yaml(too_big)
