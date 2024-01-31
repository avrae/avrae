"""
Simple lookup tests: look up every entry in test static data
"""

import itertools

import disnake
import pytest

from gamedata.compendium import compendium
from tests.utils import requires_data

pytestmark = pytest.mark.asyncio

NOT_AVAILABLE_EMBED = disnake.Embed(title="Connect your D&D Beyond account to view .+")


@requires_data()
async def test_rule(avrae, dhttp):
    pass  # rule data not included in static


@requires_data()
async def test_feat(avrae, dhttp):
    for feat in compendium.feats:
        avrae.message(f"!feat {feat.name}")
        if not feat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_racefeat(avrae, dhttp):
    for rfeat in itertools.chain(compendium.rfeats, compendium.subrfeats):
        avrae.message(f"!racefeat {rfeat.name}")
        if not rfeat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_race(avrae, dhttp):
    for race in itertools.chain(compendium.races, compendium.subraces):
        avrae.message(f"!race {race.name}")
        if not race.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_classfeat(avrae, dhttp):
    for cfeat in compendium.cfeats:
        avrae.message(f"!classfeat {cfeat.name}")
        if not cfeat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_class(avrae, dhttp):
    for klass in compendium.classes:
        avrae.message(f'!class "{klass.name}"')
        if not klass.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_subclass(avrae, dhttp):
    for subclass in compendium.subclasses:
        avrae.message(f"!subclass {subclass.name}")
        if not subclass.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_background(avrae, dhttp):
    for background in compendium.backgrounds:
        avrae.message(f"!background {background.name}")
        if not background.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_monster(avrae, dhttp):
    for monster in compendium.monsters:
        avrae.message(f"!monster {monster.name}")
        if not monster.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_spell(avrae, dhttp):
    for spell in compendium.spells:
        avrae.message(f"!spell {spell.name}")
        if not spell.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_item(avrae, dhttp):
    for item in itertools.chain(
        compendium.adventuring_gear, compendium.armor, compendium.magic_items, compendium.weapons
    ):
        avrae.message(f"!item {item.name}")
        if not item.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()
