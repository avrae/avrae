import d20
import pytest


def test_roll():
    assert type(d20.roll("1d20")) == d20.RollResult
    assert 0 < d20.roll("1d20").total < 21
    assert d20.roll("3+4*(9-2)").total == 31


def test_keeping_operators():
    # k, p
    r = d20.roll("10d6k1")
    assert len(r.roll.roll.keptset) == r.total  # the total is the number of 1s kept

    r = d20.roll("10d6k<11")
    assert len(r.roll.roll.keptset) == 10

    r = d20.roll("10d6p<11")
    assert len(r.roll.roll.keptset) == 0


def test_rerolling_operators():
    # rr, ro, ra, e
    r = d20.roll("4d6rr1")
    assert 8 <= r.total <= 24
    assert len([p for p in r.roll.roll.set if p.number == 1 and p.kept]) == 0

    r = d20.roll("4d6rr<3")
    assert 12 <= r.total <= 24
    assert len([p for p in r.roll.roll.set if p.number < 3 and p.kept]) == 0

    r = d20.roll("10d6ro1")
    # any 1s in the first batch should have rerolled
    assert len([p for p in r.roll.roll.set[:10] if p.number == 1 and p.kept]) == 0

    r = d20.roll("10d6ro<3")
    # any 1s or 2s in the first batch should have rerolled
    assert len([p for p in r.roll.roll.set[:10] if p.number < 3 and p.kept]) == 0

    r = d20.roll("10d2ra1")
    assert 11 <= r.total <= 21

    r = d20.roll("10d2e1")
    assert 20 <= r.total


def test_bounding_operators():
    # mi, ma
    r = d20.roll("10d2mi2")
    assert r.total == 20

    r = d20.roll("10d2ma1")
    assert r.total == 10


def test_h_l_selectors():
    r = d20.roll("10d6kl1")
    assert 1 <= r.total <= 6
    assert len(r.roll.roll.keptset) == 1
    assert len([p for p in r.roll.roll.set if not p.kept]) == 9

    r = d20.roll("10d6kh2")
    assert 2 <= r.total <= 12
    assert len(r.roll.roll.keptset) == 2
    assert len([p for p in r.roll.roll.set if not p.kept]) == 8


def test_gt_lt_selectors():
    r = d20.roll("10d6k>6")
    assert r.total == 0
    assert len(r.roll.roll.keptset) == 0
    assert len([p for p in r.roll.roll.set if not p.kept]) == 10

    r = d20.roll("10d6k<1")
    assert r.total == 0
    assert len(r.roll.roll.keptset) == 0
    assert len([p for p in r.roll.roll.set if not p.kept]) == 10

    r = d20.roll("10d6rr<6")
    assert r.total == 60

    r = d20.roll("10d6rr>1")
    assert r.total == 10

    r = d20.roll("10d6k<6")
    assert 10 <= r.total <= 50
    assert len(r.roll.roll.keptset) <= 10
    assert all(p.number < 6 for p in r.roll.roll.keptset)


def test_complex_rolls():
    r = d20.roll("10d6rol5mi6ma1k1[annotation] some comments", allow_comments=True)
    assert r.total == 10
    assert r.crit == 0
    assert "some comments" == r.comment

    r = d20.roll("5d6kh4e0kl3")
    assert 3 <= r.total <= 18
    assert len(r.roll.roll.keptset) == 3
    assert len([p for p in r.roll.roll.set if not p.kept]) == 2

    r = d20.roll("10d6kh4kl3")
    assert 7 <= r.total <= 42
    assert len(r.roll.roll.keptset) == 7
    assert len([p for p in r.roll.roll.set if not p.kept]) == 3


def test_infinite_loops():
    with pytest.raises(d20.TooManyRolls):
        d20.roll("1d1e1")

    with pytest.raises(d20.TooManyRolls):
        d20.roll("1d1e1rr1e1rr1")


def test_randomness():
    rolls = [d20.roll("1d1000").total for _ in range(100)]
    # the chance of all of them being equal is 1/1000^100, so this should be safe
    # unless, of course, I broke something horribly
    assert len(set(rolls)) > 1

    # just roll 500 d20s to make codecov happy about branches
    for _ in range(500):
        d20.roll("1d20")
