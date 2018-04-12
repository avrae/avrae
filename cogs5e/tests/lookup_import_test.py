import json

from cogs5e.models.monster import Monster


def test_deserialize_monsters():
    with open('./res/bestiary.json', 'r') as f:
        data = json.load(f)
    monster_mash = [Monster.from_data(m) for m in data]
    assert len(monster_mash) == len(data)
