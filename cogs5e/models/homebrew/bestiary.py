import hashlib
import logging

import aiohttp

from cogs5e.models.errors import ExternalImportError, NoActiveBrew
from cogs5e.models.homebrew.mixins import CommonHomebrewMixin
from cogs5e.models.monster import Monster
from utils.functions import search_and_select

log = logging.getLogger(__name__)

# presented to the hash first - update this when bestiary or monster schema changes
# to invalidate the existing cache of data
BESTIARY_SCHEMA_VERSION = b'1'


class Bestiary(CommonHomebrewMixin):
    def __init__(self, _id, sha256: str, upstream: str,
                 name: str, monsters: list = None, desc: str = None,
                 **_):
        # metadata - should never change
        super().__init__(_id)
        self.sha256 = sha256
        self.upstream = upstream

        # content
        self.name = name
        self.desc = desc
        self._monsters = monsters  # only loaded if needed

    @classmethod
    def from_dict(cls, d):
        if 'monsters' in d:
            d['monsters'] = [Monster.from_bestiary(m) for m in d['monsters']]
        return cls(**d)

    @classmethod
    async def from_ctx(cls, ctx):
        active_bestiary = await cls.active_id(ctx)
        if active_bestiary is None:
            raise NoActiveBrew()
        return await cls.from_id(ctx, active_bestiary)

    @classmethod
    async def from_id(cls, ctx, oid):
        bestiary = await ctx.bot.mdb.bestiaries.find_one({"_id": oid},
                                                         projection={"monsters": False})
        if bestiary is None:
            raise ValueError("Bestiary does not exist")
        return cls.from_dict(bestiary)

    @classmethod
    async def from_critterdb(cls, ctx, url):
        log.info(f"Getting bestiary ID {url}...")
        index = 1
        creatures = []
        sha256_hash = hashlib.sha256()
        sha256_hash.update(BESTIARY_SCHEMA_VERSION)
        async with aiohttp.ClientSession() as session:
            for _ in range(100):  # 100 pages max
                log.info(f"Getting page {index} of {url}...")
                async with session.get(
                        f"http://critterdb.com/api/publishedbestiaries/{url}/creatures/{index}") as resp:
                    if not 199 < resp.status < 300:
                        raise ExternalImportError(
                            "Error importing bestiary: HTTP error. Are you sure the link is right?")
                    try:
                        raw_creatures = await resp.json()
                        sha256_hash.update(await resp.read())
                    except (ValueError, aiohttp.ContentTypeError):
                        raise ExternalImportError("Error importing bestiary: bad data. Are you sure the link is right?")
                    if not raw_creatures:
                        break
                    creatures.extend(raw_creatures)
                    index += 1
            async with session.get(f"http://critterdb.com/api/publishedbestiaries/{url}") as resp:
                try:
                    raw = await resp.json()
                except (ValueError, aiohttp.ContentTypeError):
                    raise ExternalImportError("Error importing bestiary metadata. Are you sure the link is right?")
                name = raw['name']
                desc = raw['description']
                sha256_hash.update(name.encode() + desc.encode())

        # try and find a bestiary by looking up upstream|hash
        # if it exists, return it
        # otherwise commit a new one to the db and return that
        sha256 = sha256_hash.hexdigest()
        log.debug(f"Bestiary hash: {sha256}")
        existing_bestiary = await ctx.bot.mdb.bestiaries.find_one({"upstream": url, "sha256": sha256})
        if existing_bestiary:
            log.info("This bestiary already exists, subscribing")
            existing_bestiary = Bestiary.from_dict(existing_bestiary)
            await existing_bestiary.subscribe(ctx)
            return existing_bestiary

        parsed_creatures = [Monster.from_critterdb(c) for c in creatures]
        b = cls(None, sha256, url, name, parsed_creatures, desc)
        await b.write_to_db(ctx)
        await b.subscribe(ctx)
        return b

    async def load_monsters(self, ctx):
        if not self._monsters:
            bestiary = await ctx.bot.mdb.bestiaries.find_one({"_id": self.id}, projection=['monsters'])
            self._monsters = [Monster.from_bestiary(m) for m in bestiary['monsters']]
        return self._monsters

    @property
    def monsters(self):
        if self._monsters is None:
            raise AttributeError("load_monsters() must be called before accessing bestiary monsters.")
        return self._monsters

    async def write_to_db(self, ctx):
        """Writes a new bestiary object to the database."""
        assert self._monsters is not None
        monsters = [m.to_dict() for m in self._monsters]

        data = {
            "sha256": self.sha256, "upstream": self.upstream,
            "name": self.name, "desc": self.desc, "monsters": monsters
        }

        result = await ctx.bot.mdb.bestiaries.insert_one(data)
        self.id = result.inserted_id

    async def delete(self, ctx):
        await ctx.bot.mdb.bestiaries.delete_one({"_id": self.id})
        await self.remove_all_tracking(ctx)

    # ==== subscriber helpers ====
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.bestiary_subscriptions

    async def set_server_active(self, ctx):
        """
        Sets the object as active for the contextual guild.
        This override is here because bestiaries' server active docs need a provider id.
        """
        sub_doc = {"type": "server_active", "subscriber_id": ctx.guild.id,
                   "object_id": self.id, "provider_id": ctx.author.id}
        await self.sub_coll(ctx).insert_one(sub_doc)

    async def unsubscribe(self, ctx):
        """The unsubscribe operation for bestiaries actually acts as a delete operation."""
        # unsubscribe me
        await super().unsubscribe(ctx)

        # remove all server subs that I provide
        await self.sub_coll(ctx).delete_many(
            {"type": "server_active", "provider_id": ctx.author.id, "object_id": self.id}
        )

        # if no one is subscribed to this bestiary anymore, delete it.
        if not await self.num_subscribers(ctx):
            await self.delete(ctx)

    @staticmethod
    async def user_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that the user has imported."""
        async for b in Bestiary.my_sub_ids(ctx):
            yield await Bestiary.from_id(ctx, b)

    @staticmethod
    async def server_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that are active on the server."""
        async for b in Bestiary.guild_active_ids(ctx):
            yield await Bestiary.from_id(ctx, b)

    # ==== bestiary-specific database helpers ====
    async def server_subscriptions(self, ctx):
        """Returns a list of server ids (ints) representing server subscriptions supplied by the contextual author.
        Mainly used to determine what subscriptions should be carried over to a new bestiary when updated."""
        subs = ctx.bot.mdb.bestiary_subscriptions.find(
            {"type": "server_active", "object_id": self.id, "provider_id": ctx.author.id})
        return [s['subscriber_id'] async for s in subs]

    async def add_server_subscriptions(self, ctx, serv_ids):
        """Subscribes a list of servers to this bestiary."""
        existing = await ctx.bot.mdb.bestiary_subscriptions.find(
            {"type": "server_active", "subscriber_id": {"$in": serv_ids}}
        ).to_list(None)
        existing = {e['subscriber_id'] for e in existing}
        sub_docs = [{"type": "server_active", "subscriber_id": serv_id,
                     "object_id": self.id, "provider_id": ctx.author.id} for serv_id in serv_ids if
                    serv_id not in existing]
        if sub_docs:
            await ctx.bot.mdb.bestiary_subscriptions.insert_many(sub_docs)

    @staticmethod
    async def num_user(ctx):
        """Returns the number of bestiaries a user has imported."""
        return await ctx.bot.mdb.bestiary_subscriptions.count_documents(
            {"type": "subscribe", "subscriber_id": ctx.author.id}
        )

    async def get_server_sharer(self, ctx):
        """Returns the user ID of the user who shared this bestiary with the server."""
        sub = await ctx.bot.mdb.bestiary_subscriptions.find_one(
            {"type": "server_active", "object_id": self.id}
        )
        if sub is None:
            raise ValueError("This bestiary is not active on this server.")
        return sub.get("provider_id")


async def select_bestiary(ctx, name):
    user_bestiaries = []
    async for b in Bestiary.user_bestiaries(ctx):
        user_bestiaries.append(b)
    if not user_bestiaries:
        raise NoActiveBrew()

    bestiary = await search_and_select(ctx, user_bestiaries, name, key=lambda b: b.name,
                                       selectkey=lambda b: f"{b.name} (`{b.upstream})`")
    return bestiary
