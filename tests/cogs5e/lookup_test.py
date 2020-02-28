"""
Simple lookup tests: look up every entry in test static data
"""
import pytest

from cogs5e.funcs.lookupFuncs import compendium
from tests.utils import requires_data

pytestmark = pytest.mark.asyncio


@requires_data()
async def test_rule(avrae, dhttp):
    pass  # rule data not included in static


@requires_data()
async def test_feat(avrae, dhttp):
    for feat in compendium.feats:
        avrae.message(f"!feat {feat['name']}")
        await dhttp.drain()


@requires_data()
async def test_racefeat(avrae, dhttp):
    for rfeat in compendium.rfeats:
        avrae.message(f"!racefeat {rfeat['name']}")
        await dhttp.drain()


@requires_data()
async def test_race(avrae, dhttp):
    for race in compendium.fancyraces:
        avrae.message(f"!race {race.name}")
        await dhttp.drain()


@requires_data()
async def test_classfeat(avrae, dhttp):
    for cfeat in compendium.cfeats:
        avrae.message(f"!classfeat {cfeat['name']}")
        await dhttp.drain()


@requires_data()
async def test_class(avrae, dhttp):
    for klass in compendium.classes:
        avrae.message(f"!class {klass['name']}")
        await dhttp.drain()


@requires_data()
async def test_subclass(avrae, dhttp):
    for subclass in compendium.subclasses:
        avrae.message(f"!subclass {subclass['name']}")
        await dhttp.drain()


@requires_data()
async def test_background(avrae, dhttp):
    for background in compendium.backgrounds:
        avrae.message(f"!background {background.name}")
        await dhttp.drain()


@requires_data()
async def test_monster(avrae, dhttp):
    for monster in compendium.monster_mash:
        avrae.message(f"!monster {monster.name}")
        await dhttp.drain()


@requires_data()
async def test_spell(avrae, dhttp):
    for spell in compendium.spells:
        avrae.message(f"!spell {spell.name}")
        await dhttp.drain()


@requires_data()
async def test_item(avrae, dhttp):
    for item in compendium.items:
        avrae.message(f"!item {item['name']}")
        await dhttp.drain()
