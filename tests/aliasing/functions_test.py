from aliasing.api.functions import randint, randchoice
import pytest


# TODO: AliasStatBlock tests
# TODO: AliasBaseStats tests
# TODO: AliasLevels tests
# TODO: AliasAttack tests
# TODO: AliasSkill tests

# tesing the randint() and randchoice() functions, running though those looks to make sure the randomness doesn't hide bugs.
def test_randint_and_randchoice_tests():
    for i in range(100):
        r1 = randint(100)
        r2 = randint(50, 100)
        r3 = randint(10, 100, 2)
        seq = [1, 2, 3, 4, 5]
        c1 = randchoice(seq)
        
        assert r1 < 100
        
        assert r2 >=50
        assert r2 < 100
        
        assert r3 >= 10
        assert r3 % 2 == 0
        assert r3 < 100
        
        assert c1 in seq
# TODO: AliasSaves tests
# TODO: AliasResistances Tests
# TODO: AliasSpellbook Tests
# TODO: AliasSpellbookSpell tests
