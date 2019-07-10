import hashlib
import logging

import aiohttp

from cogs5e.models.errors import ExternalImportError, NoActiveBrew
from cogs5e.models.monster import Monster
from utils.functions import search_and_select

log = logging.getLogger(__name__)


class Bestiary:
    def __init__(self, _id, sha256: str, upstream: str, subscribers: list, active: list, server_active: list,
                 name: str, monsters: list = None, desc: str = None):
        # metadata - should never change
        self.id = _id
        self.sha256 = sha256
        self.upstream = upstream

        # subscription data - only atomic writes
        self.subscribers = subscribers
        self.active = active
        self.server_active = server_active

        # content
        self.name = name
        self.desc = desc
        self._monsters = monsters  # only loaded if needed

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    @classmethod
    async def from_critterdb(cls, ctx, url):
        log.info(f"Getting bestiary ID {url}...")
        index = 1
        creatures = []
        sha256_hash = hashlib.sha256()
        async with aiohttp.ClientSession() as session:
            for _ in range(100):  # 100 pages max
                log.info(f"Getting page {index} of {url}...")
                async with session.get(
                        f"http://critterdb.com/api/publishedbestiaries/{url}/creatures/{index}") as resp:
                    if not 199 < resp.status < 300:
                        raise ExternalImportError("Error importing bestiary. Are you sure the link is right?")
                    try:
                        raw_creatures = await resp.json()
                        sha256_hash.update(await resp.read())
                    except ValueError:
                        raise ExternalImportError("Error importing bestiary. Are you sure the link is right?")
                    if not raw_creatures:
                        break
                    creatures.extend(raw_creatures)
                    index += 1
            async with session.get(f"http://critterdb.com/api/publishedbestiaries/{url}") as resp:
                try:
                    raw = await resp.json()
                except ValueError:
                    raise ExternalImportError("Error importing bestiary metadata. Are you sure the link is right?")
                name = raw['name']
                desc = raw['description']
                sha256_hash.update(name.encode() + desc.encode())

        # try and find a bestiary by looking up upstream|hash
        # if it exists, return it
        # otherwise commit a new one to the db and return that
        existing_bestiary = await ctx.bot.mdb.bestiaries.find_one({"upstream": url, "sha256": sha256_hash.hexdigest()})
        if existing_bestiary:
            await existing_bestiary.subscribe(ctx)
            return existing_bestiary

        parsed_creatures = [Monster.from_critterdb(c) for c in creatures]
        b = cls(None, sha256_hash.hexdigest(), url, [], [], [], name, parsed_creatures, desc)
        await b.write_to_db(ctx)
        return b

    @classmethod
    async def from_ctx(cls, ctx):
        active_bestiary = await ctx.bot.mdb.bestiaries.find_one({"active": str(ctx.author.id)},
                                                                projection={"monsters": False})
        if active_bestiary is None:
            raise NoActiveBrew()
        return cls.from_dict(active_bestiary)

    async def load_monsters(self, ctx):
        if not self._monsters:
            monsters = await ctx.bot.mdb.bestiaries.find_one({"_id": self.id}, projection=['monsters'])
            self._monsters = [Monster.from_bestiary(m) for m in monsters]
        return self._monsters

    @property
    def monsters(self):
        if not self._monsters:
            raise AttributeError("load_monsters() must be called before accessing bestiary monsters.")
        return self._monsters

    async def write_to_db(self, ctx):
        """Writes a bestiary object to the database. Returns self."""
        assert self._monsters is not None
        data = {
            "sha256": self.sha256, "upstream": self.upstream, "subscribers": [str(ctx.author.id)], "active": [],
            "server_active": [], "name": self.name, "desc": self.desc, "monsters": [m.to_dict() for m in self._monsters]
        }

        result = await ctx.bot.mdb.bestiaries.insert_one(data)
        self.id = result.inserted_id
        return self

    async def set_active(self, ctx):
        """Sets the bestiary as active for the contextual author."""
        await ctx.bot.mdb.bestiaries.update_many(
            {"active": str(ctx.author.id)},
            {"$pull": {"active": str(ctx.author.id)}}
        )
        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$push": {"active": str(ctx.author.id)}}
        )
        return self

    async def toggle_server_active(self, ctx):
        """
        Toggles whether the bestiary should be active on the contextual server.
        :param ctx: Context
        :return: Whether the bestiary is now active on the server.
        """
        guild_id = str(ctx.guild.id)
        if guild_id in self.server_active:
            await ctx.bot.mdb.bestiaries.update_one(
                {"_id": self.id},
                {"$pull": {"active": guild_id}}
            )
            self.server_active.remove(guild_id)
        else:
            await ctx.bot.mdb.bestiaries.update_one(
                {"_id": self.id},
                {"$push": {"active": guild_id}}
            )
            self.server_active.append(guild_id)

        return guild_id in self.server_active

    async def subscribe(self, ctx):
        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$addToSet": {"subscribers": str(ctx.author.id)}}
        )
        self.subscribers.append(str(ctx.author.id))

    async def unsubscribe(self, ctx):
        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$pull": {"subscribers": str(ctx.author.id)}}
        )
        if str(ctx.author.id) in self.subscribers:
            self.subscribers.remove(str(ctx.author.id))

        # if no one is subscribed to this bestiary anymore, delete it.
        if not self.subscribers:
            await self.delete(ctx)

    async def delete(self, ctx):
        await ctx.bot.mdb.bestiaries.delete_one({"_id": self.id})

    @staticmethod
    async def num_user(ctx):
        """Returns the number of bestiaries a user has imported."""
        return await ctx.bot.mdb.bestiaries.count_documents({"subscribers": str(ctx.author.id)})

    @staticmethod
    async def user_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that the user has imported."""
        async for b in ctx.bot.mdb.bestiaries.find({"subscribers": str(ctx.author.id)},
                                                   projection={"monsters": False}):
            yield Bestiary.from_dict(b)

    @staticmethod
    async def server_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that are active on the server."""
        async for b in ctx.bot.mdb.bestiaries.find({"server_active": str(ctx.guild.id)},
                                                   projection={"monsters": False}):
            yield Bestiary.from_dict(b)


async def select_bestiary(ctx, name):
    user_bestiaries = []
    async for b in Bestiary.user_bestiaries(ctx):
        user_bestiaries.append(b)
    if not user_bestiaries:
        raise NoActiveBrew()

    bestiary = await search_and_select(ctx, user_bestiaries, name, key=lambda b: b['name'],
                                       selectkey=lambda b: f"{b['name']} (`{b['upstream']})`")
    return Bestiary.from_dict(bestiary)
