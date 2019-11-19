import hashlib
import logging

import aiohttp

from cogs5e.models.errors import ExternalImportError, NoActiveBrew
from cogs5e.models.homebrew.mixins import CommonHomebrewMixin
from cogs5e.models.monster import Monster
from utils.functions import search_and_select

log = logging.getLogger(__name__)


class Bestiary(CommonHomebrewMixin):
    def __init__(self, _id, sha256: str, upstream: str,
                 name: str, monsters: list = None, desc: str = None,
                 **_):
        # metadata - should never change
        self.id = _id
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

    @classmethod
    async def from_ctx(cls, ctx):
        active_bestiary = await ctx.bot.mdb.bestiary_subscriptions.find_one(
            {"type": "active", "subscriber_id": ctx.author.id})
        if active_bestiary is None:
            raise NoActiveBrew()
        return await cls.from_id(ctx, active_bestiary['object_id'])

    @classmethod
    async def from_id(cls, ctx, oid):
        bestiary = await ctx.bot.mdb.bestiaries.find_one({"_id": oid},
                                                         projection={"monsters": False})
        if bestiary is None:
            raise ValueError("Bestiary does not exist")
        return cls.from_dict(bestiary)

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

    async def set_active(self, ctx):
        """Sets the bestiary as active for the contextual author."""
        await ctx.bot.mdb.bestiary_subscriptions.delete_many(
            {"type": "active", "subscriber_id": ctx.author.id}
        )
        await ctx.bot.mdb.bestiary_subscriptions.insert_one(
            {"type": "active", "subscriber_id": ctx.author.id, "object_id": self.id}
        )
        return self

    async def toggle_server_active(self, ctx):
        """
        Toggles whether the bestiary should be active on the contextual server.
        :param ctx: Context
        :return: Whether the bestiary is now active on the server.
        """
        sub_query = {"type": "server_active", "subscriber_id": ctx.guild.id}
        sub_doc = await ctx.bot.mdb.bestiary_subscriptions.find_one(sub_query)

        if sub_doc is not None:  # I subscribed and want to unsubscribe
            await ctx.bot.mdb.bestiary_subscriptions.delete_one(sub_query)
            return False
        else:  # no one has served this bestiary and I want to
            sub_doc = {"type": "server_active", "subscriber_id": ctx.guild.id,
                       "object_id": self.id, "provider_id": ctx.author.id}
            await ctx.bot.mdb.bestiary_subscriptions.insert_one(sub_doc)
            return True

    async def subscribe(self, ctx):
        await ctx.bot.mdb.bestiary_subscriptions.insert_one(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

    async def unsubscribe(self, ctx):
        # unsubscribe me
        await ctx.bot.mdb.bestiary_subscriptions.delete_many(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

        # remove all server subs that I provide
        await ctx.bot.mdb.bestiary_subscriptions.delete_many(
            {"type": "server_active", "provider_id": ctx.author.id, "object_id": self.id}
        )

        # if no one is subscribed to this bestiary anymore, delete it.
        if not await ctx.bot.mdb.bestiary_subscriptions.count_documents({"type": "subscribe", "object_id": self.id}):
            await self.delete(ctx)

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

    async def delete(self, ctx):
        await ctx.bot.mdb.bestiaries.delete_one({"_id": self.id})
        await self.remove_all_tracking(ctx)

    async def remove_all_tracking(self, ctx):
        await ctx.bot.mdb.bestiary_subscriptions.delete_many({"object_id": self.id})

    @staticmethod
    async def num_user(ctx):
        """Returns the number of bestiaries a user has imported."""
        return await ctx.bot.mdb.bestiary_subscriptions.count_documents(
            {"type": "subscribe", "subscriber_id": ctx.author.id}
        )

    @staticmethod
    async def user_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that the user has imported."""
        async for b in ctx.bot.mdb.bestiary_subscriptions.find(
                {"type": "subscribe", "subscriber_id": ctx.author.id}):
            yield await Bestiary.from_id(ctx, b['object_id'])

    @staticmethod
    async def server_bestiaries(ctx):
        """Returns an async iterator of partial Bestiary objects that are active on the server."""
        async for b in ctx.bot.mdb.bestiary_subscriptions.find(
                {"type": "server_active", "subscriber_id": ctx.guild.id}):
            yield await Bestiary.from_id(ctx, b['object_id'])

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
