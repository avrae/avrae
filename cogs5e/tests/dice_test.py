from cogs5e.funcs.dice import roll, DiceResult


def test_roll():
    assert type(roll("1d20")) == DiceResult
    assert 0 < roll("1d20").total < 21
    assert roll("3+4*(9-2)").total == 31

def test_complex_roll():
    r = roll("10d6rol5kh3mi6ma1[annotation] some comments")
    assert r.total == 3
    assert r.crit == 0
    assert "some comments" in r.result
