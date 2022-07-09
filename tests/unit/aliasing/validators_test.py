import pytest

from aliasing.api.validators import unsafeify


class _FakeInterpreterNS:
    _str = str
    _list = list
    _set = set
    _dict = dict


def test_unsafeify_simple():
    assert unsafeify("foo", _FakeInterpreterNS) == "foo"
    assert unsafeify([1, 2, 3], _FakeInterpreterNS) == [1, 2, 3]
    assert unsafeify({1, 2, 3}, _FakeInterpreterNS) == {1, 2, 3}
    assert unsafeify({1: 1, 2: 2, 3: 3}, _FakeInterpreterNS) == {1: 1, 2: 2, 3: 3}


def test_unsafeify_nested():
    # test on the cross product of (list, set, dict) containing (list, set, dict, str)
    nested = [
        [1, 2, 3],
        {1, "foo"},  # can't contain compound things due to mutability rules
        {"list": [1, 2, 3], "set": {1, 2, 3}, "dict": {1: 1, 2: 2, 3: 3}, "str": "str"},
        "foo",
    ]
    assert unsafeify(nested, _FakeInterpreterNS) == nested


def test_unsafeify_self_references():
    get_rekt = []
    get_rekt.append(get_rekt)
    with pytest.raises(ValueError):
        unsafeify(get_rekt, _FakeInterpreterNS)

    get_rekt2 = {}
    get_rekt2["a"] = get_rekt2
    with pytest.raises(ValueError):
        unsafeify(get_rekt2, _FakeInterpreterNS)

    get_rekt3 = {}
    a = [get_rekt3]
    get_rekt3["a"] = a
    with pytest.raises(ValueError):
        unsafeify(a, _FakeInterpreterNS)


def test_unsafeify_references():
    foo = []
    bar = [foo, foo]
    assert bar[0] is bar[1]
    blep = unsafeify(bar, _FakeInterpreterNS)
    assert blep[0] is blep[1]
    blep[0].append("foo")
    assert blep[0] == blep[1]
