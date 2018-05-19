import json

from cogs5e.funcs.lookupFuncs import c
from cogs5e.models.monster import Monster, SKILL_MAP, SAVE_MAP


def test_deserialize_monsters():
    with open('./res/bestiary.json', 'r') as f:
        data = json.load(f)
    monster_mash = [Monster.from_data(m) for m in data]
    assert len(monster_mash) == len(data)


def test_monster_types():
    for monster in c.monster_mash:
        assert monster.name
        assert isinstance(monster.ac, int)
        assert isinstance(monster.hp, int)
        for skill in monster.skills.values():
            assert isinstance(skill, int)
        for save in monster.saves.values():
            assert isinstance(save, int)


def test_monster_saves():
    for monster in c.monster_mash:
        for skill in SKILL_MAP:
            assert skill in monster.skills
        for save in SAVE_MAP:
            assert save in monster.saves