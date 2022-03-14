"""
Simple lookup tests: look up every entry in test static data
"""
import itertools

import discord
import pytest

from gamedata.compendium import compendium
from tests.utils import requires_data

pytestmark = pytest.mark.asyncio

NOT_AVAILABLE_EMBED = discord.Embed(title="Connect your D&D Beyond account to view .+")


@requires_data()
async def test_rule(avrae, dhttp):
    pass  # rule data not included in static


@requires_data()
async def test_feat(avrae, dhttp):
    for feat in compendium.feats:
        avrae.message(f"!feat {feat.name}")
        await dhttp.receive_typing()
        if not feat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_racefeat(avrae, dhttp):
    for rfeat in itertools.chain(compendium.rfeats, compendium.subrfeats):
        avrae.message(f"!racefeat {rfeat.name}")
        await dhttp.receive_typing()
        if not rfeat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_race(avrae, dhttp):
    for race in itertools.chain(compendium.races, compendium.subraces):
        avrae.message(f"!race {race.name}")
        await dhttp.receive_typing()
        if not race.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_classfeat(avrae, dhttp):
    for cfeat in compendium.cfeats:
        avrae.message(f"!classfeat {cfeat.name}")
        await dhttp.receive_typing()
        if not cfeat.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_class(avrae, dhttp):
    for klass in compendium.classes:
        avrae.message(f'!class "{klass.name}"')
        await dhttp.receive_typing()
        if not klass.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_subclass(avrae, dhttp):
    for subclass in compendium.subclasses:
        avrae.message(f"!subclass {subclass.name}")
        await dhttp.receive_typing()
        if not subclass.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_background(avrae, dhttp):
    for background in compendium.backgrounds:
        avrae.message(f"!background {background.name}")
        await dhttp.receive_typing()
        if not background.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_monster(avrae, dhttp):
    for monster in compendium.monsters:
        avrae.message(f"!monster {monster.name}")
        await dhttp.receive_typing()
        if not monster.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_spell(avrae, dhttp):
    for spell in compendium.spells:
        avrae.message(f"!spell {spell.name}")
        await dhttp.receive_typing()
        if not spell.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()


@requires_data()
async def test_item(avrae, dhttp):
    for item in compendium.items:
        avrae.message(f"!item {item.name}")
        await dhttp.receive_typing()
        if not item.is_free:
            await dhttp.receive_message(embed=NOT_AVAILABLE_EMBED)
        await dhttp.drain()
