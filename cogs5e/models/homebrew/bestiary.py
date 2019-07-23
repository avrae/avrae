import hashlib
import logging

import aiohttp

from cogs5e.models.errors import ExternalImportError, NoActiveBrew, NotAllowed
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
        self.server_active = server_active  # [{"subscriber_id": string, "guild_id": string}, ...]

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
        b = cls(None, sha256, url, [], [], [], name, parsed_creatures, desc)
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
        subscribers = [str(ctx.author.id)]
        monsters = [m.to_dict() for m in self._monsters]

        data = {
            "sha256": self.sha256, "upstream": self.upstream, "subscribers": subscribers, "active": [],
            "server_active": [], "name": self.name, "desc": self.desc, "monsters": monsters
        }

        result = await ctx.bot.mdb.bestiaries.insert_one(data)
        self.id = result.inserted_id

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
        sub_doc = {"guild_id": guild_id, "subscriber_id": str(ctx.author.id)}

        if sub_doc in self.server_active:  # I subscribed and want to unsubscribe
            await ctx.bot.mdb.bestiaries.update_one(
                {"_id": self.id},
                {"$pull": {"server_active": sub_doc}}
            )
            self.server_active.remove(sub_doc)
        elif guild_id in map(lambda s: s['guild_id'],
                             self.server_active):  # someone else has already served this bestiary
            raise NotAllowed("Another user is already sharing this bestiary with the server!")
        else:  # no one has served this bestiary and I want to
            await ctx.bot.mdb.bestiaries.update_one(
                {"_id": self.id},
                {"$push": {"server_active": sub_doc}}
            )
            self.server_active.append(sub_doc)

        return sub_doc in self.server_active

    async def subscribe(self, ctx):
        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$addToSet": {"subscribers": str(ctx.author.id)}}
        )
        self.subscribers.append(str(ctx.author.id))

    async def unsubscribe(self, ctx):
        author_id = str(ctx.author.id)
        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$pull": {"subscribers": author_id,
                       "server_active": {"subscriber_id": author_id}}
             }
        )

        if author_id in self.subscribers:
            self.subscribers.remove(author_id)
        for serv_sub in self.server_subscriptions(ctx):
            if serv_sub in self.server_active:
                self.server_active.remove(serv_sub)

        # if no one is subscribed to this bestiary anymore, delete it.
        if not self.subscribers:
            await self.delete(ctx)

    def server_subscriptions(self, ctx):
        """Returns a list of server_active objects supplied by the contextual author.
        Mainly used to determine what subscriptions should be carried over to a new bestiary when updated."""
        return [s for s in self.server_active if s['subscriber_id'] == str(ctx.author.id)]

    async def add_server_subscriptions(self, ctx, subscriptions):
        """Adds a list of server_active objects to the existing list."""
        existing_serv_sub_set = set(s['guild_id'] for s in self.server_active)
        for sub in reversed(subscriptions):
            if sub['guild_id'] in existing_serv_sub_set:
                subscriptions.remove(sub)

        await ctx.bot.mdb.bestiaries.update_one(
            {"_id": self.id},
            {"$push": {"server_active": {"$each": subscriptions}}}
        )
        self.server_active.extend(subscriptions)

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
        async for b in ctx.bot.mdb.bestiaries.find({"server_active.guild_id": str(ctx.guild.id)},
                                                   projection={"monsters": False}):
            yield Bestiary.from_dict(b)


async def select_bestiary(ctx, name):
    user_bestiaries = []
    async for b in Bestiary.user_bestiaries(ctx):
        user_bestiaries.append(b)
    if not user_bestiaries:
        raise NoActiveBrew()

    bestiary = await search_and_select(ctx, user_bestiaries, name, key=lambda b: b.name,
                                       selectkey=lambda b: f"{b.name} (`{b.upstream})`")
    return bestiary
