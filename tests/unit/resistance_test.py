from cogs5e.models.sheet.resistance import Resistance, Resistances


def test_simple_resistance():
    fire = Resistance("fire")

    assert fire.applies_to_str("fire")
    assert fire.applies_to_str("magical fire")
    assert fire.applies_to_str("everything's on fire")
    assert fire.applies_to_str("fire truck")
    assert not fire.applies_to_str("cold")


def test_resistance_unless():
    fire = Resistance("fire", unless=["magical"])  # nonmagical fire

    assert fire.applies_to_str("fire")
    assert not fire.applies_to_str("magical fire")
    assert fire.applies_to_str("everything's on fire")
    assert fire.applies_to_str("fire truck")
    assert not fire.applies_to_str("cold")


def test_resistance_only():
    fire = Resistance("fire", only=["magical"])  # magical fire

    assert not fire.applies_to_str("fire")
    assert fire.applies_to_str("magical fire")
    assert not fire.applies_to_str("everything's on fire")
    assert not fire.applies_to_str("fire truck")
    assert not fire.applies_to_str("cold")


def test_resistance_complex():
    fire = Resistance("fire", unless=["magical"], only=["cold"])  # nonmagical cold fire

    assert not fire.applies_to_str("fire")
    assert not fire.applies_to_str("magical fire")
    assert not fire.applies_to_str("everything's on fire")
    assert not fire.applies_to_str("fire truck")
    assert not fire.applies_to_str("cold")
    assert fire.applies_to_str("cold fire")
    assert not fire.applies_to_str("cold magical fire")


def test_resistance_equality():
    assert Resistance("fire") == Resistance("fire")
    assert Resistance("cold") != Resistance("fire")

    assert Resistance("fire", unless=["magical"]) == Resistance("fire", unless={"magical"})
    assert Resistance("fire", unless=["magical"]) != Resistance("fire")
    assert Resistance("fire", unless=["magical"]) != Resistance("fire", only=["magical"])

    assert Resistance("fire", unless=["abc"], only=["def"]) == Resistance("fire", unless={"abc"}, only=["def"])
    assert Resistance("fire", unless=["abc"], only=["def"]) != Resistance("fire", only=["def"])


def test_resistance_from_str():
    assert Resistance("fire") == Resistance.from_str("fire")
    assert Resistance("fire", unless=["magical"]) == Resistance.from_str("nonmagical fire")
    assert Resistance("fire", only=["magical"]) == Resistance.from_str("magical fire")
    assert Resistance("fire", unless=["abc"], only=["def"]) == Resistance.from_str("nonabc def fire")
    assert Resistance("fire", only=["cold"]) == Resistance.from_str("cold fire")
    assert Resistance("cold", only=["fire"]) == Resistance.from_str("fire cold")


def test_resistances_util_methods():
    r = Resistances(
        resist=[Resistance.from_str("resist"), Resistance.from_str("resist neutral")],
        immune=[Resistance.from_str("immune"), Resistance.from_str("immune neutral")],
        vuln=[Resistance.from_str("vuln"), Resistance.from_str("vuln neutral")],
        neutral=[Resistance("neutral")],
    )
    assert r.is_resistant("resist")
    assert not r.is_resistant("resist neutral")
    assert r.is_immune("immune")
    assert not r.is_immune("immune neutral")
    assert r.is_vulnerable("vuln")
    assert not r.is_vulnerable("vuln neutral")
    assert r.is_neutral("neutral")
    assert r.is_neutral("resist neutral")
    assert r.is_neutral("immune neutral")
    assert r.is_neutral("vuln neutral")
    assert not r.is_neutral("foo")
