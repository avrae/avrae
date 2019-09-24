from cogs5e.funcs.dice import roll, DiceResult


def test_roll():
    assert type(roll("1d20")) == DiceResult
    assert 0 < roll("1d20").total < 21
    assert roll("3+4*(9-2)").total == 31


def test_complex_rolls():
    r = roll("10d6rol5mi6ma1k1[annotation] some comments")
    assert r.total == 10
    assert r.crit == 0
    assert "some comments" in r.result

    r = roll("5d6kh4e0kl3")
    assert 3 <= r.total <= 18
    assert len([p for p in r.raw_dice.parts[0].rolled if p.kept]) == 3
    assert len([p for p in r.raw_dice.parts[0].rolled if not p.kept]) == 2

    r = roll("10d6kh4kl3")
    assert 7 <= r.total <= 42
    assert len([p for p in r.raw_dice.parts[0].rolled if p.kept]) == 7
    assert len([p for p in r.raw_dice.parts[0].rolled if not p.kept]) == 3


def test_gt_lt_selectors():
    r = roll("10d6k>6")
    assert r.total == 0
    assert len([p for p in r.raw_dice.parts[0].rolled if p.kept]) == 0
    assert len([p for p in r.raw_dice.parts[0].rolled if not p.kept]) == 10

    r = roll("10d6k<1")
    assert r.total == 0
    assert len([p for p in r.raw_dice.parts[0].rolled if p.kept]) == 0
    assert len([p for p in r.raw_dice.parts[0].rolled if not p.kept]) == 10

    r = roll("10d6rr<6")
    assert r.total == 60

    r = roll("10d6rr>1")
    assert r.total == 10

    r = roll("10d6k<6")
    assert 10 <= r.total <= 50
    assert len([p for p in r.raw_dice.parts[0].rolled if p.kept]) <= 10
    assert all(p.value < 6 for p in r.raw_dice.parts[0].rolled if p.kept)


def test_infinite_loops():
    r = roll("1d1e1")
    assert r.total == 1001  # 1 + 1000 rerolls

    r = roll("1d1e1rr1e1rr1")
    assert r.total == 0  # error


def test_randomness():
    rolls = [roll("1d1000").total for _ in range(100)]
    # the chance of all of them being equal is 1/1000^100, so this should be safe
    # unless, of course, I broke something horribly
    assert len(set(rolls)) > 1
