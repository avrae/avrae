from aliasing.api.statblock import AliasSkill, AliasBaseStats
from cogs5e.models.sheet.base import Skill, BaseStats


# TODO: AliasStatBlock tests
# TODO: AliasBaseStats tests
def test_alias_base_stats():
    stats = BaseStats.default()
    alias_stats = AliasBaseStats(stats)

    assert alias_stats.strength == 10
    assert alias_stats.get("strength") == 10
    assert alias_stats.get_mod("strength") == 0

    assert alias_stats.dexterity == 10
    assert alias_stats.get("dexterity") == 10
    assert alias_stats.get_mod("dexterity") == 0

    assert alias_stats.constitution == 10
    assert alias_stats.get("constitution") == 10
    assert alias_stats.get_mod("constitution") == 0

    assert alias_stats.wisdom == 10
    assert alias_stats.get("wisdom") == 10
    assert alias_stats.get_mod("wisdom") == 0

    assert alias_stats.intelligence == 10
    assert alias_stats.get("intelligence") == 10
    assert alias_stats.get_mod("intelligence") == 0

    assert alias_stats.charisma == 10
    assert alias_stats.get("charisma") == 10
    assert alias_stats.get_mod("charisma") == 0

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
