from aliasing.api.statblock import AliasSkill
from cogs5e.models.sheet.base import Skill
import pytest


# TODO: AliasStatBlock tests
# TODO: AliasBaseStats tests
# TODO: AliasLevels tests
# TODO: AliasAttack tests
# TODO: AliasSkill tests
def test_alias_skill_comparison():
    s1 = AliasSkill(Skill(1))
    s2 = AliasSkill(Skill(2))

    assert s1 == s1
    assert s1 != s2
    assert s2 > s1
    assert s2 >= s1
    assert not s2 < s1
    assert not s2 <= s1
    assert s1 >= s1
    assert s1 <= s1

    assert s1 == 1
    assert s1 != 2
    assert s2 > 1
    assert s2 >= 1
    assert not s2 < 1
    assert not s2 <= 1
    assert s1 >= 1
    assert s1 <= 1

    assert 1 == s1
    assert 1 != s2
    assert 2 > s1
    assert 2 >= s1
    assert not 2 < s1
    assert not 2 <= s1
    assert 1 >= s1
    assert 1 <= s1

# TODO: AliasSaves tests
# TODO: AliasResistances Tests
# TODO: AliasSpellbook Tests
# TODO: AliasSpellbookSpell tests
