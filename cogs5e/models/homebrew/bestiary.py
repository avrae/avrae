import logging

import aiohttp

from cogs5e.models.errors import NoActiveBrew, ExternalImportError, NoSelectionElements, SelectionCancelled
from cogs5e.models.monster import Monster
from utils.functions import get_selection

log = logging.getLogger(__name__)


class Bestiary:
    def __init__(self, _id: str, name: str, monsters: list):
        self.id = _id
        self.name = name
        self.monsters = monsters

    @classmethod
    def from_raw(cls, _id, raw):
        monsters = [Monster.from_bestiary(m) for m in raw['monsters']]
        return cls(_id, raw['name'], monsters)

    @classmethod
    async def from_ctx(cls, ctx):
        active_bestiary = await ctx.bot.mdb.bestiaries.find_one({"owner": ctx.message.author.id, "active": True})
        if active_bestiary is None:
            raise NoActiveBrew()
        return cls.from_raw(active_bestiary['critterdb_id'], active_bestiary)

    def to_dict(self):
        return {'monsters': [m.to_dict() for m in self.monsters], 'name': self.name, 'critterdb_id': self.id}

    async def commit(self, ctx):
        """Writes a bestiary object to the database, under the contextual author. Returns self."""
        data = {"$set": self.to_dict(), "$setOnInsert": {"owner": ctx.message.author.id}}

        await ctx.bot.mdb.bestiaries.update_one(
            {"owner": ctx.message.author.id, "critterdb_id": self.id},
            data,
            True
        )
        return self

    async def set_active(self, ctx):
        await ctx.bot.mdb.bestiaries.update_many(
            {"owner": ctx.message.author.id, "active": True},
            {"$set": {"active": False}}
        )
        await ctx.bot.mdb.bestiaries.update_one(
            {"owner": ctx.message.author.id, "critterdb_id": self.id},
            {"$set": {"active": True}}
        )
        return self


async def select_bestiary(ctx, name):
    user_bestiaries = await ctx.bot.mdb.bestiaries.find({"owner": ctx.message.author.id}).to_list(None)

    if not user_bestiaries:
        raise NoActiveBrew()
    choices = []
    for bestiary in user_bestiaries:
        url = bestiary['critterdb_id']
        if bestiary['name'].lower() == name.lower():
            choices.append((bestiary, url))
        elif name.lower() in bestiary['name'].lower():
            choices.append((bestiary, url))

    if len(choices) > 1:
        choiceList = [(f"{c[0]['name']} (`{c[1]})`", c) for c in choices]

        result = await get_selection(ctx, choiceList, delete=True)
        if result is None:
            raise SelectionCancelled()

        bestiary = result[0]
        bestiary_url = result[1]
    elif len(choices) == 0:
        raise NoSelectionElements()
    else:
        bestiary = choices[0][0]
        bestiary_url = choices[0][1]
    return Bestiary.from_raw(bestiary_url, bestiary)


async def bestiary_from_critterdb(url):
    log.info(f"Getting bestiary ID {url}...")
    index = 1
    creatures = []
    async with aiohttp.ClientSession() as session:
        for _ in range(100):  # 100 pages max
            log.info(f"Getting page {index} of {url}...")
            async with session.get(
                    f"http://critterdb.com/api/publishedbestiaries/{url}/creatures/{index}") as resp:
                if not 199 < resp.status < 300:
                    raise ExternalImportError("Error importing bestiary. Are you sure the link is right?")
                try:
                    raw = await resp.json()
                except ValueError:
                    raise ExternalImportError("Error importing bestiary. Are you sure the link is right?")
                if not raw:
                    break
                creatures.extend(raw)
                index += 1
        async with session.get(f"http://critterdb.com/api/publishedbestiaries/{url}") as resp:
            raw = await resp.json()
            name = raw['name']
    parsed_creatures = [Monster.from_critterdb(c) for c in creatures]
    return Bestiary(url, name, parsed_creatures)
